"""`queue.derive` keeps each change of a row's reason to wait as one line of `waits.jsonl`, and a
pass that leaves the reason as it was adds none. A row that waits behind a row with no room on the
machine says so."""

import json

from jbus import queue
from test_jbus_queue import add, rows

STAMP, AT = "2026-11-09 16:00 ET", "2026-11-09T21:00:00+00:00"
ROOM = "waiting for room on the machine"


def lines(kitchen):
    path = kitchen.state / "waits.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def derive(kitchen, why, at=AT):
    queue.derive(kitchen.state, lambda row: {"why": why}, STAMP, at)


def test_a_changed_reason_is_one_line_each_time(kitchen):
    add(kitchen, "alpha", approve=False)
    derive(kitchen, "depends on beta")
    derive(kitchen, "", "2026-11-09T21:05:00+00:00")
    assert lines(kitchen) == [
        {"slug": "alpha", "why": "depends on beta", "at": AT},
        {"slug": "alpha", "why": "", "at": "2026-11-09T21:05:00+00:00"},
    ]
    assert rows(kitchen)["alpha"]["why"] == ""


def test_a_reason_that_stays_adds_no_line(kitchen):
    add(kitchen, "alpha", approve=False)
    derive(kitchen, "depends on beta")
    derive(kitchen, "depends on beta", "2026-11-09T21:05:00+00:00")
    assert lines(kitchen) == [{"slug": "alpha", "why": "depends on beta", "at": AT}]


def test_the_pass_that_starts_the_log_writes_each_rows_reason_as_it_stands(kitchen):
    """A table kept before `waits.jsonl` was: `alpha` already waited, so its reason is in the log
    from the first pass, though the pass did not change it."""
    add(kitchen, "alpha", approve=False)
    derive(kitchen, "depends on beta")
    (kitchen.state / "waits.jsonl").unlink()
    derive(kitchen, "depends on beta", "2026-11-09T21:05:00+00:00")
    derive(kitchen, "depends on beta", "2026-11-09T21:10:00+00:00")
    assert lines(kitchen) == [
        {"slug": "alpha", "why": "depends on beta", "at": "2026-11-09T21:05:00+00:00"}
    ]


def test_each_row_behind_a_row_with_no_room_says_it_waits_for_room(kitchen):
    """The load is over the machine's limit, so `first` meets no room, and the three rows queued
    behind it are read only for their reason, which is the room too, and is kept in the log."""
    for priority, slug in enumerate(("first", "second", "third", "fourth"), 1):
        add(kitchen, slug, priority=priority)
    kitchen.machine(load="30.00")
    kitchen.poll()
    assert kitchen.t3.launches == []
    waiting = {slug: row["why"] for slug, row in rows(kitchen).items()}
    assert waiting == dict.fromkeys(("first", "second", "third", "fourth"), ROOM)
    assert {line["slug"]: line["why"] for line in lines(kitchen)} == waiting
