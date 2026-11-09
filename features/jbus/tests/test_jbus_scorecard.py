"""The scorecard's measures read the telemetry store against their baselines.

The tests build a store with the real `telemetry.connect`, so each query meets the schema and
views jbus builds, and read the measures through `measures.read`, as `jbus scorecard` does.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import jsettings
from jbus import telemetry
from jbus.telemetry import measures, values

NOW = datetime(2026, 11, 9, 21, 20, tzinfo=UTC)
USER = jsettings.Settings(zone=ZoneInfo("America/New_York"))


@pytest.fixture
def store(tmp_path):
    connection = telemetry.connect(tmp_path / telemetry.FILE)
    yield connection
    connection.close()


def measure(name: str) -> measures.Measure:
    return next(each for each in measures.MEASURES if each.name == name)


def stamp(moment: datetime) -> str:
    return moment.strftime(values.STAMP)


def test_every_query_runs_on_an_empty_store(store):
    """Each query meets the store's schema and takes only the three parameters a read binds, and
    an empty store is never past a line or worse than a baseline."""
    queried = [each for each in measures.MEASURES if isinstance(each.source, measures.Sql)]
    assert queried
    for each in queried:
        reading = measures.read(store, each, "jstack", NOW, USER)
        assert reading.note == "", (each.name, reading.note)
        assert reading.state in ("none", "ok"), (each.name, reading)


def run(store, project: str, key: str) -> None:
    created = stamp(NOW - timedelta(hours=1))
    store.execute(
        "insert into runs (project, key, at, run, attempt, workflow, event, created, day)"
        " values (?, ?, ?, 1, 1, 'macos', 'pull_request', ?, '2026-11-09')",
        (project, key, created, created),
    )


def test_one_macos_run_on_a_pull_request_is_bad(store):
    macos = measure("macos-on-prs")
    run(store, "elsewhere", "r0")
    assert measures.read(store, macos, "jstack", NOW, USER).state == "ok"
    run(store, "jstack", "r1")
    reading = measures.read(store, macos, "jstack", NOW, USER)
    assert (reading.value, reading.state) == (1, "bad")


def launches(store, count: int, failed: int) -> None:
    for i in range(count):
        at = stamp(NOW - timedelta(minutes=30) + timedelta(seconds=i))
        moves = [("queued", "launched")] + ([("launched", "failed")] if i < failed else [])
        for j, (begins, ends) in enumerate(moves):
            store.execute(
                "insert into transitions (project, key, at, slug, from_status, to_status, day)"
                " values ('jstack', ?, ?, ?, ?, ?, '2026-11-09')",
                (f"k{i}.{j}", at, f"row{i}", begins, ends),
            )


def test_a_limit_under_its_floor_reads_none(store):
    """Four launches in the hour, all failed, are under the floor of five: no reading."""
    failed = measure("failed-launches")
    assert failed.kind == measures.Limit(20, 5)
    launches(store, 4, 4)
    reading = measures.read(store, failed, "jstack", NOW, USER)
    assert (reading.n, reading.state) == (4, "none")


def test_a_limit_at_its_floor_past_its_line_is_bad(store):
    launches(store, 5, 2)
    reading = measures.read(store, measure("failed-launches"), "jstack", NOW, USER)
    assert (reading.value, reading.n, reading.state) == (40, 5, "bad")


def test_no_two_measures_share_a_name():
    names = [each.name for each in measures.MEASURES]
    assert len(names) == len(set(names)) == 41
