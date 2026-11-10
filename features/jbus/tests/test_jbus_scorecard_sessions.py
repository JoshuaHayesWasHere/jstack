"""The six measures of how close the machine is to a thousand sessions, read on one small store.

A live session is a thread between its first and last model call. On 2026-11-09 in New York, the
day so far at `NOW` begins at 05:00 UTC. Thread `mcp:a` makes calls from two sessions, at 14:00
and 16:00; `mcp:b` at 15:00 and 15:30; `mcp:c` once, at 17:00; and `mcp:old` only before the day
began. So three threads were live today, at most two at once (at 15:00), for 2.5 session-hours.
"""

from datetime import UTC, datetime, timedelta

import pytest

from jbus import telemetry
from jbus.telemetry import measures
from test_jbus_scorecard import NOW, USER, measure, stamp

DAY = datetime(2026, 11, 9, 5, tzinfo=UTC)
HOURS = 2.5
REWORK = ("content-changed", "dropped", "conflicts", "proved-stale", "checked-stale")


def call(store, session: str, thread: str, at: datetime, units: int) -> None:
    """One call on Sonnet, whose units are its input tokens."""
    store.execute(
        "insert or ignore into sessions (provider, session, thread, project, role)"
        " values ('claude', ?, ?, 'jstack', 'crew')",
        (session, thread),
    )
    store.execute(
        "insert into calls (provider, call, session, at, model, input, cache_write, cache_read,"
        " output, final, day) values ('claude', ?, ?, ?, 'claude-sonnet-5-5', ?, 0, 0, 0, 1, ?)",
        (f"{session}.{stamp(at)}", session, stamp(at), units, at.date().isoformat()),
    )


def gh(store, hour: str, resource: str, calls: int, not_modified: int) -> None:
    store.execute(
        "insert into gh_hours (hour, caller, resource, calls, not_modified, failed)"
        " values (?, 'jbus.tick', ?, ?, ?, 0)",
        (hour, resource, calls, not_modified),
    )


def merged(store, project: str, key: str, at: datetime) -> None:
    store.execute(
        "insert into merged (project, key, slug, number, merged_at, day) values (?, ?, ?, 1, ?, ?)",
        (project, key, key, stamp(at), at.date().isoformat()),
    )


def wait(store, project: str, key: str, label: str, at: datetime) -> None:
    store.execute(
        "insert into merges (project, key, at, verb, number, label, day)"
        " values (?, ?, ?, 'wait', 1, ?, ?)",
        (project, key, stamp(at), label, at.date().isoformat()),
    )


@pytest.fixture
def day(tmp_path):
    store = telemetry.connect(tmp_path / telemetry.FILE)
    hour = timedelta(hours=1)
    call(store, "a1", "mcp:a", DAY + 9 * hour, 2_000_000)
    call(store, "a2", "mcp:a", DAY + 11 * hour, 3_000_000)
    call(store, "b1", "mcp:b", DAY + 10 * hour, 1_000_000)
    call(store, "b1", "mcp:b", DAY + 10.5 * hour, 1_000_000)
    call(store, "c1", "mcp:c", DAY + 12 * hour, 2_000_000)
    call(store, "old", "mcp:old", DAY - 3 * hour, 9_000_000)
    call(store, "old", "mcp:old", DAY - 2 * hour, 9_000_000)
    gh(store, "2026-11-09T04", "core", 900, 0)
    gh(store, "2026-11-09T14", "core", 600, 200)
    gh(store, "2026-11-09T14", "graphql", 1_000, 0)
    gh(store, "2026-11-09T21", "core", 100, 0)
    merged(store, "jstack", "m1", DAY + 9 * hour)
    merged(store, "jstack", "m2", DAY + 12 * hour)
    merged(store, "elsewhere", "m3", DAY + 13 * hour)
    merged(store, "jstack", "m0", DAY - hour)
    for i, label in enumerate((*REWORK, "live-run", "fresh-conflict")):
        wait(store, "jstack", f"w{i}", label, DAY + 9 * hour)
    wait(store, "elsewhere", "e1", "content-changed", DAY + 9 * hour)
    wait(store, "jstack", "w-old", "dropped", DAY - hour)
    yield store
    store.close()


def read(store, name: str) -> measures.Reading:
    reading = measures.read(store, measure(name), "jstack", NOW, USER)
    assert reading.note == "", reading.note
    return reading


def test_live_sessions_is_the_most_threads_live_at_once_today(day):
    reading = read(day, "live-sessions")
    assert (reading.value, reading.n, reading.baseline) == (2, 3, 48)


def test_gh_calls_per_session_hour_counts_core_calls_that_cost(day):
    """A 304 costs nothing and GraphQL is another allowance: 400 core calls cost at 14:00 and
    100 in the hour still running."""
    reading = read(day, "gh-calls-per-session-hour")
    assert (reading.value, reading.baseline) == (pytest.approx(500 / HOURS), 171)


def test_gh_calls_per_session_hour_is_no_reading_under_twenty_session_hours(day):
    """Over 2.5 session-hours the idle floor is most of the numerator: the value says how idle
    the machine was, not what a session costs."""
    reading = read(day, "gh-calls-per-session-hour")
    assert (reading.n, reading.state) == (int(HOURS), "none")


def test_the_idle_floor_counts_only_hours_with_no_session_live(day):
    """A thread is live in an hour from its first to its last model call in that hour, so a home
    left open all day is not at work in the hours between. Hour 07 had no call and cost 1,500
    core calls; hour 10 had `mcp:d` live for 20 minutes and cost 500; hour 14 had one call of
    `mcp:a`, live no time in it, and cost 400. Hour 15 had `mcp:b` live for half an hour, hour 04
    is before the day, a GraphQL call is another allowance, and hour 21 is still running."""
    call(day, "d1", "mcp:d", DAY + 5 * timedelta(hours=1), 1)
    call(day, "d1", "mcp:d", DAY + 5 * timedelta(hours=1) + timedelta(minutes=20), 1)
    gh(day, "2026-11-09T07", "core", 2_000, 500)
    gh(day, "2026-11-09T07", "graphql", 4_000, 0)
    gh(day, "2026-11-09T10", "core", 700, 200)
    gh(day, "2026-11-09T15", "core", 9_000, 0)
    reading = read(day, "gh-idle-calls-per-hour")
    assert (reading.value, reading.n, reading.baseline) == (800, 3, 2_130)
    assert reading.state == "bad"


def test_merges_per_session_hour_counts_every_project(day):
    """The machine's sessions merge for every project it serves."""
    reading = read(day, "merges-per-session-hour")
    assert (reading.value, reading.n, reading.baseline) == (pytest.approx(3 / HOURS), 3, 0.71)


def test_units_per_merge_is_every_unit_spent_today_over_its_merges(day):
    reading = read(day, "units-per-merge")
    assert (reading.value, reading.n, reading.baseline) == (pytest.approx(9 / 3), 3, 3.76)


def test_rework_per_merge_counts_the_five_waits_that_redo_a_pull_request(day):
    """A live run or a fresh conflict is not rework, nor another project's wait."""
    reading = read(day, "rework-per-merge")
    assert (reading.value, reading.n, reading.baseline) == (pytest.approx(5 / 2), 2, 2.1)
