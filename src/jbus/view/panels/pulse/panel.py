"""Is the bus alive: the timer and the service as systemd has them, the last pass, the
status file, and which code of the view answers.

jbus has stopped when the timer is not active, or when the last pass ended more than `QUIET`
seconds ago and systemd does not say one is running now. A pass that starts and dies each
minute has stopped too: a start is no end.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from typing import Any

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
        "pass": {"started": None, "ended": None, "seconds": None, "running": None},
        "timer": {"active": None, "sub": None, "enabled": None, "last_trigger": None},
        "status": {
            "last_pass": None,
            "token_expires": None,
            "failed_wakes": None,
            "last_error": None,
            "outbox": None,
            "top_level": {"failed_wakes": None, "last_error": None, "outbox": None},
            "sign_in": None,
            "sweep": None,
            "streaks": {ANY: None},
            "homes_off_bus": [None],
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
    """What systemd says of the timer and the service, or None where it did not answer. It is
    the machine's, so one answer of the server asks it once (`Read.machine`)."""
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


def pulse(read: Read) -> dict[str, Any]:
    """What systemd, `pass.json` and `status.json` say, and whether systemd `answered`."""
    sources, name, now = read.sources, read.name, read.now
    record = read.record
    status = _table(sources.state_dir / "status.json") or {}
    units = read.machine(systemd)
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
    top = mine.get("top_level")
    said = "systemd did not answer"
    if units is not None:
        said = (
            f"{TIMER} {text(timer.get('ActiveState'), 60)} ({text(timer.get('SubState'), 60)}), "
            f"{SERVICE} {text(service.get('Result'), 60)}, "
            f"exit {text(service.get('ExecMainStatus'), 60)}"
        )
    return {
        "stopped": stopped,
        "why": "the timer is not active" if down else f"no pass in the last {QUIET} s" * stopped,
        "quiet": QUIET,
        "last_end": last,
        "said": said,
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
            "top_level": {
                "failed_wakes": count(top.get("failed_wakes")),
                "last_error": text(top.get("last_error")),
                "outbox": count(top.get("outbox")),
            }
            if isinstance(top, dict)
            else None,
            "sign_in": text(mine.get("sign_in")),
            "sweep": text(mine.get("sweep")),
            "streaks": {
                text(key, 60): count(one.get("count"))
                for key, one in streaks.items()
                if isinstance(one, dict)
            },
            "homes_off_bus": [text(home, 60) for home in homes if isinstance(home, str)],
        },
    }


def _code(said: dict[str, Any]) -> dict[str, Any]:
    """Which code answers: when the server started, whether a file it runs is newer on disk
    than that, and why the code on disk did not start where it was tried and did not."""
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
    kept("main.json", lambda read: read.table("main.json"), 80),
)


def blind(read: Read) -> list[Spot]:
    """While the last pass could not ask a source, how many tasks are not confirmed."""
    tasks, unconfirmed = read.tasks, read.unconfirmed
    if not unconfirmed or not tasks:
        return []
    many = f"{len(tasks)} {'task is' if len(tasks) == 1 else 'tasks are'}"
    return [Spot(f"{many} {unconfirmed['line']}", 300)]


def build(read: Read) -> dict[str, Any]:
    main = read.table("main.json")
    sha = text(main.get("main") if main else "", 40)
    said = {key: value for key, value in read.once(pulse).items() if key != "answered"}
    return {
        "jbus": said | {"code": _code(read.code)},
        "main": {"sha": sha if _SHA.fullmatch(sha) else "", "at": when((main or {}).get("at"))},
    }
