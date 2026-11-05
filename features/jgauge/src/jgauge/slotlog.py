"""A log of every test slot taken and let go, and the report on a span of it.

`jgauge test-slot` appends one row when it takes a slot and one when it lets the slot go, in
both lanes and with or without `--thread`, to `jgauge/slots.jsonl` beside the lock files'
directory: `~/.local/state/jgauge/slots.jsonl`, and with `JGAUGE_LOCKS_DIR` set, as a test or a
sandbox sets it, the log moves with the locks. The holders file (`jgauge.holders`) keeps a run only
until jbus has woken its thread, and only a run with `--thread`, so it holds no history; this
log is the history.

A row is one JSON object:

- `at`, the time, ISO in UTC, and `event`, `take` or `release`;
- `id`, which pairs a take with its release, and `pid`, the `jgauge test-slot` process that
  holds the slot;
- `lane`, `full` or `short`, `slot`, the slot's number, and `slots`, the lane's size as the
  caller counted it, so a run with `--slots 5` shows as one;
- `thread`, the thread id or nothing, `command` and `cwd`, which name the caller;
- on a take, `waited`, the seconds the call waited for the slot;
- on a release, `code`, the command's exit code, and `hold`, the seconds the slot was held.

A row is one `write` with `O_APPEND`, under the lock on the log's directory that `jgauge sample`
also takes. Once the first row is over 30 days old, the writer keeps the last 29 days, as the
load log does.

The report pairs takes with releases into holds. A take with no release is held to the end of
the span while its pid lives, and is counted as lost otherwise: a holder killed outright leaves
no release, and its slot was free once it died. For each lane it prints the holds, the mean
occupancy (slot-seconds held in the span over the span), Little's law from the same holds (takes
per second times the mean hold), and the wait in the call at p50 and p90. Then, from jbus's
`slot-wake` events, it prints the mean occupancy over the time a thread of that lane waited for
a slot: with a waiter waiting every slot should be taken, so that share near 100% says the log
sees every holder, and a low one says some holder takes slots this log does not see.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import statistics
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jgauge import sample

KEEP_DAYS = 30
PRUNED_TO_DAYS = 29
WAKE = re.compile(r"^slot-wake: woke \S+, a (\w+) slot is free for `[^`]*`, after (\d+) min")


def path(locks: Path) -> Path:
    """The log of the slots whose lock files are in `locks`."""
    return locks.parent / "jgauge" / "slots.jsonl"


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="milliseconds")


def _prune(log: Path, now: float) -> None:
    since = now - PRUNED_TO_DAYS * sample.DAY
    part = log.with_name(f".{log.name}.part")
    with log.open() as old, part.open("w") as new:
        for line in old:
            try:
                at = datetime.fromisoformat(json.loads(line)["at"]).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            if at >= since:
                new.write(line)
        new.flush()
        os.fsync(new.fileno())
    part.replace(log)


def _append(log: Path, row: dict) -> None:
    """Append one row. A log that cannot be written stops no test: the slot is the point."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        folder = os.open(log.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        fcntl.flock(folder, fcntl.LOCK_EX)
        if log.exists():
            with log.open() as lines:
                first = lines.readline()
            try:
                oldest = datetime.fromisoformat(json.loads(first)["at"]).timestamp()
            except (ValueError, KeyError, TypeError):
                oldest = None
            now = datetime.now(UTC).timestamp()
            if oldest is not None and oldest < now - KEEP_DAYS * sample.DAY:
                _prune(log, now)
        written = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(written, (json.dumps(row) + "\n").encode())
        finally:
            os.close(written)
    except OSError:
        pass
    finally:
        os.close(folder)


@dataclass(frozen=True)
class Taken:
    """A slot taken, as its take row says, to pass to `release`."""

    log: Path
    at: datetime
    fields: dict


def take(
    log: Path, lane: str, slot: int, slots: int, thread: str, command: list[str], waited: float
) -> Taken:
    now = datetime.now(UTC)
    fields = {
        "id": secrets.token_hex(6),
        "pid": os.getpid(),
        "lane": lane,
        "slot": slot,
        "slots": slots,
        "thread": thread,
        "command": command,
        "cwd": os.getcwd(),
    }
    _append(log, {"at": _stamp(now), "event": "take", **fields, "waited": round(waited, 3)})
    return Taken(log, now, fields)


