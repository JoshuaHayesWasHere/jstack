"""The slot log's writer and report, in this process: the log keeps 30 days, a log that cannot
be written stops no run, and the report reads only what is a row. `test_slot.py` drives
`jgauge test-slot` itself and reads its rows back."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from jgauge import slotlog

NOON = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def rows(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_the_log_keeps_the_last_29_days_once_its_first_row_is_over_30_days_old(tmp_path):
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()
    now = datetime.now(UTC)
    old = {"at": (now - timedelta(days=31)).isoformat(), "event": "take", "id": "old"}
    kept = {"at": (now - timedelta(days=20)).isoformat(), "event": "take", "id": "kept"}
    log.write_text("".join(json.dumps(one) + "\n" for one in (old, kept)) + "not a row\n")

    taken = slotlog.take(log, "full", 3, 4, "mcp:t", ["make", "check"], 1.23456)
    slotlog.release(taken, 2)

    *before, take, release = rows(log)
    assert before == [kept]
    assert (take["event"], take["lane"], take["slot"], take["slots"]) == ("take", "full", 3, 4)
    assert (take["thread"], take["command"], take["waited"]) == ("mcp:t", ["make", "check"], 1.235)
    assert (take["pid"], take["cwd"]) == (os.getpid(), os.getcwd())
    shared = {key: value for key, value in take.items() if key not in ("at", "event", "waited")}
    assert release == {
        **shared,
        "at": release["at"],
        "event": "release",
        "code": 2,
        "hold": release["hold"],
    }
    assert 0 <= release["hold"] < 5


@pytest.mark.parametrize("blocked", ["parent is a file", "log is a directory"])
def test_a_log_that_cannot_be_written_stops_nothing(tmp_path, blocked):
    log = slotlog.path(tmp_path / "locks")
    if blocked == "parent is a file":
        log.parent.write_text("")
    else:
        log.mkdir(parents=True)
    slotlog.release(slotlog.take(log, "short", 1, 3, "", ["true"], 0), 0)


def stamp(minute):
    return (NOON + timedelta(minutes=minute)).isoformat()


def test_the_report_reads_only_rows_and_merges_waits_that_overlap(tmp_path, monkeypatch):
    """A take with no release whose holder lives, pid 1 here, is held to the span's end. Two
    waits that overlap, 10:01 to 10:05 and 10:03 to 10:08, are 7 minutes of waiting, and a lane
    with no holds prints nothing."""
    monkeypatch.setenv("JBUS_STATE_DIR", str(tmp_path / "jbus"))
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()
    assert slotlog.report(log, None, None, NOON.timestamp()) == []
    log.write_text("not a row\n")
    assert slotlog.report(log, None, None, NOON.timestamp()) == [f"test slots: no holds in {log}"]
    take = {"event": "take", "id": "a", "pid": 1, "lane": "full", "slot": 1, "slots": 2}
    take |= {"thread": "", "command": ["true"], "cwd": "/", "waited": 0}
    log.write_text(json.dumps({"at": stamp(0), **take}) + "\nnot a row\n")
    events = tmp_path / "jbus" / "jstack" / "events.jsonl"
    events.parent.mkdir(parents=True)
    woke = "slot-wake: woke mcp:{}, a full slot is free for `make`, after {} min"
    events.write_text(
        "\n".join(
            json.dumps(one)
            for one in (
                {"at": stamp(5), "event": "slot-wake", "line": woke.format("a", 4)},
                {"at": stamp(8), "event": "slot-wake", "line": woke.format("b", 5)},
                {"at": stamp(6), "event": "stall", "line": "stall: x"},
            )
        )
    )
    start, until = NOON.timestamp(), (NOON + timedelta(minutes=10)).timestamp()

    assert slotlog.report(log, until, None, start) == [f"test slots: the span is empty in {log}"]
    assert slotlog.report(log, start, until, until + 60)[1:] == [
        "  full: 1 holds, 0 lost; mean occupancy 1.000 of 2 slots;"
        " Little's law (takes/s x mean hold) 0.000; wait in the call p50 0.0 s, p90 0.0 s",
        "  full, while a thread waited for a slot (0.12 h, from 2 slot-wake events):"
        " mean occupancy 1.00 (50% of 2)",
    ]
