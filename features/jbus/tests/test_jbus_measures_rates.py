"""A measure that counts over a span reads a rate its baseline is a rate of: a count of the week so
far is read a day, so Monday and Saturday are judged alike, and hours-unowned is read per 72 h of
the last 72 h.

The tests build a store with the real `telemetry.connect` and read the measures through
`measures.read`, as `jbus scorecard` does.
"""

from datetime import UTC, datetime, timedelta

import pytest

from jbus import telemetry
from jbus.telemetry import measures
from test_jbus_scorecard import USER, measure, stamp

TUESDAY = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)
"""Midnight of Tuesday in New York: the week so far, from Sunday's midnight, is 2 days."""


@pytest.fixture
def store(tmp_path):
    connection = telemetry.connect(tmp_path / telemetry.FILE)
    yield connection
    connection.close()


def typed(store, surface: str, count: int) -> None:
    for i in range(count):
        at = TUESDAY - timedelta(hours=1, minutes=i)
        store.execute(
            "insert into messages (project, key, role, at, created_by, kind, day, surface)"
            " values ('jstack', ?, 'user', ?, 'user', 'text', '2026-11-09', ?)",
            (f"{surface}{i}", stamp(at), surface),
        )


def capped(store, minutes: int) -> None:
    """Reads 5 minutes apart with one account capped, each holding its 5 minutes."""
    reads = minutes // 5
    for i in range(reads):
        at = TUESDAY - timedelta(hours=20) + timedelta(minutes=5 * i)
        store.execute(
            "insert into capped_reads (project, key, at, reader, instances, capped, day)"
            " values ('', ?, ?, 'pass', 2, 1, '2026-11-09')",
            (f"c{i}", stamp(at)),
        )
    last = TUESDAY - timedelta(hours=20) + timedelta(minutes=5 * reads)
    store.execute("insert into builds (at) values (?)", (stamp(last),))


@pytest.mark.parametrize(
    ("name", "fill", "count", "weekly", "line", "state"),
    [
        ("merge-asks", lambda store: typed(store, "merge", 12), 12, 40, 48, "watch"),
        ("approval-reasks", lambda store: typed(store, "approval", 42), 42, 143, 171.6, "watch"),
        ("capped-any-minutes", lambda store: capped(store, 1700), 1700, 5585, 5585, "bad"),
    ],
)
def test_a_weekly_count_is_read_as_a_days_rate(store, name, fill, count, weekly, line, state):
    """Over the 2 days of a week so far, a count is half of itself a day, against a seventh of the
    weekly baseline and of its line: 12 merge asks are 6 a day, over the 5.7 a day of 40 a week,
    where a sum of the week so far would read 12 under 40 as fine."""
    each = measure(name)
    fill(store)
    reading = measures.read(store, each, "jstack", TUESDAY, USER)
    assert reading.value == pytest.approx(count / 2)
    assert reading.baseline == pytest.approx(weekly / 7)
    assert isinstance(each.kind, measures.Limit)
    assert each.kind.at == pytest.approx(line / 7)
    assert reading.state == state
    assert "a day" in each.unit


def moves(store, slug: str, merged: datetime, *spells: tuple[str, float]) -> None:
    """The row's transitions, each status held its hours in turn, the last ending at `merged`."""
    at = merged - timedelta(hours=sum(hours for _, hours in spells))
    before = "queued"
    for i, (status, hours) in enumerate(spells):
        store.execute(
            "insert into transitions (project, key, at, slug, from_status, to_status, day)"
            " values ('jstack', ?, ?, ?, ?, ?, '2026-11-09')",
            (f"{slug}.{i}", stamp(at), slug, before, status),
        )
        at, before = at + timedelta(hours=hours), status
    store.execute(
        "insert into transitions (project, key, at, slug, from_status, to_status, day)"
        " values ('jstack', ?, ?, ?, 'pr', 'merged', '2026-11-09')",
        (f"{slug}.end", stamp(merged), slug),
    )
    store.execute(
        "insert into merged (project, key, slug, merged_at, day) values ('jstack', ?, ?, ?, ?)",
        (slug, slug, stamp(merged), merged.date().isoformat()),
    )


def test_a_row_left_for_its_review_is_not_unowned(store):
    """A row that waits 2 h, works, is left 1 h for the review before its pull request and then
    opens it has 2 h unowned; one left 3 h for its home to resume it has those 3. A row merged 60 h
    ago, before the week began, still counts its 1 h waiting in the last 72 h; one merged 73 h ago
    does not."""
    moves(
        store,
        "reviewed",
        TUESDAY - timedelta(hours=2),
        ("waiting", 2),
        ("launched", 1),
        ("left", 1),
        ("pr", 1),
    )
    moves(
        store,
        "resumed",
        TUESDAY - timedelta(hours=3),
        ("launched", 1),
        ("left", 3),
        ("launched", 1),
        ("pr", 1),
    )
    moves(
        store, "sunday", TUESDAY - timedelta(hours=60), ("waiting", 1), ("launched", 1), ("pr", 1)
    )
    moves(store, "old", TUESDAY - timedelta(hours=73), ("waiting", 5), ("pr", 1))
    each = measure("hours-unowned")
    reading = measures.read(store, each, "jstack", TUESDAY, USER)
    assert (reading.value, reading.n) == (pytest.approx(6.0), 3)
    assert each.window == "72h"