def release(taken: Taken, code: int) -> None:
    now = datetime.now(UTC)
    held = (now - taken.at).total_seconds()
    _append(
        taken.log,
        {
            "at": _stamp(now),
            "event": "release",
            **taken.fields,
            "code": code,
            "hold": round(held, 3),
        },
    )


@dataclass(frozen=True)
class Hold:
    lane: str
    slots: int
    start: float
    end: float | None
    pid: int
    waited: float


def _rows(log: Path) -> Iterator[dict]:
    try:
        lines = log.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        try:
            row = json.loads(line)
            row["at"] = datetime.fromisoformat(row["at"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        yield row


def holds(log: Path) -> list[Hold]:
    """Every take in the log with the time of its release, or None for a take with none."""
    taken: dict[str, dict] = {}
    ended: dict[str, float] = {}
    for row in _rows(log):
        if row.get("event") == "take":
            taken[row["id"]] = row
        elif row.get("event") == "release":
            ended[row["id"]] = row["at"]
    return [
        Hold(
            row["lane"],
            int(row.get("slots") or 0),
            row["at"],
            ended.get(key),
            int(row.get("pid") or 0),
            float(row.get("waited") or 0),
        )
        for key, row in taken.items()
    ]


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _held(spans: list[tuple[float, float]], start: float, end: float) -> float:
    return sum(max(0.0, min(b, end) - max(a, start)) for a, b in spans)


def _quantile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def _waits(start: float, end: float) -> dict[str, list[tuple[float, float]]]:
    """The spans in which a thread waited for a slot of each lane, from jbus's `slot-wake`
    events: each ends at its wake and began its minutes before."""
    found: dict[str, list[tuple[float, float]]] = {}
    for events in sorted(sample.jbus_state().glob("*/events.jsonl")):
        for row in _rows(events):
            said = WAKE.match(str(row.get("line") or ""))
            if row.get("event") != "slot-wake" or not said:
                continue
            woke = row["at"]
            began = woke - 60 * int(said[2])
            if woke > start and began < end and woke > began:
                found.setdefault(said[1], []).append((max(began, start), min(woke, end)))
    return found


def _union(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def report(log: Path, start: float | None, until: float | None, now: float) -> list[str]:
    """The slot section of `jgauge sample --report`, and nothing when there is no log."""
    if not log.exists():
        return []
    every = holds(log)
    if not every:
        return [f"test slots: no holds in {log}"]
    start = min(one.start for one in every) if start is None else start
    end = now if until is None else min(until, now)
    if end <= start:
        return [f"test slots: the span is empty in {log}"]
    span = end - start
    lines = [
        f"test slots, from {log}, {datetime.fromtimestamp(start):%Y-%m-%d %H:%M:%S}"
        f" to {datetime.fromtimestamp(end):%Y-%m-%d %H:%M:%S} ({span / 3600:.2f} h):"
    ]
    waited_for = _waits(start, end)
    for lane in ("full", "short"):
        mine = [one for one in every if one.lane == lane]
        alive = [one for one in mine if one.end is None and _alive(one.pid)]
        spans = [(one.start, one.end) for one in mine if one.end is not None]
        spans += [(one.start, end) for one in alive]
        inside = [one for one in mine if start <= one.start < end]
        lost = sum(one.end is None and one not in alive for one in inside)
        held = _held(spans, start, end)
        size = max((one.slots for one in inside), default=0) or max(
            (one.slots for one in mine), default=0
        )
        done = [one.end - one.start for one in inside if one.end is not None]
        little = len(inside) / span * statistics.fmean(done) if done else 0.0
        waits = [one.waited for one in inside]
        wait = (
            f"wait in the call p50 {_quantile(waits, 0.5):.1f} s, p90 {_quantile(waits, 0.9):.1f} s"
            if waits
            else "no wait"
        )
        lines.append(
            f"  {lane}: {len(inside)} holds, {lost} lost; mean occupancy"
            f" {held / span:.3f} of {size} slots; Little's law (takes/s x mean hold)"
            f" {little:.3f}; {wait}"
        )
        waiting = _union(waited_for.get(lane, []))
        if waiting:
            length = sum(b - a for a, b in waiting)
            occupied = sum(_held(spans, a, b) for a, b in waiting) / length
            share = f" ({100 * occupied / size:.0f}% of {size})" if size else ""
            lines.append(
                f"  {lane}, while a thread waited for a slot ({length / 3600:.2f} h, from"
                f" {len(waited_for[lane])} slot-wake events): mean occupancy"
                f" {occupied:.2f}{share}"
            )
    return lines
