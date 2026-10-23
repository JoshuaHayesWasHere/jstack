"""The launchd agents of macOS, made from the same unit templates as the systemd units.

The templates under `features/*/units/` are the one source. `agents` reads them and gives one
`Agent` for each unit that systemd would enable: each timer, run with the service of its stem,
and each service that `[Install]` puts under `default.target`. The services that only a timer
starts, or that only an `OnFailure=` names, are part of the agent that runs them.

Each key of a template is carried over or dropped, by `CARRIED` and `DROPPED`. A key that is in
neither raises ValueError, so a template that gains a key fails until someone decides what it
becomes on macOS.

`text` writes an agent as the plist launchd reads from `~/Library/LaunchAgents/<label>.plist`,
with a comment that names the source the install made it from: the plist belongs to the install
whose source it names, as a link belongs to the install whose layout it points into.

Every agent runs its command through `/bin/sh`, which first prints `jstack: started <epoch>`.
launchd keeps no journal of an agent, so it writes what the agent says to `log`, and the marker
lets a reader keep the runs of a time window, as `journalctl --since` does. What a reader needs
of an agent, its label, its log and how to read both, is jbus's (`jbus.launchd`), which this
module uses.
"""

import plistlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from jbus.launchd import STARTED, TIMED_OUT, label, log

HOMEBREW = "/opt/homebrew/bin"
"""Where Homebrew puts its programs on Apple Silicon, `gh` and `jq` among them, which the PATH of
each agent has after `~/.local/bin`."""
LOG_CAP = 1048576
"""launchd never rotates an agent's log, so the shell empties it at the start of a run once it
holds this many bytes."""
MADE = "<!-- jstack: made by the install from "
WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
SECONDS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hour": 3600}
CALENDAR = re.compile(r"(?:(?P<day>[A-Z][a-z]{2}) )?\*-\*-\* (?P<h>\d\d):(?P<m>\d\d)(?::00)?")

CARRIED = {
    ("Service", "ExecStart"): "the command",
    ("Service", "Environment"): "EnvironmentVariables",
    ("Service", "EnvironmentFile"): "read line by line by the shell, which runs none of it",
    ("Service", "Restart"): "KeepAlive: always, or only after a failed exit",
    ("Service", "RestartSec"): "ThrottleInterval",
    ("Service", "RestartPreventExitStatus"): "the shell exits 0 for it: no restart",
    ("Service", "TimeoutStartSec"): "the shell stops the command and says so as systemd does",
    ("Unit", "OnFailure"): "the failure service's command runs when the command fails",
    ("Timer", "OnUnitActiveSec"): "StartInterval",
    ("Timer", "OnCalendar"): "StartCalendarInterval",
    ("Install", "WantedBy"): "default.target makes the service an agent of its own",
}
DROPPED = {
    ("Unit", "Description"): "launchd keeps no description",
    ("Unit", "Documentation"): "launchd keeps no documentation",
    ("Service", "Type"): "launchd runs each agent as a process, a oneshot included",
    ("Service", "SuccessExitStatus"): "the view, the one unit with it, gets no agent",
    ("Service", "RestartForceExitStatus"): "the view, the one unit with it, gets no agent",
    ("Timer", "OnBootSec"): "launchd starts an interval agent one interval after it loads",
    ("Timer", "OnActiveSec"): "launchd starts an interval agent one interval after it loads",
    ("Timer", "AccuracySec"): "launchd has no accuracy to set",
    ("Timer", "Persistent"): "launchd runs a calendar job missed asleep on wake, not after off",
}


@dataclass(frozen=True)
class Agent:
    """One launchd agent. `unit` is the unit that systemd would enable in its place, and
    `templates` the files it is made from. `schedule` holds the keys that say when launchd
    starts it: StartInterval or StartCalendarInterval for a timer, RunAtLoad and KeepAlive for a
    service that runs all the time."""

    label: str
    unit: str
    templates: tuple[Path, ...]
    script: str
    environment: dict[str, str] = field(default_factory=dict)
    schedule: dict = field(default_factory=dict)


def read_unit(path: Path) -> dict[tuple[str, str], list[str]]:
    """Each `(section, key)` of a unit file, with every value it is given, in order."""
    found: dict[tuple[str, str], list[str]] = {}
    section = ""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        key, _, value = line.partition("=")
        if (section, key) not in CARRIED and (section, key) not in DROPPED:
            raise ValueError(f"{path.name}: [{section}] {key}= has no launchd form")
        found.setdefault((section, key), []).append(value)
    return found


