"""The scorecard's measures read the telemetry store against their baselines.

The tests build a store with the real `telemetry.connect`, so each query meets the schema and
views jbus builds, and read the measures through `measures.read`, as `jbus scorecard` does.
"""

import contextlib
import hashlib
import importlib
import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import jsettings
from jbus import cli, telemetry
from jbus.telemetry import measures, values
from jgauge import spend as jgauge_spend
from test_jbus_telemetry import Machine

MODULES = (
    "jbus.telemetry.measures.m01_lead_time",
    "jbus.telemetry.measures.m02_pr_to_merge_p85",
    "jbus.telemetry.measures.m03_hours_after_pr",
    "jbus.telemetry.measures.m04_merged_per_day",
    "jbus.telemetry.measures.m05_queue_depth",
    "jbus.telemetry.measures.m06_held_ready_pr",
    "jbus.telemetry.measures.m07_wait_verdicts",
    "jbus.telemetry.measures.m08_crew_units_per_row",
    "jbus.telemetry.measures.m09_reviewer_units_per_row",
    "jbus.telemetry.measures.m10_dollars_per_row",
    "jbus.telemetry.measures.m11_home_context",
    "jbus.telemetry.measures.m12_crew_context",
    "jbus.telemetry.measures.m13_first_call_context",
    "jbus.telemetry.measures.m14_crew_first_load",
    "jbus.telemetry.measures.m15_coordination_share",
    "jbus.telemetry.measures.m16_scout_units_joined",
    "jbus.telemetry.measures.m17_pr_checks_failed",
    "jbus.telemetry.measures.m18_two_review_rounds",
    "jbus.telemetry.measures.m19_first_round",
    "jbus.telemetry.measures.m20_fix_share",
    "jbus.telemetry.measures.m21_red_main_minutes",
    "jbus.telemetry.measures.m22_change_failure",
    "jbus.telemetry.measures.m23_follow_ups",
    "jbus.telemetry.measures.m24_backward_moves",
    "jbus.telemetry.measures.m25_macos_on_prs",
    "jbus.telemetry.measures.m26_typed_per_day",
    "jbus.telemetry.measures.m27_typed_per_row",
    "jbus.telemetry.measures.m28_go_refused",
    "jbus.telemetry.measures.m29_gate_wait",
    "jbus.telemetry.measures.m30_lost_asks",
    "jbus.telemetry.measures.m31_friction_by_surface",
    "jbus.telemetry.measures.m32_pass_time",
    "jbus.telemetry.measures.m33_failed_launches",
    "jbus.telemetry.measures.m34_capped_reads",
    "jbus.telemetry.measures.m35_gh_allowance",
    "jbus.telemetry.measures.m36_load_over_cores",
    "jbus.telemetry.measures.m37_slot_exits",
    "jbus.telemetry.measures.m38_slot_wait",
    "jbus.telemetry.measures.m39_disk",
    "jbus.telemetry.measures.m40_drift_broken",
    "jbus.telemetry.measures.m41_build_time",
    "jbus.telemetry.measures.m42_crew_after_pr",
    "jbus.telemetry.measures.m43_sends_share",
    "jbus.telemetry.measures.m44_go_to_launch_p90",
    "jbus.telemetry.measures.m45_hours_unowned",
    "jbus.telemetry.measures.m46_reviewer_sessions",
    "jbus.telemetry.measures.m47_done_no_merge",
    "jbus.telemetry.measures.m48_closed_unmerged",
    "jbus.telemetry.measures.m49_duplicate_reviews",
    "jbus.telemetry.measures.m50_reread_tokens",
    "jbus.telemetry.measures.m51_brief_versions",
    "jbus.telemetry.measures.m52_needs_me_asks",
    "jbus.telemetry.measures.m53_sidebar_friction",
    "jbus.telemetry.measures.m54_status_asks",
    "jbus.telemetry.measures.m55_merge_asks",
    "jbus.telemetry.measures.m56_reply_corrections",
    "jbus.telemetry.measures.m57_approval_reasks",
    "jbus.telemetry.measures.m58_visual_misses",
    "jbus.telemetry.measures.m59_wrong_home",
    "jbus.telemetry.measures.m60_schema_files",
    "jbus.telemetry.measures.m61_gh_calls_per_hour",
)
"""Each measure's module by its dotted name, so a new measure is named by a test that reads it."""

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


def test_the_registry_is_each_measure_module_in_the_order_of_its_name():
    assert tuple(importlib.import_module(module).MEASURE for module in MODULES) == measures.MEASURES


