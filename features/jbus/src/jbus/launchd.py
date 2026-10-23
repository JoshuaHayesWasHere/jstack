"""What jbus reads of the launchd agents that the install runs on macOS in place of the systemd
units (`jinstall.launchd` makes them): each agent's label, the log launchd writes for it, and
the words of that log and of `launchctl print`."""

from pathlib import Path

PREFIX = "jstack."
NOT_LOADED = (3, 113)
"""What `launchctl print` and `bootout` exit with for a service the domain does not have: 113,
or 3 (ESRCH) on older releases."""
STARTED = "jstack: started "
"""The line each run of an agent starts its log with, then the run's start in epoch seconds."""
TIMED_OUT = "jstack: Failed with result 'timeout'"
"""What an agent's shell says when it stops the command at its start timeout: the words that
systemd's journal gives, which `jbus.health` counts."""


def label(unit: str) -> str:
    """The agent's label, `jstack.<the unit's stem>`: `jstack.jbus` for jbus.timer and
    jbus.service."""
    return PREFIX + unit.rsplit(".", 1)[0]


def log(home: Path, name: str) -> Path:
    """Where launchd writes what the agent of label `name` says."""
    return home / "Library" / "Logs" / "jstack" / f"{name}.log"


def parse_print(said: str) -> dict[str, str]:
    """The `key = value` lines of `launchctl print`, at any depth, the first of each key."""
    found: dict[str, str] = {}
    for line in said.splitlines():
        key, sep, value = line.strip().partition(" = ")
        if sep and not value.endswith("{"):
            found.setdefault(key, value)
    return found


def recent(lines: list[str], after: float) -> list[str]:
    """The lines of each run that started at `after` or later, by the start marker that opens
    each run. The markers are not among them."""
    kept, started = [], None
    for line in lines:
        if line.startswith(STARTED):
            try:
                started = int(line.removeprefix(STARTED))
            except ValueError:
                started = None
            continue
        if started is not None and started >= after:
            kept.append(line)
    return kept