def seconds(text: str) -> int:
    """A systemd time span, such as `15s`, `2min` or `1h 30min`, in seconds."""
    parts = re.findall(r"(\d+)\s*([a-z]*)", text)
    if not parts or "".join(n + u for n, u in parts) != text.replace(" ", ""):
        raise ValueError(f"{text} is not a time span")
    if any(unit not in SECONDS and unit for _, unit in parts):
        raise ValueError(f"{text} is not a time span")
    return sum(int(n) * SECONDS[unit or "s"] for n, unit in parts)


def calendar(text: str) -> dict[str, int]:
    """One `OnCalendar=` of the form `[<weekday>] *-*-* HH:MM[:00]` as a launchd calendar
    interval."""
    found = CALENDAR.fullmatch(text)
    if found is None or (found["day"] and found["day"] not in WEEKDAYS):
        raise ValueError(f"OnCalendar={text} has no launchd form")
    when = {"Hour": int(found["h"]), "Minute": int(found["m"])}
    return ({"Weekday": WEEKDAYS.index(found["day"])} if found["day"] else {}) | when


def _one(unit: dict, key: tuple[str, str]) -> str | None:
    values = unit.get(key, [])
    return values[-1] if values else None


def _command(unit: dict, home: Path) -> str:
    start = _one(unit, ("Service", "ExecStart"))
    if start is None:
        raise ValueError("a service with no ExecStart=")
    return shlex.join(shlex.split(start.replace("%h", str(home))))


ENVIRONMENT_FILE = r"""{
    sub(/^[ \t\r]+/, ""); sub(/[ \t\r]+$/, "")
    at = index($0, "="); if (!at) next
    key = substr($0, 1, at - 1); value = substr($0, at + 1)
    sub(/^[ \t]+/, "", key); sub(/[ \t]+$/, "", key)
    if (key !~ /^[A-Za-z_][A-Za-z0-9_]*$/) next
    sub(/^[ \t]+/, "", value); sub(/[ \t]+$/, "", value)
    gsub("^[\"" q "]+|[\"" q "]+$", "", value)
    print key "\t" value
}"""
"""The awk that reads an `EnvironmentFile=` as systemd and `jbus.relay.env_file` read it: one
`KEY=value` a line, the key a variable name, the value trimmed and with its quotes left out. It
prints `KEY<tab>value`, and the shell exports each value as it is, so no line of the file runs."""


def _environment_file(path: str) -> list[str]:
    """The lines that export each variable of the env file at `path`, or stop the run, as
    systemd does, when there is no such file."""
    return [
        f'[ -r {path} ] || {{ echo "jstack: {path} cannot be read"; exit 1; }}',
        "tab=$(printf '\\t')",
        f"pairs=$(awk -v q=\"'\" '{ENVIRONMENT_FILE}' {path})",
        'while IFS="$tab" read -r key value; do',
        '    [ -z "$key" ] || export "$key=$value"',
        "done << THE_PAIRS_END_HERE",
        "$pairs",
        "THE_PAIRS_END_HERE",
    ]


def _script(service: dict, units: dict[str, dict], home: Path, name: str) -> str:
    """The shell that runs the service as systemd would: the start marker, the environment
    file, the command (stopped at the start timeout), the failure service's command when the
    command fails, and the exit status of the command. With nothing to do after the command,
    the shell is replaced by it, so the process launchd keeps and stops is the command.

    The start timeout's watcher gets a process group of its own (`set -m`), and the whole group
    is killed once the command ends. A sleep it forks as the KILL lands is in that group too:
    the kernel restarts a fork that a signal to its group interrupts, and no shell can catch a
    KILL, so nothing of the watcher outlives the agent to hold its output open."""
    said = shlex.quote(str(log(home, name)))
    lines = [
        f'[ "$(wc -c < {said} 2> /dev/null || echo 0)" -lt {LOG_CAP} ] || : > {said}',
        f'echo "{STARTED}$(date +%s)"',
    ]
    for each in service.get(("Service", "EnvironmentFile"), []):
        lines += _environment_file(shlex.quote(each.replace("%h", str(home))))
    command = _command(service, home)
    timeout = _one(service, ("Service", "TimeoutStartSec"))
    failure = _one(service, ("Unit", "OnFailure"))
    prevent = _one(service, ("Service", "RestartPreventExitStatus"))
    if timeout is None and failure is None and prevent is None:
        return "\n".join([*lines, f"exec {command}"])
    if timeout is None:
        lines += [command, "code=$?"]
    else:
        lines += [
            f"{command} &",
            "pid=$!",
            "set -m",
            f'(sleep {seconds(timeout)}; kill "$pid" 2> /dev/null && echo "{TIMED_OUT}") &',
            "watch=$!",
            "set +m",
            'wait "$pid"; code=$?',
            'kill -KILL -- "-$watch" 2> /dev/null',
        ]
    if failure is not None:
        lines.append(f'[ "$code" -eq 0 ] || {_command(units[failure], home)}')
    if prevent is not None:
        stop = f'echo "jstack: exit {int(prevent)} is not restarted"; exit 0'
        lines.append(f'[ "$code" -ne {int(prevent)} ] || {{ {stop}; }}')
    return "\n".join([*lines, 'exit "$code"'])