@pytest.mark.parametrize("module", MODULES)
def test_every_measure_reads_an_empty_store_as_none_or_ok(store, module):
    """Each query meets the store's schema and takes only the three parameters a read binds, and
    an empty store is never past a line or worse than a baseline."""
    each = importlib.import_module(module).MEASURE
    reading = measures.read(store, each, "jstack", NOW, USER)
    assert reading.state in ("none", "ok"), reading
    if isinstance(each.source, measures.Sql):
        assert reading.note == "", reading.note
    else:
        assert reading.note == f"needs {each.source.needs}"


def test_a_query_that_fails_reads_none_with_its_error(tmp_path):
    """A store with none of the tables, as a file with no schema is, reads `none`: no raise."""
    bare = sqlite3.connect(tmp_path / "bare.sqlite")
    reading = measures.read(bare, measure("macos-on-prs"), "jstack", NOW, USER)
    assert reading.state == "none"
    assert "no such table: runs" in reading.note


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


def first_load(store, at: datetime, kilobytes: float) -> None:
    store.execute(
        "insert into first_loads (project, key, at, bytes) values ('', ?, ?, ?)",
        (stamp(at), stamp(at), int(kilobytes * 1000)),
    )


@pytest.mark.parametrize(
    ("today", "state"),
    [(21.0, "bad"), (17.5, "watch"), (16.0, "ok")],
)
def test_a_trend_is_past_its_line_above_the_mean_of_its_seven_days_before(store, today, state):
    """The crew first load was 17 KB at this time on each of the seven days before; 20% over
    that mean is past its line, and under it but over the baseline of 16.3 KB is a watch."""
    load = measure("crew-first-load")
    assert (load.kind, load.baseline) == (measures.Trend(20), 16.3)
    for back in range(1, 8):
        first_load(store, NOW - timedelta(days=back, minutes=5), 17.0)
    first_load(store, NOW - timedelta(minutes=5), today)
    reading = measures.read(store, load, "jstack", NOW, USER)
    assert (reading.value, reading.state) == (today, state)


def scorecard(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "scorecard", *argv])
    return code, out.getvalue()


def test_jbus_scorecard_prints_each_measure_and_writes_nothing(tmp_path, monkeypatch):
    Machine(tmp_path, monkeypatch)
    path = tmp_path / "store.sqlite"
    writer = telemetry.connect(path)
    created = stamp(datetime.now(UTC) - timedelta(minutes=1))
    for project in ("alpha", "beta"):
        writer.execute(
            "insert into runs (project, key, workflow, event, created)"
            " values (?, 'r1', 'macos', 'pull_request', ?)",
            (project, created),
        )
    writer.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    code, out = scorecard("--json", "--store", str(path))
    assert code == 0
    read = json.loads(out)
    assert [item["name"] for item in read] == [each.name for each in measures.MEASURES]
    for item in read:
        assert {"name", "group", "value", "n", "baseline", "state", "tier", "audit"} <= set(item)
    macos = next(item for item in read if item["name"] == "macos-on-prs")
    assert (macos["value"], macos["state"], macos["tier"]) == (1, "bad", "wake")

    code, out = scorecard("--store", str(path))
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == len(measures.MEASURES)
    assert next(line for line in lines if "macos-on-prs" in line).startswith("bad ")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    code, out = scorecard("--store", str(tmp_path / "none.sqlite"))
    assert (code, out.startswith("refused: no telemetry store")) == (2, True)
    assert not (tmp_path / "none.sqlite").exists()


def test_no_two_measures_share_a_name():
    names = [each.name for each in measures.MEASURES]
    assert len(names) == len(set(names))


AUDIT = range(1, 41)
"""The ranks of the audit's 40 findings (`reports/po-audit.html` in the home)."""


def test_every_finding_of_the_audit_is_carried_by_a_measure():
    """Each rank is in some measure's `audit`, so the scorecard reads every counter the audit
    ranked, and no measure names a rank the audit does not have."""
    carried = {rank for each in measures.MEASURES for rank in each.audit}
    assert carried == set(AUDIT)


def calls(store, project: str, role: str, slug: str, session: str, thread: str, *made) -> None:
    """A session of `role` on `slug` and its calls, each `(at, tokens of context)`, all of it as
    input on Opus, so a call's dollars are its tokens at Opus's plain price."""
    store.execute(
        "insert into sessions (provider, session, thread, project, role, slug)"
        " values ('claude', ?, ?, ?, ?, ?)",
        (session, thread, project, role, slug),
    )
    for i, (at, tokens) in enumerate(made):
        store.execute(
            "insert into calls (provider, call, session, at, model, input, cache_write,"
            " cache_read, output, final, day) values ('claude', ?, ?, ?, 'claude-opus-5-5', ?,"
            " 0, 0, 0, 1, ?)",
            (f"{session}.{i}", session, stamp(at), tokens, at.date().isoformat()),
        )


