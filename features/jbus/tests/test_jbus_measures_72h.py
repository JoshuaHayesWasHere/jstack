"""The measures whose baseline is a count per 72 h read the last 72 h, which no Sunday resets.

`done-no-merge`, `backward-moves` and `duplicate-reviews` were each judged against a count read
over a rolling 72 h, so each reads the same span: a row 71 h old counts on any day of the week,
and one 73 h old does not. The store is the real `telemetry.connect`, and each row is written to
the tables jbus fills, so it reaches the measure through the views it reads, as
`jbus scorecard` reads it."""

from datetime import UTC, datetime, timedelta

import pytest

from jbus import telemetry
from jbus.telemetry import measures
from test_jbus_scorecard import USER, calls, measure, stamp

MONDAY = datetime(2026, 11, 9, 21, 20, tzinfo=UTC)
"""16:20 on a Monday in New York, 40 h 20 m after the week began at Sunday's midnight."""
SATURDAY = datetime(2026, 11, 14, 21, 20, tzinfo=UTC)
"""16:20 on a Saturday in New York, 6 days and 16 h 20 m after the week began."""


@pytest.fixture
def store(tmp_path):
    connection = telemetry.connect(tmp_path / telemetry.FILE)
    yield connection
    connection.close()


def ended_with_no_merge(store, slug: str, at: datetime) -> None:
    """A crew row that ended dropped, its one crew call at `at`."""
    store.execute(
        "insert into queue (project, key, slug, status) values ('jstack', ?, ?, 'done')",
        (slug, slug),
    )
    store.execute(
        "insert into brief_versions (project, key, at, slug, pull, outcome)"
        " values ('jstack', ?, ?, ?, 'open', 'dropped')",
        (slug, stamp(at - timedelta(days=5)), slug),
    )
    calls(store, "jstack", "crew", slug, f"crew-{slug}", f"mcp:crew-{slug}", (at, 1_000_000))


def moved_back(store, slug: str, at: datetime) -> None:
    """A row moved out of `merged` at `at`."""
    store.execute(
        "insert into transitions (project, key, at, slug, from_status, to_status, day)"
        " values ('jstack', ?, ?, ?, 'merged', 'launched', ?)",
        (slug, stamp(at), slug, at.date().isoformat()),
    )


def reviewed_twice(store, slug: str, at: datetime) -> None:
    """Two reviewers of seat 1 at one head, the second, the repeat, launched at `at`."""
    for n, launched in enumerate((at - timedelta(minutes=1), at)):
        thread = f"mcp:review-{slug}-{n}"
        calls(store, "jstack", "reviewer", slug, f"review-{slug}-{n}", thread, (launched, 10))
        store.execute(
            "insert into review_heads (project, key, at, slug, thread, head, kind, number)"
            " values ('jstack', ?, ?, ?, ?, ?, 'first', 1)",
            (thread, stamp(launched), slug, thread, "a" * 40),
        )


SEEDS = {
    "done-no-merge": ended_with_no_merge,
    "backward-moves": moved_back,
    "duplicate-reviews": reviewed_twice,
}
"""Each measure judged per 72 h, and how one thing it counts is written to the store."""


def worth(store, name: str, slugs: list[str]) -> float:
    """What `slugs` come to in `name`'s unit by hand: a row each, or for `done-no-merge` the sum
    of their crew units, in millions."""
    if name != "done-no-merge":
        return len(slugs)
    marks = ",".join("?" * len(slugs))
    (units,) = store.execute(
        f"select sum(units) from call_rows where role = 'crew' and slug in ({marks})", slugs
    ).fetchone()
    return units / 1e6


@pytest.mark.parametrize("name", SEEDS)
def test_a_measure_judged_per_72_hours_reads_the_last_72_hours(store, name):
    """On a Monday afternoon, things 2 h, 30 h and 60 h old are of the last 72 h, the last two from
    before the week began at Sunday's midnight, and one 80 h old is not: the measure reads what
    the three come to, as a plain count or sum, with nothing scaled by the days the span has."""
    for hours in (2, 30, 60, 80):
        SEEDS[name](store, f"row-{hours}h", MONDAY - timedelta(hours=hours))
    reading = measures.read(store, measure(name), "jstack", MONDAY, USER)
    assert measure(name).window == "72h"
    assert reading.value == pytest.approx(worth(store, name, ["row-2h", "row-30h", "row-60h"]))


@pytest.mark.parametrize("now", [MONDAY, SATURDAY], ids=["monday", "saturday"])
@pytest.mark.parametrize("name", SEEDS)
def test_no_sunday_resets_a_72_hour_count(store, name, now):
    """A thing 71 h old is counted and one 73 h old is not, early in the week and late in it."""
    SEEDS[name](store, "row-71h", now - timedelta(hours=71))
    SEEDS[name](store, "row-73h", now - timedelta(hours=73))
    reading = measures.read(store, measure(name), "jstack", now, USER)
    assert reading.value == pytest.approx(worth(store, name, ["row-71h"]))
