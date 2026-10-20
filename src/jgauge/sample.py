"""A log of the machine's load, pressure and /tmp files, a row every 15 s from a user timer,
and a report of a span of it: how often the load was over room's line while CPU pressure was
low, the peaks against room's other lines, and the stalls jbus recorded in the span.

The log is one TSV file under a header of COLUMNS. A field that cannot be read (no
/proc/pressure/io, a kernel with no `full` line for cpu) is empty, never a crash. It holds 30
days at most: once its first row is older than that, the sampler writes it again with the last
29 days, so the file is rewritten about once a day and not on every sample. A log written
before the two /tmp columns is written again once, with those fields empty in its old rows.

The stalls are read from each project's `events.jsonl` under jbus's state directory: a
`stall`, a `slot-wake` (a thread that waited for a test slot, and how many minutes), and a
`gate` that says a row had no room for its passes."""

from __future__ import annotations

import datetime
import fcntl
import json
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
BEFORE_TMP = COLUMNS
COLUMNS = (*BEFORE_TMP, "tmp_files", "tmp_used")
EVERY_SECONDS = 15
PRESSURE_LINE = 10.0
DAY = 86400
KEEP_DAYS = 30
PRUNED_TO_DAYS = 29
STALL_MINUTES = 5
ROOM = Path(__file__).with_name("room.sh")
ROOM_LINES = ("LOAD", "CPU", "MEMORY", "PRESSURE", "CUSHION", "SLOTS")


def log_path() -> Path:
    named = os.environ.get("JGAUGE_LOAD_LOG")
    return Path(named) if named else Path.home() / ".local" / "state" / "jgauge" / "load.tsv"


def proc() -> Path:
    return Path(os.environ.get("PROC") or "/proc")


def tmpfs() -> Path:
    """The filesystem whose file slots are counted, room.sh's `TMPFS`."""
    return Path(os.environ.get("TMPFS") or "/tmp")


def jbus_state() -> Path:
    named = os.environ.get("JBUS_STATE_DIR")
    return Path(named) if named else Path.home() / ".local" / "state" / "jbus"


def room_line(name: str) -> int:
    """One of room's lines, `<name>=` in room.sh, the one copy: `LOAD` is a percent of the
    cores, `CPU` and `PRESSURE` a share of time, `MEMORY` GB, `CUSHION` and `SLOTS` percents."""
    found = re.search(rf"^\s*{name}=(\d+)$", ROOM.read_text(), re.MULTILINE)
    if not found:
        raise SystemExit(f"jgauge: {ROOM} has no {name}= line to read room's line from")
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
    try:
        files = os.statvfs(tmpfs())
    except OSError:
        pass
    else:
        if files.f_files:
            fields |= {
                "tmp_files": str(files.f_files),
                "tmp_used": str(files.f_files - files.f_ffree),
            }
    return [fields.get(name, "") for name in COLUMNS]


def _first_time(log: Path) -> int | None:
    with log.open() as lines:
        next(lines, None)
        first = next(lines, "").split("\t", 1)[0]
    return int(first) if first.isdecimal() else None


def _widen(log: Path) -> None:
    """Write a log of the columns before /tmp's again under today's header, its old rows with
    the two /tmp fields empty."""
    part = log.with_name(f".{log.name}.part")
    with log.open() as old, part.open("w") as new:
        next(old)
        new.write("\t".join(COLUMNS) + "\n")
        for line in old:
            new.write(line.rstrip("\n") + "\t" * (len(COLUMNS) - len(BEFORE_TMP)) + "\n")
        new.flush()
        os.fsync(new.fileno())
    part.replace(log)


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
        if found == "\t".join(BEFORE_TMP) + "\n":
            _widen(log)
            found = header
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


