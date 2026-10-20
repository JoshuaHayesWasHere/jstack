"""A log of the machine's load and pressure, a row every 15 s from a user timer, and a report
of how often the load was over room's line while CPU pressure was low.

The log is one TSV file under a header of COLUMNS. A field that cannot be read (no
/proc/pressure/io, a kernel with no `full` line for cpu) is empty, never a crash. It holds 30
days at most: once its first row is older than that, the sampler writes it again with the last
29 days, so the file is rewritten about once a day and not on every sample."""

from __future__ import annotations

import datetime
import fcntl
import os
import re
import time
from pathlib import Path

RESOURCES = ("cpu", "memory", "io")
KINDS = ("some", "full")
WINDOWS = ("avg10", "avg60")
COLUMNS = (
    "time",
    "cores",
    "load1",
    "load5",
    "load15",
    *(f"{r}_{k}_{w}" for r in RESOURCES for k in KINDS for w in WINDOWS),
)
EVERY_SECONDS = 15
PRESSURE_LINE = 10.0
DAY = 86400
KEEP_DAYS = 30
PRUNED_TO_DAYS = 29
ROOM = Path(__file__).with_name("room.sh")


def log_path() -> Path:
    named = os.environ.get("JGAUGE_LOAD_LOG")
    return Path(named) if named else Path.home() / ".local" / "state" / "jgauge" / "load.tsv"


def proc() -> Path:
    return Path(os.environ.get("PROC") or "/proc")


def load_line() -> int:
    """Room's load line, `LOAD=` in room.sh, the one copy: a percent of the cores."""
    found = re.search(r"^\s*LOAD=(\d+)$", ROOM.read_text(), re.MULTILINE)
    if not found:
        raise SystemExit(f"jgauge: {ROOM} has no LOAD= line to read room's load line from")
    return int(found[1])


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _pressure(text: str) -> dict[str, str]:
    """`some avg10=1.00 avg60=2.00 ...` lines as {"some_avg10": "1.00", ...}."""
    found = {}
    for line in text.splitlines():
        kind, *fields = line.split() or [""]
        for field in fields:
            window, _, value = field.partition("=")
            found[f"{kind}_{window}"] = value
    return found


def row(now: int) -> list[str]:
    root = proc()
    load = _read(root / "loadavg").split()[:3]
    fields = {
        "time": str(now),
        "cores": str(len(os.sched_getaffinity(0))),
        **dict(zip(("load1", "load5", "load15"), load, strict=False)),
    }
    for resource in RESOURCES:
        read = _pressure(_read(root / "pressure" / resource))
        fields |= {f"{resource}_{key}": value for key, value in read.items()}
    return [fields.get(name, "") for name in COLUMNS]


def _first_time(log: Path) -> int | None:
    with log.open() as lines:
        next(lines, None)
        first = next(lines, "").split("\t", 1)[0]
    return int(first) if first.isdecimal() else None


def _prune(log: Path, now: int) -> None:
    """Write the log again with the rows of the last PRUNED_TO_DAYS, by time and not by place,
    so a clock that went back loses no row it should keep."""
    since = now - PRUNED_TO_DAYS * DAY
    part = log.with_name(f".{log.name}.part")
    with log.open() as old, part.open("w") as new:
        new.write(next(old))
        for line in old:
            at = line.split("\t", 1)[0]
            if not at.isdecimal() or int(at) >= since:
                new.write(line)
        new.flush()
        os.fsync(new.fileno())
    part.replace(log)


def take(log: Path) -> None:
    """Append one row, under a lock on the log's directory, which a rename does not move."""
    log.parent.mkdir(parents=True, exist_ok=True)
    header = "\t".join(COLUMNS) + "\n"
    folder = os.open(log.parent, os.O_RDONLY)
    try:
        fcntl.flock(folder, fcntl.LOCK_EX)
        now = int(time.time())
        if not log.exists() or log.stat().st_size == 0:
            log.write_text(header)
        with log.open() as lines:
            found = lines.readline()
        if found != header:
            raise SystemExit(f"jgauge: {log} has other columns than a sample writes: {found!r}")
        first = _first_time(log)
        if first is not None and first < now - KEEP_DAYS * DAY:
            _prune(log, now)
        written = os.open(log, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(written, ("\t".join(row(now)) + "\n").encode())
        finally:
            os.close(written)
    finally:
        os.close(folder)


def since(asked: str) -> int:
    """A start for the report: seconds since the epoch, or an ISO date or time, local if it
    names no zone."""
    if asked.isdecimal():
        return int(asked)
    try:
        return int(datetime.datetime.fromisoformat(asked).timestamp())
    except ValueError as error:
        raise ValueError(
            f"{asked!r} is not a time: give seconds since the epoch or an ISO date"
        ) from error


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def report(log: Path, start: int | None, pressure_line: float) -> list[str]:
    at = {name: n for n, name in enumerate(COLUMNS)}
    rows = []
    if log.exists():
        with log.open() as lines:
            next(lines, None)
            for line in lines:
                fields = line.rstrip("\n").split("\t")
                if len(fields) == len(COLUMNS) and fields[0].isdecimal():
                    if start is None or int(fields[0]) >= start:
                        rows.append(fields)
    if not rows:
        return [f"rows: 0 in {log}"]
    times = [int(fields[0]) for fields in rows]
    first, last = min(times), max(times)
    shown = [
        datetime.datetime.fromtimestamp(one).strftime("%Y-%m-%d %H:%M:%S") for one in (first, last)
    ]
    line = load_line()
    read = over = low = 0
    for fields in rows:
        load = _number(fields[at["load1"]])
        cores = _number(fields[at["cores"]])
        cpu = _number(fields[at["cpu_some_avg60"]])
        if load is None or not cores or cpu is None:
            continue
        read += 1
        if int(load * 100 + 0.5) >= cores * line:
            over += 1
            low += cpu < pressure_line
    return [
        f"rows: {len(rows)}, from {shown[0]} to {shown[1]}"
        f" ({datetime.timedelta(seconds=last - first)});"
        f" a row every {EVERY_SECONDS} s would give {(last - first) // EVERY_SECONDS + 1}",
        f"read: {read} rows have the 1-minute load and CPU pressure (some avg60),"
        f" and {len(rows) - read} of the {len(rows)} do not",
        f"load at or over room's line, {line}% of the cores:"
        f" {over} of {read} rows ({_share(over, read)})",
        f"and CPU pressure under {pressure_line:g}: {low} of {read} rows ({_share(low, read)}),"
        f" {low} of the {over} over the line ({_share(low, over)})",
    ]
