"""Whether the bus is alive: the timer and the service as systemd reports them, the last pass,
the status file, and which code of the view answers. On macOS launchd runs the timer and the
service as one agent (`jbus.launchd`), and `launchd` gives its answer in systemd's words.

jbus has stopped when the timer is not active, or when the last pass ended more than `QUIET`
seconds ago and systemd does not report a pass running now. A pass that starts and crashes each
minute has stopped too, because only the end of a pass counts, not its start.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from typing import Any

from jbus import launchd as agents
from jbus.view.clean import ANY
from jbus.view.state import (
    PASS_FILE,
    Read,
    Source,
    Spot,
    _mtime,
    _table,
    count,
    iso,
    kept,
    text,
    when,
)
from jmerge import mainjson

FIRST = True
QUIET = 150
TIMER, SERVICE = "jbus.timer", "jbus.service"
ASKED = "Id,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,LastTriggerUSec"
_SHA = re.compile(r"[0-9a-f]{7,40}")
SHAPE = {
    "jbus": {
        "stopped": None,
        "why": None,
        "quiet": None,
        "last_end": None,
        "said": None,
        "manager": None,
        "pass": {"started": None, "ended": None, "seconds": None, "running": None},
        "timer": {"active": None, "sub": None, "enabled": None, "last_trigger": None},
        "status": {
            "last_pass": None,
            "token_expires": None,
            "failed_wakes": None,
            "last_error": None,
            "outbox": None,
            "top_level": {"failed_wakes": None, "last_error": None, "outbox": None},
            "blocking": {"failed_wakes": None, "last_error": None, "outbox": None},
            "sign_in": None,
            "sweep": None,
            "streaks": {ANY: None},
            "homes_off_bus": [None],
            "scratch": [{"name": None, "home_thread": None}],
        },
        "code": {"started": None, "stale": None, "error": None},
    },
    "main": {"sha": None, "at": None},
}
NOT_KEPT = (
    Spot("only the last pass is kept, not the ones before it", 500),
    Spot(
        "a pass that raised, or could not read its queue, is not said on a task: "
        "only T3 Code and GitHub are",
        530,
    ),
)


def systemd(read: Read) -> dict[str, dict[str, str]] | None:
    """What systemd says of the timer and the service, or None where systemd did not answer. The
    answer is the same for the whole machine, so the server asks systemd once for each answer
    it builds (`Read.machine`)."""
    try:
        asked = subprocess.run(
            ["systemctl", "--user", "show", TIMER, SERVICE, "-p", ASKED],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if asked.returncode:
        return None
    units: dict[str, dict[str, str]] = {}
    for block in asked.stdout.split("\n\n"):
        said = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if said.get("Id") in (TIMER, SERVICE):
            units[said["Id"]] = said
    return units if TIMER in units else None


def launchd(read: Read) -> dict[str, dict[str, str]] | None:
    """What launchd says of jbus's agent, as systemd would say it of the timer and the service,
    or None where launchd did not answer. A loaded agent is an active timer, and a running one
    a service at work. Its last exit code is the service's result."""
    label = agents.label(TIMER)
    try:
        asked = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if asked.returncode in agents.NOT_LOADED:
        return {TIMER: {"Id": label, "ActiveState": "inactive"}, SERVICE: {"Id": label}}
    if asked.returncode:
        return None
    said = agents.parse_print(asked.stdout)
    running = said.get("state") == "running"
    code = said.get("last exit code", "")
    result = "success" if code == "0" else "exit-code" if code.isdigit() else ""
    timer = {"Id": label, "ActiveState": "active", "SubState": "running" if running else "waiting"}
    service = {"Id": label, "ActiveState": "activating" if running else "inactive"}
    return {
        TIMER: timer | {"UnitFileState": "loaded"},
        SERVICE: service | {"Result": result, "ExecMainStatus": code},
    }


