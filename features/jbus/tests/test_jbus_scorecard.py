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
from jbus.telemetry import scorecard as card
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
    "jbus.telemetry.measures.m62_live_sessions",
    "jbus.telemetry.measures.m63_gh_calls_per_session_hour",
    "jbus.telemetry.measures.m64_merges_per_session_hour",
    "jbus.telemetry.measures.m65_units_per_merge",
    "jbus.telemetry.measures.m66_rework_per_merge",
    "jbus.telemetry.measures.m67_units_vs_capped_line",
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


def closed_unmerged(store, number: int, branch: str, closed: datetime) -> None:
    store.execute(
        "insert into ci_prs (project, key, number, branch, created, closed, day)"
        " values ('jstack', ?, ?, ?, ?, ?, ?)",
        (
            str(number),
            number,
            branch,
            stamp(closed - timedelta(hours=1)),
            stamp(closed),
            closed.date().isoformat(),
        ),
    )


def test_closed_unmerged_counts_abandoned_pull_requests_of_the_last_72_hours(store):
    """A probe whose row asked for no pull request and a revert jbus opened and closed are never
    meant to merge, so neither counts; a pull request closed 60 h ago, before the week began at
    2026-11-08 05:00 UTC, by a branch that is no row, does, and the value is the count itself."""
    store.execute(
        "insert into queue (project, key, slug, status) values ('jstack', 'probe', 'probe', 'done')"
    )
    store.execute(
        "insert into brief_versions (project, key, at, slug, pull)"
        " values ('jstack', 'probe', ?, 'probe', 'none')",
        (stamp(NOW - timedelta(hours=4)),),
    )
    closed_unmerged(store, 1, "probe", NOW - timedelta(hours=2))
    store.execute(
        "insert into reverts (project, key, branch) values ('jstack', 'r', 'revert-9-main-x')"
    )
    closed_unmerged(store, 2, "revert-9-main-x", NOW - timedelta(hours=1))
    closed_unmerged(store, 3, "abandoned", NOW - timedelta(hours=60))
    closed_unmerged(store, 4, "too-old", NOW - timedelta(hours=73))
    reading = measures.read(store, measure("closed-unmerged"), "jstack", NOW, USER)
    assert (reading.value, reading.n) == (1, 1)


def scorecard(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "scorecard", *argv])
    return code, out.getvalue()


def test_load_over_cores_is_the_share_of_todays_load_samples_above_the_cores(tmp_path, monkeypatch):
    """jgauge's load.tsv, its header and a row each 15 s, reaches the store through a build, and
    `load-over-cores` reads the share of today's rows whose 1-minute load is above their cores:
    30 of today's 120, so 25%, past its line. A load equal to the cores is not above them, and
    yesterday's rows over the cores are not today's."""
    machine = Machine(tmp_path, monkeypatch)
    log = tmp_path / "load.tsv"
    monkeypatch.setenv("JGAUGE_LOAD_LOG", str(log))
    yesterday = [(NOW - timedelta(days=1, seconds=15 * i), "40.00") for i in range(10)]
    today = [
        (
            NOW - timedelta(seconds=15 * (i + 1)),
            "30.52" if i < 30 else "24.00" if i < 60 else "3.10",
        )
        for i in range(120)
    ]
    lines = [f"{int(at.timestamp())}\t24\t{load}\t1.00\t1.00" for at, load in yesterday + today]
    log.write_text("\n".join(["time\tcores\tload1\tload5\tload15", *lines]) + "\n")
    machine.build()
    with contextlib.closing(machine.store()) as store:
        reading = measures.read(store, measure("load-over-cores"), "alpha", NOW, USER)
    assert (reading.value, reading.n, reading.state) == (25.0, 120, "bad")


MIDNIGHT = datetime(2026, 11, 10, 0, 0, 30, tzinfo=USER.zone)
"""30 seconds into a New York day, when a minute before now is the user's day before."""