def queued(store, slug: str, entry: str | None, briefed: datetime) -> None:
    store.execute(
        "insert into queue (project, key, slug, status, entry, queued_by_session)"
        " values ('jstack', ?, ?, 'launched', ?, 'h1')",
        (slug, slug, entry),
    )
    store.execute(
        "insert into brief_versions (project, key, at, slug) values ('jstack', ?, ?, ?)",
        (slug, stamp(briefed), slug),
    )


def test_the_three_weekly_reads_of_calls_give_these_values(store):
    """The week began at Sunday's midnight in New York, 2026-11-08 05:00 UTC. Crew-context is the
    mean context of this week's crew calls of the project, a call of a session begun last week
    among them; first-call-context is the mean of the first call of each crew session begun this
    week; dollars-per-row is what the week's one merged row spent: its crew's calls, the home's
    calls whose next brief was its own, and its scout's whole share, since its entry has no other
    merged row. A home call whose next brief is a row that has not merged, and one after the last
    brief, are no merged row's."""
    week = datetime(2026, 11, 8, 5, tzinfo=UTC)
    monday = datetime(2026, 11, 9, tzinfo=UTC)
    calls(
        store,
        "jstack",
        "crew",
        "row-old",
        "c0",
        "mcp:c0",
        (week - timedelta(days=3), 100_000),
        (week + timedelta(hours=7), 30_000),
    )
    calls(
        store,
        "jstack",
        "crew",
        "row-a",
        "c1",
        "mcp:c1",
        (monday + timedelta(hours=14), 40_000),
        (monday + timedelta(hours=15), 80_000),
    )
    calls(store, "jstack", "crew", "row-b", "c2", "mcp:c2", (monday + timedelta(hours=16), 60_000))
    calls(
        store, "elsewhere", "crew", "row-e", "e1", "mcp:e1", (monday + timedelta(hours=16), 900_000)
    )
    calls(store, "jstack", "home", "jstack", "h1", "mcp:home", (monday + timedelta(hours=12), 500))
    calls(
        store,
        "jstack",
        "home",
        "jstack",
        "h2",
        "mcp:home",
        (monday + timedelta(hours=13), 1_000),
        (monday + timedelta(hours=14), 3_000),
        (monday + timedelta(hours=20), 7_000),
    )
    calls(store, "jstack", "scout", "scout-x", "s1", "mcp:s1", (week + timedelta(hours=5), 2_000))
    queued(store, "row-a", "scout-x", monday + timedelta(hours=13, minutes=30))
    queued(store, "row-b", None, monday + timedelta(hours=14, minutes=30))
    store.execute(
        "insert into transitions (project, key, at, slug, from_status, to_status, day)"
        " values ('jstack', 't1', ?, 'row-a', 'pr', 'merged', '2026-11-09')",
        (stamp(monday + timedelta(hours=18)),),
    )

    def read(name: str) -> tuple[float | None, int]:
        reading = measures.read(store, measure(name), "jstack", NOW, USER)
        assert reading.note == "", reading.note
        return reading.value, reading.n

    assert read("crew-context") == (pytest.approx((30 + 40 + 80 + 60) / 4), 4)
    assert read("first-call-context") == (pytest.approx((40 + 60) / 2), 2)
    opus = jgauge_spend.PRICES["claude-opus-5-5"].plain / 1e6
    spent = (40_000 + 80_000) + (500 + 1_000) + 2_000
    assert read("dollars-per-row") == (pytest.approx(spent * opus), 1)


@pytest.mark.parametrize("name", ["crew-context", "first-call-context", "dollars-per-row"])
def test_no_weekly_read_of_calls_walks_every_call_of_a_provider(store, name):
    """A store made by `telemetry.connect` gives SQLite's planner the shape of `calls`
    (`jbus.telemetry.migrations.v016_calls_stats`), so a read joins a session to its own calls by
    `calls_session` and never reads `calls` by its provider alone, once a session: on the store of
    311756 calls that walk made crew-context and first-call-context about 30 s each."""
    query = measure(name).source.query
    bound = {"project": "jstack", "begins": stamp(NOW), "ends": stamp(NOW)}
    plan = [row[3] for row in store.execute(f"EXPLAIN QUERY PLAN {query}", bound)]
    assert not [step for step in plan if step.endswith("USING PRIMARY KEY (provider=?)")], plan