def pulse(read: Read) -> dict[str, Any]:
    """What systemd, `pass.json` and `status.json` say, and whether systemd `answered`."""
    sources, name, now = read.sources, read.name, read.now
    record = read.record
    status = _table(sources.state_dir / "status.json") or {}
    manager = agents.manager()
    units = read.machine(launchd if manager == "launchd" else systemd)
    timer, service = (units or {}).get(TIMER, {}), (units or {}).get(SERVICE, {})
    started, ended = when(record.get("started")), when(record.get("ended"))
    last = ended or when(status.get("last_pass"), sources.user)
    quiet = last is None or (now - datetime.fromisoformat(last)).total_seconds() > QUIET
    down = units is not None and timer.get("ActiveState") != "active"
    stopped = down or (quiet and service.get("ActiveState") != "activating")
    mine = status.get("projects", {}).get(name) if isinstance(status.get("projects"), dict) else {}
    mine = mine if isinstance(mine, dict) else {}
    streaks = status.get("streaks") if isinstance(status.get("streaks"), dict) else {}
    homes = status.get("homes_off_bus") if isinstance(status.get("homes_off_bus"), list) else []
    scratch = status.get("scratch") if isinstance(status.get("scratch"), dict) else {}
    said = f"{manager} did not answer"
    if units is not None:
        said = (
            f"{timer.get('Id', TIMER)} {text(timer.get('ActiveState'), 60)} "
            f"({text(timer.get('SubState'), 60)}), "
            f"{service.get('Id', SERVICE)} {text(service.get('Result'), 60)}, "
            f"exit {text(service.get('ExecMainStatus'), 60)}"
        )
    return {
        "stopped": stopped,
        "why": "the timer is not active" if down else f"no pass in the last {QUIET} s" * stopped,
        "quiet": QUIET,
        "last_end": last,
        "said": said,
        "manager": manager,
        "answered": units is not None,
        "pass": {
            "started": started,
            "ended": ended,
            "seconds": record.get("seconds")
            if isinstance(record.get("seconds"), int | float)
            else None,
            "running": bool(started and not ended),
        },
        "timer": {
            "active": text(timer.get("ActiveState"), 60),
            "sub": text(timer.get("SubState"), 60),
            "enabled": text(timer.get("UnitFileState"), 60),
            "last_trigger": text(timer.get("LastTriggerUSec"), 60),
        },
        "status": {
            "last_pass": when(status.get("last_pass"), sources.user),
            "token_expires": when(status.get("token_expires"), sources.user),
            "failed_wakes": count(mine.get("failed_wakes")),
            "last_error": text(mine.get("last_error")),
            "outbox": count(mine.get("outbox")),
            "top_level": _hook(mine.get("top_level")),
            "blocking": _hook(mine.get("blocking")),
            "sign_in": text(mine.get("sign_in")),
            "sweep": text(mine.get("sweep")),
            "streaks": {
                text(key, 60): count(one.get("count"))
                for key, one in streaks.items()
                if isinstance(one, dict)
            },
            "homes_off_bus": [text(home, 60) for home in homes if isinstance(home, str)],
            "scratch": [
                {"name": text(name, 60), "home_thread": text(one.get("home_thread"), 80)}
                for name, one in sorted(scratch.items())
                if isinstance(one, dict)
            ],
        },
    }


def _hook(one: Any) -> dict[str, Any] | None:
    """What the status file says of a webhook beside the project's own, or None where the
    project posts to no such webhook."""
    if not isinstance(one, dict):
        return None
    return {
        "failed_wakes": count(one.get("failed_wakes")),
        "last_error": text(one.get("last_error")),
        "outbox": count(one.get("outbox")),
    }


def _code(said: dict[str, Any]) -> dict[str, Any]:
    """Which code answers requests: when the server started, and whether a file it runs is newer
    on disk than that start. Where the server tried the code on disk and that code did not start,
    the answer also says why."""
    return {
        "started": when(said.get("started")),
        "stale": said.get("stale") is True,
        "error": text(said.get("error")),
    }


def _timer(read: Read) -> dict[str, Any]:
    return {"at": iso(read.now), "read": read.once(pulse)["answered"]}


def _status(read: Read) -> dict[str, Any]:
    path = read.sources.state_dir / "status.json"
    return {"at": _mtime(path), "read": _table(path) is not None, "path": path}


SOURCES = (
    Source(TIMER, "server", _timer, 10, machine=True),
    Source("status.json", "jbus", _status, 20, machine=True),
    PASS_FILE,
    kept(mainjson.NAME, lambda read: read.table(mainjson.NAME), 80),
)


def blind(read: Read) -> list[Spot]:
    """How many tasks the last pass could not confirm, because it could not ask a source."""
    tasks, unconfirmed = read.tasks, read.unconfirmed
    if not unconfirmed or not tasks:
        return []
    many = f"{len(tasks)} {'task is' if len(tasks) == 1 else 'tasks are'}"
    return [Spot(f"{many} {unconfirmed['line']}", 300)]


def build(read: Read) -> dict[str, Any]:
    main = mainjson.typed(read.table(mainjson.NAME)) or {}
    sha = text(main.get("main", ""), 40)
    said = {key: value for key, value in read.once(pulse).items() if key != "answered"}
    return {
        "jbus": said | {"code": _code(read.code)},
        "main": {"sha": sha if _SHA.fullmatch(sha) else "", "at": when(main.get("at"))},
    }