@pytest.mark.parametrize("clock", [None, MIDNIGHT], ids=["now", "first-minute"])
def test_jbus_scorecard_prints_each_measure_and_writes_nothing(tmp_path, monkeypatch, clock):
    """A macOS run on a pull request today reads 1 and bad at any time of the user's day."""
    Machine(tmp_path, monkeypatch)
    settings = tmp_path / "x" / "jstack" / "config.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text('timezone = "America/New_York"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(settings.parent.parent))
    now = clock or datetime.now(UTC)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(telemetry, "datetime", Frozen)
    path = tmp_path / "store.sqlite"
    writer = telemetry.connect(path)
    created, _ = measures.bounds("day", now, USER)
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
        assert {"name", "group", "value", "n", "baseline", "state", "tier", "audit", "each"} <= set(
            item
        )
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


def test_a_week_baseline_is_the_measures_own_query_over_that_week(store):
    """dollars-per-row's baseline is the week of 2026-11-01 read by the same view as the value,
    so a change of what a row's dollars count moves the baseline with the value. Each week has a
    merged row with a crew call and the home call that led to it."""
    for slug, home_session, monday, crew, home in (
        ("row-l", "h1", datetime(2026, 11, 2, tzinfo=UTC), 90_000, 6_000),
        ("row-a", "h2", datetime(2026, 11, 9, tzinfo=UTC), 50_000, 2_000),
    ):
        noon = monday + timedelta(hours=12)
        calls(store, "jstack", "home", "jstack", home_session, "mcp:home", (noon, home))
        queued(store, slug, None, noon + timedelta(hours=1))
        calls(store, "jstack", "crew", slug, f"c-{slug}", f"mcp:{slug}", (noon, crew))
        store.execute(
            "insert into transitions (project, key, at, slug, from_status, to_status, day)"
            " values ('jstack', ?, ?, ?, 'pr', 'merged', ?)",
            (f"t-{slug}", stamp(noon + timedelta(hours=3)), slug, monday.date().isoformat()),
        )
    (last,) = store.execute(
        "select dollars_per_row from weekly_row_spend"
        " where project = 'jstack' and week = '2026-11-01'"
    ).fetchone()
    opus = jgauge_spend.PRICES["claude-opus-5-5"].plain / 1e6
    assert last == pytest.approx(96_000 * opus)

    reading = measures.read(store, measure("dollars-per-row"), "jstack", NOW, USER)

    assert (reading.value, reading.baseline) == (pytest.approx(52_000 * opus), pytest.approx(last))


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


def test_exactly_three_measures_wake_and_no_other_alert_raises_them():
    """A wake opens an alert on jbus's list (`jbus.kpis`), so a fourth is a change someone chose,
    and each of the three keeps the line it was chosen with."""
    wakes = {
        each.name: each for each in measures.MEASURES if each.tier == "wake" and not each.wired
    }
    assert sorted(wakes) == ["failed-launches", "held-ready-pr", "macos-on-prs"]
    assert (wakes["macos-on-prs"].kind, wakes["macos-on-prs"].window) == (measures.Zero(), "day")
    assert wakes["failed-launches"].kind == measures.Limit(20, 5)
    assert wakes["held-ready-pr"].kind == measures.Limit(2, 0)
    assert wakes["held-ready-pr"].unit == "h"


def ran(store, instance: str, *made) -> None:
    """A crew session on `instance` and its calls, each `(at, units)`, all of it plain input on
    Sonnet, so a call's units are its tokens."""
    store.execute(
        "insert into sessions (provider, session, instance, project, role)"
        " values ('claude', ?, ?, 'jstack', 'crew')",
        (instance, instance),
    )
    for i, (at, units) in enumerate(made):
        store.execute(
            "insert into calls (provider, call, session, at, model, input, cache_write,"
            " cache_read, output, final, day) values ('claude', ?, ?, ?, 'claude-sonnet-5-5', ?,"
            " 0, 0, 0, 1, ?)",
            (f"{instance}.{i}", instance, stamp(at), units, at.date().isoformat()),
        )