def _environment(service: dict, home: Path) -> dict[str, str]:
    """`Environment=`, with Homebrew's programs on PATH after `~/.local/bin`."""
    found = {}
    for each in service.get(("Service", "Environment"), []):
        key, _, value = each.partition("=")
        found[key] = value.replace("%h", str(home))
    if "PATH" in found:
        first, sep, rest = found["PATH"].partition(":")
        found["PATH"] = f"{first}:{HOMEBREW}{sep}{rest}"
    return found


def _kept(service: dict) -> dict:
    """RunAtLoad and KeepAlive for a service that runs all the time, by its `Restart=`."""
    restart = _one(service, ("Service", "Restart"))
    alive: bool | dict = {"SuccessfulExit": False} if restart == "on-failure" else True
    found: dict = {"RunAtLoad": True, "KeepAlive": alive}
    throttle = _one(service, ("Service", "RestartSec"))
    return found | ({"ThrottleInterval": seconds(throttle)} if throttle else {})


def _timed(timer: dict) -> dict:
    interval = _one(timer, ("Timer", "OnUnitActiveSec"))
    days = timer.get(("Timer", "OnCalendar"), [])
    if bool(interval) == bool(days):
        raise ValueError("a timer has one of OnUnitActiveSec= and OnCalendar=")
    if interval:
        return {"StartInterval": seconds(interval)}
    return {"StartCalendarInterval": [calendar(one) for one in days]}


def agents(templates: dict[str, Path], home: Path) -> dict[str, Agent]:
    """One agent for each unit that systemd would enable, by that unit's name."""
    units = {name: read_unit(path) for name, path in templates.items()}
    found = {}
    for name, unit in sorted(units.items()):
        stem, _, kind = name.rpartition(".")
        if kind == "timer":
            service = f"{stem}.service"
            schedule = _timed(unit)
            made = (templates[name], templates[service])
        elif _one(unit, ("Install", "WantedBy")) == "default.target":
            service, schedule, made = name, _kept(unit), (templates[name],)
        else:
            continue
        found[name] = Agent(
            label(name),
            name,
            made,
            _script(units[service], units, home, label(name)),
            _environment(units[service], home),
            schedule,
        )
    return found


def text(agent: Agent, home: Path, source: Path) -> str:
    """The plist of `agent`, with the comment that names `source`, percent-encoded so that no
    `--` of a path ends the comment."""
    said = str(log(home, agent.label))
    value = {
        "Label": agent.label,
        "ProgramArguments": ["/bin/sh", "-c", agent.script],
        "StandardOutPath": said,
        "StandardErrorPath": said,
        **({"EnvironmentVariables": agent.environment} if agent.environment else {}),
        **agent.schedule,
    }
    head, _, rest = plistlib.dumps(value, sort_keys=True).decode().partition("<plist")
    where = quote(str(source)).replace("-", "%2D")
    named = f"{MADE}{where}; it rewrites this file, and an edit is lost -->\n"
    return f"{head}{named}<plist{rest}"


def made_from(said: str) -> str | None:
    """The source a plist's comment names, or None for a plist that no install made."""
    start = said.find(MADE)
    if start < 0:
        return None
    return unquote(said[start + len(MADE) :].partition("; it rewrites")[0])