def report(
    log: Path, start: int | None, pressure_line: float, until: int | None = None
) -> list[str]:
    at = {name: n for n, name in enumerate(COLUMNS)}
    rows = []
    if log.exists():
        with log.open() as lines:
            next(lines, None)
            for line in lines:
                fields = line.rstrip("\n").split("\t")
                if len(fields) == len(BEFORE_TMP):
                    fields += [""] * (len(COLUMNS) - len(BEFORE_TMP))
                if len(fields) == len(COLUMNS) and fields[0].isdecimal():
                    if (start is None or int(fields[0]) >= start) and (
                        until is None or int(fields[0]) < until
                    ):
                        rows.append(fields)
    if not rows:
        said = [f"rows: 0 in {log}"]
        return said + ([_stalls(start, until)] if start is not None and until is not None else [])
    times = [int(fields[0]) for fields in rows]
    first, last = min(times), max(times)
    shown = [
        datetime.datetime.fromtimestamp(one).strftime("%Y-%m-%d %H:%M:%S") for one in (first, last)
    ]
    line = room_line("LOAD")
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
        *_peaks(rows, at),
        _stalls(min(times), max(times) + EVERY_SECONDS),
    ]


def _peaks(rows: list[list[str]], at: dict[str, int]) -> list[str]:
    """The highest load, CPU pressure, memory pressure and /tmp use of the rows, and how many
    rows were at or over room's line for each."""
    lines = []
    for column, name, room in (
        ("cpu_some_avg60", "CPU pressure (some avg60)", "CPU"),
        ("memory_some_avg60", "memory pressure (some avg60)", "PRESSURE"),
    ):
        read = [n for fields in rows if (n := _number(fields[at[column]])) is not None]
        line = room_line(room)
        over = sum(n >= line for n in read)
        top = f"{max(read):g}" if read else "-"
        lines.append(
            f"{name}: at most {top}; at or over room's line of {line}:"
            f" {over} of {len(read)} rows ({_share(over, len(read))})"
        )
    loads = [
        (load, cores)
        for fields in rows
        if (load := _number(fields[at["load1"]])) is not None
        and (cores := _number(fields[at["cores"]]))
    ]
    if loads:
        load, cores = max(loads)
        lines.append(
            f"1-minute load: at most {load:g}, {100 * load / cores:.0f}% of {cores:g} cores"
        )
    used = [
        (int(fields[at["tmp_used"]]), int(fields[at["tmp_files"]]))
        for fields in rows
        if fields[at["tmp_used"]].isdecimal() and fields[at["tmp_files"]].isdecimal()
    ]
    line = room_line("SLOTS")
    if used:
        most, files = max(used)
        over = sum(taken * 100 > total * line for taken, total in used)
        lines.append(
            f"/tmp files: at most {most} of {files} ({_share(most, files)}); over room's line of"
            f" {line}%: {over} of {len(used)} rows"
        )
    else:
        lines.append("/tmp files: no row has them")
    return lines


def _stalls(start: int, until: int) -> str:
    """What jbus recorded in the span as a thread or a row held up: its `stall` events, the
    threads woken from a wait for a test slot and how many waited over STALL_MINUTES, and the
    rows gated for no room."""
    stalls = waits = timed = long = longest = rooms = 0
    files = sorted(jbus_state().glob("*/events.jsonl"))
    for path in files:
        for line in _read(path).splitlines():
            try:
                event = json.loads(line)
                moment = datetime.datetime.fromisoformat(event["at"]).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            if not start <= moment < until:
                continue
            said = str(event.get("line") or "")
            if event.get("event") == "stall":
                stalls += 1
            elif event.get("event") == "slot-wake":
                waits += 1
                found = re.search(r", after (\d+) min$", said)
                if found:
                    timed += 1
                    long += int(found[1]) > STALL_MINUTES
                    longest = max(longest, int(found[1]))
            elif event.get("event") == "gate" and ": no room for " in said:
                rooms += 1
    if not files:
        return f"jbus events: none read, {jbus_state()} has no events.jsonl"
    return (
        f"jbus events in {len(files)} projects: {stalls} stalls, {waits} threads woken from a"
        f" wait for a test slot (of the {timed} that say how long, {long} waited over"
        f" {STALL_MINUTES} min, the longest {longest} min), {rooms} rows gated for no room"
    )