def quota(store, instance: str, window: str, *readings) -> None:
    """The health look's readings of `instance`'s `window`, each `(at, percent used)`."""
    for at, value in readings:
        store.execute(
            "insert into health_readings (project, key, at, reading, value, over)"
            " values ('', ?, ?, ?, ?, 0)",
            (f"{instance} {window} {stamp(at)}", stamp(at), f"quota {instance} {window}", value),
        )


def test_units_an_hour_read_against_each_accounts_capped_line(store):
    """claudeAgent's seven-day window rose 10 points over 168 M units, so 100 points, its whole
    week, is 1,680 M units, and its capped line is 10 M an hour; it ran 5 M in the last hour, 50%
    of its line. prime's rose 10 points over 84 M, a line of 5 M an hour, and it ran 10 M, 200%:
    the measure is past its line at the account nearest its cap, and shows each account."""
    hours = [NOW - timedelta(hours=back) for back in (6, 1)]
    quota(store, "claudeAgent", "seven_day", (hours[0], 30), (hours[1], 40))
    quota(store, "claudeAgent", "five_hour", (hours[0], 0), (hours[1], 0))
    quota(store, "prime", "seven_day", (hours[0], 10), (hours[1], 20))
    ran(
        store,
        "claudeAgent",
        (hours[0] + timedelta(hours=2), 168_000_000),
        (NOW - timedelta(minutes=30), 5_000_000),
    )
    ran(
        store,
        "prime",
        (hours[0] + timedelta(hours=2), 84_000_000),
        (NOW - timedelta(minutes=30), 10_000_000),
    )
    reading = measures.read(store, measure("units-vs-capped-line"), "jstack", NOW, USER)
    assert (reading.value, reading.n, reading.state) == (200.0, 2, "bad")
    assert reading.each == (
        measures.Part("claudeAgent", 5.0, 10.0),
        measures.Part("prime", 10.0, 5.0),
    )
    page = card.page([card.Line(measure("units-vs-capped-line"), reading)], NOW)
    assert "claudeAgent 5 of 10 M units an hour" in page and "prime 10 of 5 M units an hour" in page


def test_an_account_whose_quota_rose_too_little_has_no_capped_line_yet(store):
    """A rise of a point or two says more about where the percent rounds than about the account:
    its line would swing tenfold, so the account is shown with its units an hour alone."""
    quota(store, "claudeAgent", "seven_day", (NOW - timedelta(hours=3), 30), (NOW, 31))
    ran(store, "claudeAgent", (NOW - timedelta(minutes=30), 5_000_000))
    reading = measures.read(store, measure("units-vs-capped-line"), "jstack", NOW, USER)
    assert (reading.value, reading.state) == (None, "none")
    assert reading.each == (measures.Part("claudeAgent", 5.0, None),)
    page = card.page([card.Line(measure("units-vs-capped-line"), reading)], NOW)
    assert "claudeAgent 5 M units an hour, no line yet" in page


def test_a_quota_rise_across_a_reset_counts_the_new_share_alone(store):
    """The view `quota_rises` (`jbus.telemetry.views.quota_rises`) steps from reading to reading;
    where the window reset between two, its share fell, and the points it gained are the new
    share."""
    quota(
        store,
        "claudeAgent",
        "seven_day",
        (NOW - timedelta(hours=2), 95),
        (NOW - timedelta(hours=1), 98),
        (NOW, 4),
    )
    rows = store.execute("select span, rise from quota_rises order by at").fetchall()
    assert rows == [("seven_day", 3.0), ("seven_day", 4.0)]


def test_a_measure_whose_each_query_fails_keeps_its_value_and_shows_no_part(store):
    each = measures.Measure(
        name="probe",
        group="machinery",
        says="a probe",
        unit="%",
        better="lower",
        source=measures.Sql("select 7 as value, 1 as n", each="select label from nowhere"),
        window="hour",
        baseline=10,
        baseline_of="a test",
        kind=measures.Limit(100),
        tier="page",
    )
    reading = measures.read(store, each, "jstack", NOW, USER)
    assert (reading.value, reading.state, reading.each) == (7.0, "ok", ())
