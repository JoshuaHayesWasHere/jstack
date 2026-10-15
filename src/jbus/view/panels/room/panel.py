"""The machine and the plan: its load, memory, pressure, the file slots of `/tmp` and the
plan's limits, and the one answer `jgauge room` gives of them.

The limits file is written by a session's status line, so it is old whenever no session ran:
it says its age, and is no fault of jbus. A limit in it whose reset time has passed is from
a window that is over: its use is not known, and is never given as a number.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import jsettings
from jbus.view.clean import ANY
from jbus.view.state import Read, Source, Sources, Spot, _lines, _mtime, iso, text, when

FIRST = True
ROOM = Path(__file__).resolve().parents[4] / "jgauge" / "room.sh"
LIMITS = {"five_hour": "five-hour", "seven_day": "seven-day"}
SHAPE = {
    "room": {
        "answer": None,
        "why": None,
        "cores": None,
        "load": [None],
        "memory_gb": None,
        "pressure": None,
        "tmp": {"total": None, "used": None},
        "plan": {ANY: {"used": None, "resets": None, "written": None, "say": None}},
        "limits": {ANY: None},
    }
}
NOT_KEPT = (
    Spot(
        "the plan's use since the limits file was last written is not known: "
        "only a session's status line writes it",
        540,
    ),
)


def room_limits() -> dict[str, int]:
    """The limits `jgauge room` holds a launch to, read from its script."""
    script = ROOM.read_text()
    names = {
        "load": "LOAD",
        "memory": "MEMORY",
        "pressure": "PRESSURE",
        "slots": "SLOTS",
        "plan": "CUSHION",
    }
    return {
        key: int(re.search(rf"^\s*{name}=(\d+)$", script, re.M)[1]) for key, name in names.items()
    }


def limits_path() -> Path:
    """Where the plan's limits are written, as `jgauge room` finds it."""
    named = os.environ.get("LIMITS")
    below = re.search(r"LIMITS=\$\{LIMITS:-\$HOME/([^}]+)\}", ROOM.read_text())[1]
    return Path(named) if named else Path.home() / below


def _number_in(path: Path, pattern: str) -> float | None:
    found = re.search(pattern, "\n".join(_lines(path) or []), re.M)
    return float(found[1]) if found else None


def _plan(limits: Path, now: datetime, user: jsettings.Settings) -> dict[str, Any]:
    """The plan's limits as the limits file has them, each with when the file was written.

    A limit whose reset time has passed is of a window that is over: its `used` is None,
    and it says when the file was last written."""
    written = _mtime(limits)
    plan: dict[str, Any] = {}
    for line in _lines(limits) or []:
        words = line.split()
        if len(words) == 3 and words[0] in LIMITS:
            try:
                used, resets = float(words[1]), when(int(words[2]))
            except ValueError:
                continue
            over = resets is None or resets <= iso(now)
            last = user.stamp(datetime.fromisoformat(written)) if written else "at no known time"
            plan[words[0]] = {
                "used": None if over else used,
                "resets": resets,
                "written": written,
                "say": f"unknown, last written {last}" if over else "",
            }
    return plan


def _room(sources: Sources, now: datetime) -> dict[str, Any]:
    """The machine and the plan, and the one answer `jgauge room` gives of them."""
    limits = sources.limits or limits_path()
    load = (_lines(sources.proc / "loadavg") or [""])[0].split()[:3]
    memory = _number_in(sources.proc / "meminfo", r"^MemAvailable:\s+(\d+)")
    plan = _plan(limits, now, sources.user)
    try:
        slots = os.statvfs(sources.tmp)
        tmp = {"total": slots.f_files, "used": slots.f_files - slots.f_ffree}
    except OSError:
        tmp = None
    env = os.environ | {"PROC": str(sources.proc), "LIMITS": str(limits), "TMPFS": str(sources.tmp)}
    try:
        asked = subprocess.run(
            ["sh", str(ROOM)], capture_output=True, text=True, timeout=5, env=env
        )
        answer, _, why = (asked.stdout.strip().splitlines() or [""])[-1].partition(": ")
    except (OSError, subprocess.SubprocessError):
        answer, why = "", ""
    known = answer in ("go", "wait")
    try:
        loads = [float(one) for one in load]
    except ValueError:
        loads = []
    return {
        "answer": answer if known else "unknown",
        "why": text(why) if known else "the room check did not run",
        "cores": os.cpu_count() or 0,
        "load": loads,
        "memory_gb": round(memory / 1048576, 1) if memory is not None else None,
        "pressure": _number_in(sources.proc / "pressure" / "memory", r"^some .*avg60=([0-9.]+)"),
        "tmp": tmp,
        "plan": plan,
        "limits": room_limits(),
    }


def room(read: Read) -> dict[str, Any]:
    return _room(read.sources, read.now)


def _past(read: Read) -> list[str]:
    """The limits of the plan whose window is over."""
    return [key for key, one in read.machine(room)["plan"].items() if one["used"] is None]


def _limits(read: Read) -> dict[str, Any]:
    limits = read.sources.limits or limits_path()
    return {
        "at": _mtime(limits),
        "read": _lines(limits) is not None,
        "path": limits,
        "old": bool(_past(read)),
    }


SOURCES = (
    Source("the machine", "server", lambda read: {"at": iso(read.now)}, 160, machine=True),
    Source("limits", "session", _limits, 170, machine=True),
)


def blind(read: Read) -> list[Spot]:
    """A room check that did not run, and each limit of the plan whose window is over."""
    plan = read.machine(room)["plan"]
    unknown = read.machine(room)["answer"] == "unknown"
    return [Spot("the room check did not run", 200, machine=True)] * unknown + [
        Spot(f"the plan's {LIMITS[key]} limit is {plan[key]['say']}", 210, machine=True)
        for key in _past(read)
    ]


def build(read: Read) -> dict[str, Any]:
    return {"room": read.machine(room)}
