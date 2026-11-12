"""A measure judged against "last week" reads that week with its own query.

A literal baseline stays where it was read while a later change moves what the measure's view
counts: `change-failure`'s 3.0 was read before #1588 made `change_failures` count only the spells
a change caused. A `Week` baseline is read by the same query as the value, so both sides of the
comparison are of one definition.
"""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import jsettings
from jbus.telemetry import measures, values

NAMED = measures.Week(date(2026, 11, 1))
"""The week #1583 pinned the baselines to, and not a rolling last week."""

WEEKLY = {
    "lead-time": (105.9, 127, 5),
    "pr-to-merge-p85": (261, 313.2, 5),
    "coordination-share": (41.2, 49.5, 3),
    "first-round": (29.9, 23.9, 5),
    "change-failure": (3.0, 3.6, 20),
    "typed-per-row": (1.07, 1.28, 5),
    "drift-broken": (3, 3.6, 1),
    "build-time": (0.33, 0.4, 10),
}
"""Each measure's literal baseline before it read the named week, the `Limit` it was judged by,
and that limit's floor."""


def measure(name: str) -> measures.Measure:
    return next(each for each in measures.MEASURES if each.name == name)


@pytest.mark.parametrize("name", sorted(WEEKLY))
def test_each_weekly_measure_reads_its_baseline_with_its_own_query(name):
    """Each reads the named week by its own query, judged by an `Over` that stands where its old
    `Limit` stood over the old literal, within a point, and keeps that limit's floor."""
    literal, at, floor = WEEKLY[name]
    each = measure(name)

    assert each.baseline == NAMED
    assert isinstance(each.kind, measures.Over)
    assert each.kind.floor == floor
    step = each.kind.by / 100 if each.better == "lower" else -each.kind.by / 100
    assert literal * (1 + step) == pytest.approx(at, rel=0.01)
    assert each.baseline_of == "the same query over the week of 2026-11-01"


def test_no_literal_baseline_says_last_week():
    """A number beside "last week" goes stale as soon as the week rolls or the view changes, so a
    literal names the day it was read instead."""
    stale = [
        each.name
        for each in measures.MEASURES
        if not isinstance(each.baseline, measures.Week) and "last week" in each.baseline_of
    ]

    assert stale == []


THE_WEEK = datetime(2026, 11, 3, 12, tzinfo=UTC)
NOW = datetime(2026, 11, 10, 15, tzinfo=UTC)
USER = jsettings.Settings(zone=ZoneInfo("America/New_York"))
COUNT = "select sum(v), count(*) from t where project = :project and at >= :begins and at < :ends"
NOTE = "select count(*) || ' left out' from t where project = :project and at < :begins"


def noted(note: str) -> measures.Measure:
    """A measure judged against the named week whose source also gives a note."""
    return measures.Measure(
        name="noted",
        group="flow",
        says="",
        unit="",
        better="lower",
        source=measures.Sql(COUNT, note=note),
        window="72h",
        baseline=NAMED,
        baseline_of="",
        kind=measures.Over(20),
        tier="wake",
    )


@pytest.fixture
def store():
    """Rows of 2 and 3 in the named week, and one of 10 two hours before `NOW`."""
    connection = sqlite3.connect(":memory:")
    connection.execute("create table t (project text, at text, v real)")
    for at, v in (
        (THE_WEEK, 2),
        (THE_WEEK + timedelta(hours=1), 3),
        (NOW - timedelta(hours=2), 10),
    ):
        connection.execute("insert into t values ('jstack', ?, ?)", (at.strftime(values.STAMP), v))
    yield connection
    connection.close()


def test_a_week_baseline_and_a_note_are_read_together(store):
    """A reading carries the named week's value as its baseline and what the source's note says,
    side by side, and it is no failure."""
    reading = measures.read(store, noted(NOTE), "jstack", NOW, USER)

    assert (reading.value, reading.n, reading.baseline) == (10, 1, 5)
    assert (reading.note, reading.failed, reading.state) == ("2 left out", False, "bad")


def test_a_note_whose_query_fails_fails_the_reading_of_a_week_baseline(store):
    """A failing note query makes the whole reading `none` and failed, with no baseline: a week
    is read by the query, so none stands where the query failed."""
    reading = measures.read(store, noted("select nothing from nowhere"), "jstack", NOW, USER)

    assert (reading.value, reading.baseline, reading.state, reading.failed) == (
        None,
        None,
        "none",
        True,
    )
    assert reading.note.startswith("OperationalError: ")
