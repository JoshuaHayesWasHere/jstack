"""`jbus ci` keeps CI's jobs, and from them counts the plan's nine targets and the six CI health
numbers.

The tests check the numbers against a recording of GitHub's Actions API for jstack, from 2026-10-14
to 2026-10-17 (`features/jbus/tests/fixtures/ci/jstack`, which `ci_replay` replays). They run the
collector as `jbus ci` runs it. The plan's figures held the local runner's jobs alone. The numbers
now count the jobs of both runners together, so a figure that differs from the plan's says by how
much and why. The recording has no log of a hosted job, so each red hosted job is counted unread.
The health numbers are checked against a fixed slice of ci.jsonl written here (`SLICE`).
"""

import ast
import configparser
import itertools
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jsettings
from ci_replay import FOLDER, Replay
from jbus import ci, passes, watch
from jbus.ci import collect, daily, ledger, notice, numbers, report
from jbus.ci.collect import Unavailable
from test_jbus_kitchen import NOW as KITCHEN_NOW
from test_jbus_kitchen import REPO as CHECKOUT
from test_jbus_kitchen import iso, queued

HOST = "github.com"
REPO = "JoshuaHayesWasHere/jstack"
NOW = datetime(2026, 10, 17, 22, 15, tzinfo=UTC)
START = NOW - timedelta(days=14)


@pytest.fixture(scope="module")
def kept(tmp_path_factory):
    state = tmp_path_factory.mktemp("state")
    counts = collect.collect(Replay(), REPO, state, NOW, 14)
    return state, counts


@pytest.fixture(scope="module")
def facts(kept):
    state, _ = kept
    events = [json.loads(line) for line in (FOLDER / "events.jsonl").open()]
    return numbers.Facts(
        ledger.read(state / ledger.JOBS), ledger.read(state / ledger.PULLS), events, NOW
    )


@pytest.fixture(scope="module")
def nine(facts):
    return {one.key: one for one in numbers.compute(facts, START, NOW)}


def test_the_nine_targets_come_in_the_order_of_the_plan_and_the_health_numbers_after_them(nine):
    assert list(nine) == [
        "queue",
        "waste",
        "own",
        "rebases",
        "stale",
        "green",
        "mainred",
        "flaky",
        "inode",
        *HEALTH,
    ]


def test_a_green_job_waits_0_minutes_for_a_runner_and_runs_8_22_over_both_runners(nine):
    """The plan's 26.6 vs 9.67 was the local runner's 75 green jobs alone. The hosted runner's 120
    start at once, so over both the median wait is 0."""
    one = nine["queue"]
    assert (one.shown, one.n, one.met) == ("0 vs 8.22 min", 195, True)
    assert one.runners == "local 75, hosted 120"


def test_37_1_percent_of_both_runners_minutes_go_to_jobs_that_fail_or_are_cancelled(nine):
    """The plan's 42.9% was the local runner's alone, and the hosted runner's was 31.4%."""
    assert (nine["waste"].shown, nine["waste"].met) == ("37.1%", False)
    assert nine["waste"].runners == "local 130, hosted 165"


def test_7_of_68_reds_are_the_pull_requests_own_and_the_33_hosted_reds_are_unread(nine):
    """The plan's 7 of 35 was the local runner's reds. The recording has no log of the 33
    hosted reds, so they are counted unread and none of them is the pull request's own."""
    assert nine["own"].shown == "10% (7 of 68: 7 own, 10 main, 16 runner, 2 flake, 33 unread)"
    assert (nine["own"].met, nine["own"].runners) == (False, "local 35, hosted 33")


def test_29_force_pushes_over_62_merged_pull_requests_is_0_47_each(nine):
    assert nine["rebases"].shown == "0.47 (29 over 62)"
    assert nine["rebases"].met is False


def test_time_to_green_is_11_minutes_over_the_62_merged_pull_requests(nine):
    """The plan's 33 minutes was the 28 pull requests with a green local job; every merged pull
    request had a green job on one runner or the other."""
    assert (nine["green"].shown, nine["green"].n, nine["green"].runners) == (
        "11 min",
        62,
        "local 28, hosted 36",
    )


def test_main_was_red_43_minutes_on_the_16th_and_174_on_the_17th(facts):
    days = {
        day: numbers.mainred(facts, first, last).shown
        for day, first, last in numbers.day_windows(NOW, 3, UTC)
    }
    assert days == {"2026-10-15": "0 min", "2026-10-16": "43.2 min", "2026-10-17": "174 min"}


def test_staleness_only_rebases_are_22_of_38_where_the_plan_counted_21_by_hand(nine):
    assert nine["stale"].shown == "22 of 38"
    assert nine["stale"].met is False


def test_the_rule_finds_1_flaky_test_where_the_plan_named_9_by_hand(nine):
    """The relay test failed on js-item-model and jstack-help. The room test beside it in
    jstack-help's red failed there alone, so it is no flake."""
    assert (nine["flaky"].value, nine["flaky"].met) == (1.0, True)


def red(job, branch, *tests):
    at = iso(NOW - timedelta(hours=job))
    return {
        "job": job,
        "run": job,
        "attempt": 1,
        "branch": branch,
        "event": "pull_request",
        "kind": "local",
        "conclusion": "failure",
        "steps": 3,
        "sha": f"{job:040d}",
        "created": at,
        "started": at,
        "completed": at,
        "tests": list(tests),
        "signs": [],
    }


def test_a_test_that_failed_on_one_branch_is_no_flake_beside_one_that_failed_on_two():
    jobs = [red(1, "beta", "test_both", "test_beta_only"), red(2, "gamma", "test_both")]
    found = numbers.flaky(numbers.Facts(jobs, [], [], NOW), START, NOW)
    assert (found.value, found.shown, found.n) == (1.0, "1", 2)


@pytest.mark.parametrize("mac", ["macos", "macos 2 of 3"])
def test_numbers_count_a_red_macos_job_on_main_as_no_red_main(mac):
    """macos.yml runs on each push to main, beside main's check, and is never main's check:
    neither its job `macos` nor a part `macos K of N` of its Mac tests."""
    jobs = [
        hosted(1, "m1", "main", "success", event="push"),
        hosted(2, "m1", "main", "failure", event="push", name=mac, tests=["tests/test_m.py"]),
        hosted(3, "m1", "main", "success", event="push", name="macos-select"),
    ]
    facts = numbers.Facts(jobs, [], [], NOW)
    assert facts.intervals == []
    assert numbers.mainred(facts, NOW - timedelta(days=7), NOW).shown == "0 min"


def test_numbers_end_no_red_main_at_a_green_macos_job():
    red_at = NOW - timedelta(days=1) + timedelta(minutes=6)
    jobs = [
        hosted(0, "m1", "main", "failure", event="push"),
        hosted(1, "m2", "main", "success", event="push", name="macos"),
    ]
    assert numbers.Facts(jobs, [], [], NOW).intervals == [(red_at, NOW)]


def test_the_macos_yml_job_names_are_one_list_in_jbus_watch():
    """`jbus.ci.numbers` judges main's runs by the test `jbus.watch` judges main by, not a copy."""
    src = Path(watch.__file__).parent
    defined = [
        str(path.relative_to(src))
        for path in sorted(src.rglob("*.py"))
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MAC_JOBS" for t in node.targets)
    ]
    assert defined == ["watch.py"]
    assert numbers.mac_job is watch.mac_job and numbers.MAC_PART is watch.MAC_PART


def test_no_inode_figure_is_kept_until_a_job_writes_one(nine):
    assert (nine["inode"].value, nine["inode"].shown, nine["inode"].met) == (None, "no data", None)


def hosted(job, sha, branch, conclusion, *, pr=None, event="pull_request", tests=(), **more):
    """A job of a GitHub-hosted runner that ran, created at `NOW - 1 day + job minutes`."""
    created = NOW - timedelta(days=1) + timedelta(minutes=job)
    return {
        "run": job,
        "job": job,
        "attempt": 1,
        "name": "check",
        "sha": sha,
        "branch": branch,
        "pr": pr,
        "event": event,
        "created": iso(created),
        "started": iso(created + timedelta(minutes=1)),
        "completed": iso(created + timedelta(minutes=6)),
        "conclusion": conclusion,
        "runner": f"GitHub Actions {job}",
        "kind": "hosted",
        "steps": 5,
        "tests": list(tests),
        "signs": [],
        **dict.fromkeys(ledger.TELEMETRY),
        **more,
    }


def test_a_week_of_hosted_jobs_only_has_a_number_for_each_of_the_nine_targets_and_says_so():
    flaky_test = "tests/test_a.py::test_b"
    jobs = [
        hosted(1, "h1", "one", "success", pr=1, tmp_inode_pct=40),
        hosted(2, "h2", "two", "failure", pr=2, tests=[flaky_test]),
        hosted(3, "h3", "three", "failure", pr=3, tests=[flaky_test]),
        hosted(4, "h4", "four", "failure", pr=4, tests=["tests/test_c.py::test_d"]),
        hosted(5, "m1", "main", "success", event="push"),
    ]
    merged = iso(NOW - timedelta(hours=12))
    pulls = [
        {
            "number": 1,
            "branch": "one",
            "head": "h1",
            "created": iso(NOW - timedelta(days=2)),
            "merged": merged,
            "closed": merged,
            "merge_commit": "m1",
            "pushes": [iso(NOW - timedelta(hours=20))],
        }
    ]
    week = numbers.compute(numbers.Facts(jobs, pulls, [], NOW), NOW - timedelta(days=7), NOW)
    assert [(one.key, one.shown) for one in week if one.key not in HEALTH] == [
        ("queue", "1 vs 5 min"),
        ("waste", "60.0%"),
        ("own", "33% (1 of 3: 1 own, 2 flake)"),
        ("rebases", "1.00 (1 over 1)"),
        ("stale", "0 of 1"),
        ("green", "6 min"),
        ("mainred", "0 min"),
        ("flaky", "1"),
        ("inode", "40%"),
    ]
    jobs_of = {one.key: one.runners for one in week}
    assert jobs_of["queue"] == "hosted 2"
    assert jobs_of["waste"] == "hosted 5"
    assert jobs_of["own"] == jobs_of["flaky"] == "hosted 3"
    assert jobs_of["green"] == jobs_of["inode"] == "hosted 1"
    assert jobs_of["rebases"] == jobs_of["stale"] == "pull requests, any runner"
    text = report.body(
        numbers.Facts(jobs, pulls, [], NOW),
        week,
        NOW - timedelta(days=7),
        NOW,
        UTC,
        report.jsettings.DEFAULTS,
    )
    assert "| queue p50 under exec p50 | 1 vs 5 min | hosted 2 | queue under exec | met |" in text
    table = text.split("## Counted")[0].splitlines()
    assert [row for row in table if row.endswith("| no data |")] == [
        "| shard queue wait p90 | no data | - | baseline | no data |",
        "| macos queue wait p90 | no data | - | baseline | no data |",
    ]


def test_every_number_says_how_it_was_counted(nine):
    for one in nine.values():
        assert one.how and one.target and one.name
    assert "job level" in nine["queue"].how
    assert all(one.runners for one in nine.values() if one.value is not None)
    assert "cancelled while it waited" in nine["queue"].how


def test_a_target_with_no_job_in_the_window_has_no_data_and_is_not_missed(facts):
    nothing = numbers.compute(facts, START - timedelta(days=60), START - timedelta(days=59))
    assert [one.shown for one in nothing] == ["no data"] * len(numbers.ALL)
    assert [one.met for one in nothing] == [None] * len(numbers.ALL)


def test_a_job_kept_once_is_not_added_by_a_second_run(kept, tmp_path):
    state, counts = kept
    assert counts.jobs == len(ledger.read(state / ledger.JOBS)) == 314
    again = collect.collect(Replay(), REPO, state, NOW, 14)
    assert again.jobs == 0
    assert len(ledger.read(state / ledger.JOBS)) == 314


def test_a_second_run_asks_for_the_jobs_of_no_run_it_has(kept):
    state, _ = kept
    asked = Replay()
    collect.collect(asked, REPO, state, NOW, 14)
    assert [path for path in asked.asked if "/jobs" in path] == []


def test_hosted_and_local_jobs_are_kept_apart_and_a_job_cancelled_while_queued_is_counted(kept):
    rows = ledger.read(kept[0] / ledger.JOBS)
    kinds = {(one["kind"], one["conclusion"]) for one in rows}
    assert ("hosted", "success") in kinds and ("local", "success") in kinds
    queued = [one for one in rows if one["conclusion"] == "cancelled" and one["started"] is None]
    assert queued and {one["kind"] for one in queued} >= {"local"}
    assert all(one["runner"] is None for one in queued)


def test_a_row_has_the_ids_the_sha_the_pull_request_the_event_and_the_three_times(kept):
    rows = ledger.read(kept[0] / ledger.JOBS)
    row = next(
        one
        for one in rows
        if one["pr"] and one["event"] == "pull_request" and one["kind"] == "local" and one["runner"]
    )
    for field in (
        "run",
        "job",
        "sha",
        "pr",
        "event",
        "created",
        "started",
        "completed",
        "conclusion",
        "runner",
        "kind",
    ):
        assert row[field] is not None


def test_a_job_the_run_gave_no_telemetry_has_every_lever_field_empty(kept):
    rows = ledger.read(kept[0] / ledger.JOBS)
    assert all(one[field] is None for one in rows for field in ledger.TELEMETRY)


def test_a_red_local_job_has_its_failing_tests_and_the_faults_its_log_shows(kept):
    rows = ledger.read(kept[0] / ledger.JOBS)
    red = [one for one in rows if one["conclusion"] == "failure" and one["kind"] == "local"]
    assert any(one["tests"] for one in red)
    assert any("bus" in one["signs"] for one in red)


def annotation(**given):
    return {
        "annotation_level": "notice",
        "title": "jstack-ci",
        "message": json.dumps(given),
    }


def test_a_jobs_telemetry_is_read_back_from_its_annotation_and_a_stranger_is_left_out(tmp_path):
    base = Replay()
    ran = next(
        job
        for jobs in base.jobs.values()
        for job in jobs
        if job["steps"]
        and job["conclusion"] == "success"
        and collect.kind(job["labels"]) == "local"
    )
    said = {
        ran["id"]: [
            annotation(
                full=True,
                tree="abc",
                selection="all",
                reason="no map",
                slowest_s=41.5,
                tail_s=12.0,
                cpu_pressure="some avg10=0.00",
                cgroup_pressure="some avg10=0.10",
                workers=4,
                stranger="x",
            ),
            {"annotation_level": "notice", "title": "other", "message": '{"full": false}'},
        ]
    }
    collect.collect(Replay(said), REPO, tmp_path, NOW, 14)
    row = next(one for one in ledger.read(tmp_path / ledger.JOBS) if one["job"] == ran["id"])
    assert {field: row[field] for field in ledger.TELEMETRY if row[field] is not None} == {
        "full": True,
        "tree": "abc",
        "selection": "all",
        "reason": "no map",
        "slowest_s": 41.5,
        "tail_s": 12.0,
        "cpu_pressure": "some avg10=0.00",
        "cgroup_pressure": "some avg10=0.10",
        "workers": 4,
    }
    assert "stranger" not in row


def test_the_inode_peak_is_the_highest_a_job_wrote(tmp_path):
    base = Replay()
    jobs = [
        job
        for each in base.jobs.values()
        for job in each
        if job["steps"]
        and job["conclusion"] == "success"
        and collect.kind(job["labels"]) == "local"
    ][:2]
    said = {
        jobs[0]["id"]: [annotation(tmp_inode_pct=33)],
        jobs[1]["id"]: [annotation(tmp_inode_pct=61.5)],
    }
    collect.collect(Replay(said), REPO, tmp_path, NOW, 14)
    rows = ledger.read(tmp_path / ledger.JOBS)
    peak = numbers.inode(numbers.Facts(rows, [], [], NOW), START, NOW)
    assert (peak.shown, peak.met) == ("61.5%", True)


def test_a_red_job_whose_log_could_not_be_read_is_kept_unread_and_is_never_the_pull_requests_own(
    tmp_path,
):
    class NoLogs(Replay):
        def log(self, repo, job):
            raise Unavailable("down")

    collect.collect(NoLogs(), REPO, tmp_path, NOW, 14)
    rows = ledger.read(tmp_path / ledger.JOBS)
    red = [one for one in rows if one["conclusion"] == "failure" and one["kind"] == "local"]
    assert len(rows) == 314 and red and all(one["tests"] is None for one in red)
    one = numbers.own(numbers.Facts(rows, [], [], NOW), START, NOW)
    assert (one.value, one.met) == (0.0, False) and "68 unread" in one.shown


FAILED_LOG = "2026-10-17T20:00:00.1Z FAILED tests/test_a.py::test_b - boom\n"


BEFORE = ("logged", "step")
"""The fields a red kept before the collector read hosted logs and failed steps lacks."""


def a_hosted_red():
    base = Replay()
    return next(
        job
        for jobs in base.jobs.values()
        for job in jobs
        if job["steps"]
        and job["conclusion"] == "failure"
        and collect.kind(job["labels"]) == "hosted"
    )


class HostedLog(Replay):
    """The recording, with a log for one red hosted job, and the logs it was asked for."""

    def __init__(self, job):
        super().__init__()
        self.logs[str(job)] = FAILED_LOG
        self.read = []

    def log(self, repo, job):
        self.read.append(job)
        return super().log(repo, job)


def test_a_red_job_on_a_hosted_runner_has_the_failing_tests_its_log_names(tmp_path):
    red = a_hosted_red()
    collect.collect(HostedLog(red["id"]), REPO, tmp_path, NOW, 14)
    row = next(one for one in ledger.read(tmp_path / ledger.JOBS) if one["job"] == red["id"])
    assert (row["kind"], row["tests"], row["logged"]) == (
        "hosted",
        ["tests/test_a.py::test_b"],
        True,
    )


def test_a_hosted_red_kept_before_its_log_was_read_is_read_once_by_the_next_collect(tmp_path):
    red = a_hosted_red()
    collect.collect(Replay(), REPO, tmp_path, NOW, 14)
    rows = ledger.read(tmp_path / ledger.JOBS)
    older = [{k: v for k, v in one.items() if k not in BEFORE} | {"tests": []} for one in rows]
    ledger.rewrite(tmp_path / ledger.JOBS, older)
    gh = HostedLog(red["id"])
    collect.collect(gh, REPO, tmp_path, NOW, 14)
    after = {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)}
    assert after[red["id"]]["tests"] == ["tests/test_a.py::test_b"]
    reds = [
        one
        for one in after.values()
        if one["conclusion"] == "failure" and one["steps"] and one["kind"] == "hosted"
    ]
    assert len(after) == len(rows) and after[red["id"]]["logged"] is True
    assert all("logged" not in one for one in reds if one["job"] != red["id"])
    assert red["id"] in gh.read
    again = HostedLog(red["id"])
    collect.collect(again, REPO, tmp_path, NOW, 14)
    assert red["id"] not in again.read
    assert sorted(again.read) == sorted(one["job"] for one in reds if one["job"] != red["id"])


def test_a_re_read_keeps_what_a_local_red_held_and_retries_a_log_github_did_not_give(tmp_path):
    """A red kept before `step` is read again, and one whose log GitHub did not give now is left
    as it was, a local red with the tests it held, for the next collect."""
    red = a_hosted_red()
    collect.collect(Replay(), REPO, tmp_path, NOW, 14)
    rows = ledger.read(tmp_path / ledger.JOBS)
    older = [{k: v for k, v in one.items() if k not in BEFORE} for one in rows]
    for one in older:
        if one["job"] == red["id"]:
            one["tests"] = []
    ledger.rewrite(tmp_path / ledger.JOBS, older)
    local = {
        one["job"]: one["tests"]
        for one in older
        if one["kind"] == "local" and one["conclusion"] == "failure" and one["steps"]
    }

    class Down(HostedLog):
        def log(self, repo, job):
            self.read.append(job)
            raise Unavailable("down")

    down = Down(red["id"])
    collect.collect(down, REPO, tmp_path, NOW, 14)
    after = {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)}
    assert local and {job: after[job]["tests"] for job in local} == local
    assert set(local) <= set(down.read) and red["id"] in down.read
    assert "logged" not in after[red["id"]] and after[red["id"]]["tests"] == []
    gh = HostedLog(red["id"])
    collect.collect(gh, REPO, tmp_path, NOW, 14)
    row = next(one for one in ledger.read(tmp_path / ledger.JOBS) if one["job"] == red["id"])
    assert (row["tests"], row["logged"]) == (["tests/test_a.py::test_b"], True)


FAILED_RUNS = FOLDER.parent / "failed-runs"
FAILED_AT = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)
TIMED_OUT = (
    "features/crew/tests/test_crew_check_command.py::"
    "test_a_change_to_one_feature_runs_its_guards_in_a_full_slot_then_the_rest_in_a_short_one"
)


class FailedRuns(Replay):
    """Two red shards of jstack's check, recorded on 2026-11-04: one that failed a test in
    `make test`, and one that failed `make check-fast` at its `lint` target before a test ran
    (`fixtures/ci/failed-runs`)."""

    def __init__(self):
        super().__init__()
        for name in ("runs", "jobs", "logs"):
            setattr(self, name, json.loads((FAILED_RUNS / f"{name}.json").read_text()))
        self.pulls, self.pushes, self.read = [], {}, []

    def log(self, repo, job):
        self.read.append(job)
        return super().log(repo, job)


def test_failed_tests_or_the_failed_step_is_kept_for_each_red_shard(tmp_path):
    collect.collect(FailedRuns(), REPO, tmp_path, FAILED_AT, 1)
    rows = {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)}
    assert (rows[126596643643]["tests"], rows[126596643643]["step"]) == ([TIMED_OUT], "make test")
    assert (rows[126315030200]["tests"], rows[126315030200]["step"]) == (
        [],
        "make check-fast: lint",
    )


def test_failed_tests_a_red_kept_before_its_step_is_read_once_more_for_it(tmp_path):
    collect.collect(FailedRuns(), REPO, tmp_path, FAILED_AT, 1)
    rows = ledger.read(tmp_path / ledger.JOBS)
    fresh = {one["job"]: one for one in rows}
    older = [{k: v for k, v in one.items() if k != "step"} | {"tests": []} for one in rows]
    ledger.rewrite(tmp_path / ledger.JOBS, older)
    gh = FailedRuns()
    collect.collect(gh, REPO, tmp_path, FAILED_AT, 1)
    assert {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)} == fresh
    assert sorted(gh.read) == sorted(fresh)
    again = FailedRuns()
    collect.collect(again, REPO, tmp_path, FAILED_AT, 1)
    assert again.read == []


def test_failed_tests_a_red_whose_run_github_did_not_list_is_left_for_the_next_collect(tmp_path):
    collect.collect(FailedRuns(), REPO, tmp_path, FAILED_AT, 1)
    rows = ledger.read(tmp_path / ledger.JOBS)
    fresh = {one["job"]: one for one in rows}
    older = [{k: v for k, v in one.items() if k != "step"} | {"tests": []} for one in rows]
    ledger.rewrite(tmp_path / ledger.JOBS, older)

    class NoJobs(FailedRuns):
        def pages(self, path, key=None):
            if "/jobs" in path:
                raise Unavailable("down")
            return super().pages(path, key)

    down = NoJobs()
    collect.collect(down, REPO, tmp_path, FAILED_AT, 1)
    assert ledger.read(tmp_path / ledger.JOBS) == older and down.read == []
    collect.collect(FailedRuns(), REPO, tmp_path, FAILED_AT, 1)
    assert {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)} == fresh


def test_failed_tests_a_red_whose_log_github_did_not_give_still_names_its_step(tmp_path):
    class NoLogs(FailedRuns):
        def log(self, repo, job):
            raise Unavailable("down")

    collect.collect(NoLogs(), REPO, tmp_path, FAILED_AT, 1)
    rows = {one["job"]: one for one in ledger.read(tmp_path / ledger.JOBS)}
    assert {job: (one["tests"], one["step"]) for job, one in rows.items()} == {
        126596643643: (None, "make test"),
        126315030200: (None, "make check-fast"),
    }


def test_a_log_with_colour_codes_gives_the_same_evidence_as_one_without():
    plain = "2026-10-17T20:00:00.1Z FAILED tests/test_a.py::test_b - boom\n"
    coloured = "2026-10-17T20:00:00.1Z \x1b[31mFAILED\x1b[0m tests/test_a.py::test_b - boom\n"
    assert collect.evidence(coloured) == collect.evidence(plain)
    assert collect.failing_tests(collect.evidence(coloured)) == ["tests/test_a.py::test_b"]


def test_a_pass_reads_the_logs_of_its_red_jobs_at_one_moment_and_keeps_what_it_kept_one_by_one(
    tmp_path,
):
    """Each log read waits until as many reads as the pass runs at one moment have begun, so a
    collector that read them one by one would wait 5 s on each. What it keeps is what the
    collector kept when it read them one by one."""

    class Red(Replay):
        """The recording's runs that have a red job on a local runner."""

        def __init__(self):
            super().__init__()
            red = {
                str(job["run_id"])
                for jobs in self.jobs.values()
                for job in jobs
                if str(job["id"]) in self.logs
            }
            self.runs = [run for run in self.runs if str(run["id"]) in red]
            self.reads, self.reading, self.peak = 0, 0, 0
            self.moment = threading.Condition()

        def log(self, repo, job):
            with self.moment:
                self.reads += 1
                self.reading += 1
                self.peak = max(self.peak, self.reading)
                self.moment.notify_all()
                self.moment.wait_for(
                    lambda: self.reading >= passes.WIDE or self.reads == 42, timeout=5
                )
            try:
                return super().log(repo, job)
            finally:
                with self.moment:
                    self.reading -= 1

    gh = Red()
    counts = collect.keep(gh, REPO, tmp_path, NOW)
    rows = ledger.read(tmp_path / ledger.JOBS)
    red = [one for one in rows if one["tests"] is not None and one["conclusion"] == "failure"]
    assert gh.peak == passes.WIDE
    assert (counts.runs, counts.jobs, counts.pulls, gh.reads) == (37, 44, 4, 42)
    assert len(red) == 42 and sum(1 for one in red if one["tests"]) == 40
    assert sorted({sign for one in red for sign in one["signs"]}) == ["browser", "bus", "space"]


def test_the_notice_a_job_prints_is_the_annotation_the_collector_reads(tmp_path):
    printed = notice.write(
        ["full=true", "tree=abc", "workers=4", "slowest_s=41.5", "cpu_pressure=some avg10=0.00 x=1"]
    )
    title, _, message = printed.removeprefix("::notice title=").partition("::")
    assert title == "jstack-ci"
    assert json.loads(message) == {
        "full": True,
        "tree": "abc",
        "workers": 4,
        "slowest_s": 41.5,
        "cpu_pressure": "some avg10=0.00 x=1",
    }


@pytest.mark.parametrize(
    "pairs,kept",
    [
        (["selection=212"], {"selection": 212, "reason": None}),
        (
            ["selection=all", "reason=pyproject.toml"],
            {"selection": "all", "reason": "pyproject.toml"},
        ),
    ],
)
def test_the_selection_a_check_notices_is_kept_on_its_row(tmp_path, pairs, kept):
    """The full suite step of a pull request's check notices how many test files it selected,
    or `all` and the path that forced it, and the collector keeps that on the job's row."""
    base = Replay()
    ran = next(
        job
        for jobs in base.jobs.values()
        for job in jobs
        if job["steps"] and job["conclusion"] == "success"
    )
    printed = notice.write(["full=false", "tree=abc", *pairs])
    title, _, message = printed.removeprefix("::notice title=").partition("::")
    said = {ran["id"]: [{"annotation_level": "notice", "title": title, "message": message}]}
    collect.collect(Replay(said), REPO, tmp_path, NOW, 14)
    row = next(one for one in ledger.read(tmp_path / ledger.JOBS) if one["job"] == ran["id"])
    assert {field: row[field] for field in kept} == kept


def test_a_field_the_ledger_does_not_have_is_refused(tmp_path):
    with pytest.raises(notice.Refused, match="not a field of ci.jsonl"):
        notice.write(["fulll=true"])
    with pytest.raises(notice.Refused, match="not field=value"):
        notice.write(["full"])


def test_a_job_summary_gets_the_fields_as_a_table(tmp_path):
    summary = tmp_path / "summary.md"
    notice.write(["full=false", "workers=4"], summary)
    assert "| workers | 4 |" in summary.read_text() and "| full | False |" in summary.read_text()


def test_the_verb_prints_the_notice_and_needs_no_config(kitchen, monkeypatch):
    monkeypatch.delenv("JBUS_CONFIG_DIR", raising=False)
    code, said = kitchen.main("ci", "--notice", "full=true", "workers=2")
    assert code == 0 and said == '::notice title=jstack-ci::{"full":true,"workers":2}\n'
    code, said = kitchen.main("ci", "--notice", "nope=1")
    assert code == 2 and said.startswith("refused: nope is not a field")


def test_the_week_report_says_every_number_with_how_it_was_counted(facts, nine):
    text = report.body(
        facts, list(nine.values()), NOW - timedelta(days=7), NOW, UTC, report.jsettings.DEFAULTS
    )
    assert "Job level only" in text and "its runners column says which" in text
    assert "| 0 vs 8.22 min | local 75, hosted 120 |" in text
    assert "cancelled while it waited" in text
    for one in nine.values():
        assert f"**{one.name}**" in text
    assert "- local:" in text and "- hosted:" in text
    assert "2026-10-16: 43.2 min" in text


def test_only_a_missed_target_is_missed(nine):
    assert [one.key for one in report.missed(list(nine.values()))] == [
        "waste",
        "own",
        "rebases",
        "stale",
    ]


def test_a_week_with_a_target_missed_alerts_once_and_a_week_without_alerts_nobody(
    kitchen, nine, tmp_path
):
    import jbus

    config = jbus.load()
    project = config.projects[0]
    said = []
    path = tmp_path / "ci-week.md"
    met = [one for one in nine.values() if one.met is not False]
    assert report.escalate(config, project, met, path, KITCHEN_NOW, said.append) == 0
    assert kitchen.wakes.said == [] and said == ["ci: every target met or without data, no alert"]
    late = list(nine.values())
    report.escalate(config, project, late, path, KITCHEN_NOW, said.append)
    report.escalate(config, project, late, path, KITCHEN_NOW, said.append)
    kitchen.poll(KITCHEN_NOW)
    (line,) = kitchen.wakes.said
    assert "missed" in line and "wasted-minute share 37.1%" in line
    assert "flaky tests" not in line and str(path) in line


def unit(name):
    read = configparser.ConfigParser(interpolation=None)
    read.optionxform = str
    read.read(CHECKOUT / "features" / "jbus" / "units" / name)
    return read


def fire(zone, name="jbus-ci.timer"):
    """The next three times the timer `name` fires after 2026-10-18 on a machine in `zone`, in
    UTC, as systemd counts them."""
    asked = subprocess.run(
        [
            "systemd-analyze",
            "calendar",
            "--base-time=2026-10-18",
            "--iterations=3",
            unit(name)["Timer"]["OnCalendar"],
        ],
        capture_output=True,
        text=True,
        env={"TZ": zone, "PATH": os.environ["PATH"]},
    )
    assert asked.returncode == 0, asked.stderr
    return [line.split(": ", 1)[1] for line in asked.stdout.splitlines() if "(in UTC)" in line]


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="no systemd-analyze")
def test_the_timer_runs_every_monday_at_nine_in_the_machines_own_zone():
    tokyo, new_york = fire("Asia/Tokyo"), fire("America/New_York")
    assert len(tokyo) == 3 and all(one.startswith("Mon ") for one in tokyo)
    assert [one.split()[2] for one in tokyo] == ["00:00:00", "00:00:00", "00:00:00"]
    assert [one.split()[2] for one in new_york] == ["13:00:00", "13:00:00", "14:00:00"]
    timer = unit("jbus-ci.timer")
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def service(kitchen, monkeypatch):
    """Run the command of `jbus-ci.service` in the kitchen, with GitHub's recorded answers,
    and return its exit code, what it printed, and the kitchen's project."""
    command = shlex.split(unit("jbus-ci.service")["Service"]["ExecStart"])
    assert command[0].endswith("/.local/bin/jbus")
    import jbus

    project = jbus.load().projects[0]
    monkeypatch.setattr(collect, "Cli", Replay)
    subprocess.run(
        [
            "git",
            "-C",
            str(project.checkout),
            "remote",
            "set-url",
            "origin",
            f"https://{HOST}/{REPO}.git",
        ],
        check=True,
    )
    code, said = kitchen.main(*command[1:])
    return code, said, project


def test_the_service_writes_no_report_and_alerts_nobody_where_no_project_asks_for_one(
    kitchen, monkeypatch
):
    asked = []
    monkeypatch.setattr(Replay, "pages", lambda self, *args: asked.append(args) or [])

    code, said, project = service(kitchen, monkeypatch)

    assert (code, said.strip()) == (0, "ci: no project asks for the week's report (ci_report)")
    assert asked == [] and kitchen.wakes.said == []
    assert not (jbus_home(project) / "reports").exists()


def test_the_service_collects_and_writes_the_report_of_each_project_that_asks_for_one(
    kitchen, monkeypatch
):
    other = kitchen.second()
    path = kitchen.config_dir / "config.toml"
    path.write_text(
        path.read_text().replace('state = "demo"\n', 'state = "demo"\nci_report = true\n')
    )

    code, said, project = service(kitchen, monkeypatch)

    assert code == 0, said
    assert list((jbus_home(project) / "reports").glob("ci-week-*.md"))
    assert not (other.home / "reports").exists()
    assert f"ci: {project.name}, the last 14 days" in said and "ci: other" not in said


def test_each_project_and_a_named_project_together_are_refused(kitchen):
    code, said = kitchen.main("--project", "demo", "ci", "--report", "--each")
    assert (code, said.strip()) == (2, "refused: --each is every project that asks, not --project")


def jbus_home(project):
    import jbus

    return jbus.load().home(project)


def test_a_second_collector_waits_for_the_first_and_then_adds_nothing(tmp_path):
    inside, release = threading.Event(), threading.Event()

    class Held(Replay):
        def pages(self, path, key=None):
            inside.set()
            release.wait(10)
            return super().pages(path, key)

    counts = {}

    def run(name, gh):
        counts[name] = collect.collect(gh, REPO, tmp_path, NOW, 14)

    first = threading.Thread(target=run, args=("first", Held()))
    first.start()
    assert inside.wait(10)
    second = threading.Thread(target=run, args=("second", Replay()))
    second.start()
    second.join(0.5)
    assert second.is_alive()
    release.set()
    first.join(30)
    second.join(30)
    assert (counts["first"].jobs, counts["second"].jobs) == (314, 0)
    assert len(ledger.read(tmp_path / ledger.JOBS)) == 314


@pytest.mark.parametrize("value", ['"yes"', "1"])
def test_a_ci_report_that_is_not_true_or_false_is_refused(kitchen, value):
    path = kitchen.config_dir / "config.toml"
    path.write_text(
        path.read_text().replace('state = "demo"\n', f'state = "demo"\nci_report = {value}\n')
    )

    code, said = kitchen.main("ci", "--report", "--each")

    assert (code, said.strip()) == (
        1,
        "refused: project demo has a ci_report that is not true or false",
    )


def test_a_pass_asks_for_the_runs_of_its_last_hours_and_keeps_at_most_its_share_of_new_runs(
    tmp_path,
):
    asked = Replay()
    counts = collect.keep(asked, REPO, tmp_path, NOW)
    since = (NOW - timedelta(hours=collect.PASS_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (runs,) = [path for path in asked.asked if "/actions/runs?" in path]
    assert runs.endswith(f"&created=%3E%3D{since}")
    jobs = [path for path in asked.asked if path.endswith("/jobs?filter=all")]
    assert len(jobs) == collect.PASS_RUNS
    assert counts.jobs == len(ledger.read(tmp_path / ledger.JOBS)) > 0
    more = collect.keep(Replay(), REPO, tmp_path, NOW)
    assert more.jobs > 0
    assert len({one["job"] for one in ledger.read(tmp_path / ledger.JOBS)}) == (
        counts.jobs + more.jobs
    )


@pytest.mark.parametrize(
    ("gap", "kept"),
    [(timedelta(hours=1), 60), (timedelta(hours=6), 360), (timedelta(days=20), 14 * 24 * 60)],
    ids=["no gap", "a gap longer than the pass's hours", "a gap longer than jbus ci's days"],
)
def test_a_pass_keeps_every_pull_request_updated_since_the_newest_the_ledger_holds(
    tmp_path, gap, kept
):
    """`ci-prs.jsonl` is written on every merge: a pass that comes after a gap, longer than
    `PASS_HOURS`, keeps each pull request merged in it, back as far as `jbus ci` reads."""
    gh = Paged(15 * 24 * 60)
    stamp = (NOW - gap).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger.rewrite(tmp_path / ledger.PULLS, [{"number": 0, "updated": stamp}])
    collect.keep(gh, REPO, tmp_path, NOW)
    minutes = max(kept, collect.PASS_HOURS * 60)
    assert {one["number"] for one in ledger.read(tmp_path / ledger.PULLS)} == {
        0,
        *(one["number"] for one in gh.pulls[: minutes + 1]),
    }


def test_a_pass_keeps_nothing_and_does_not_wait_while_jbus_ci_holds_the_ledger(tmp_path):
    inside, release = threading.Event(), threading.Event()

    class Held(Replay):
        def page(self, path, key=None):
            inside.set()
            release.wait(10)
            return super().page(path, key)

    weekly = threading.Thread(target=collect.collect, args=(Held(), REPO, tmp_path, NOW, 14))
    weekly.start()
    try:
        assert inside.wait(10)
        asked = Replay()
        assert collect.keep(asked, REPO, tmp_path, NOW) is None
        assert asked.asked == []
    finally:
        release.set()
        weekly.join(30)
    assert len(ledger.read(tmp_path / ledger.JOBS)) == 314


def test_a_pull_request_kept_at_the_same_update_is_not_asked_for_its_timeline_again(tmp_path):
    class Updated(Replay):
        def __init__(self, changed=()):
            super().__init__()
            for one in self.pulls:
                moved = one["number"] in changed
                one["updated_at"] = "2026-10-17T21:00:00Z" if moved else "2026-10-17T20:00:00Z"

    def timelines(gh):
        return {int(path.split("/")[-2]) for path in gh.asked if "/timeline" in path}

    first = Updated()
    collect.collect(first, REPO, tmp_path, NOW, 14)
    assert len(timelines(first)) == 71
    kept = {one["number"]: one for one in ledger.read(tmp_path / ledger.PULLS)}
    pushed = next(number for number, one in kept.items() if one["pushes"])
    again = Updated(changed={pushed})
    collect.collect(again, REPO, tmp_path, NOW, 14)
    assert timelines(again) == {pushed}
    after = {one["number"]: one for one in ledger.read(tmp_path / ledger.PULLS)}
    assert {n: one["pushes"] for n, one in after.items()} == {
        n: one["pushes"] for n, one in kept.items()
    }
    assert after[pushed]["updated"] == "2026-10-17T21:00:00Z"


def test_a_pull_request_with_no_update_time_is_asked_for_its_timeline_each_time(kept):
    state, _ = kept
    asked = Replay()
    collect.collect(asked, REPO, state, NOW, 14)
    assert len([path for path in asked.asked if "/timeline" in path]) == 71


class Paged:
    """GitHub's pull requests in pages of `collect.PAGE`, the latest update first: the `n`th is
    updated `n` minutes before `NOW`. It counts each page it is asked for."""

    def __init__(self, many):
        def stamp(minutes):
            return (NOW - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

        self.pulls = [
            {
                "number": many - n,
                "head": {"ref": f"pie-{n}", "sha": "a" * 40},
                "created_at": stamp(n + 1),
                "updated_at": stamp(n),
            }
            for n in range(many)
        ]
        self.asked = []

    def page(self, path, key=None):
        number = int(path.rsplit("&page=", 1)[1])
        self.asked.append(number)
        return self.pulls[(number - 1) * collect.PAGE : number * collect.PAGE]

    def pages(self, path, key=None):
        return []


@pytest.mark.parametrize(
    ("many", "minutes", "kept", "asked"),
    [(250, 300, 250, [1, 2, 3]), (300, 149.5, 150, [1, 2]), (200, 300, 200, [1, 2, 3])],
    ids=["a short last page", "a page that reaches back past the window", "an empty last page"],
)
def test_the_pull_requests_are_read_a_page_at_a_time_up_to_the_window(many, minutes, kept, asked):
    gh = Paged(many)
    found = collect.pulls(gh, REPO, NOW - timedelta(minutes=minutes))
    assert [one["number"] for one in found] == [one["number"] for one in gh.pulls[:kept]]
    assert gh.asked == asked


@pytest.mark.parametrize(
    "said",
    ['{"workflow_runs": []}', "[[1, 2]]", '[{"jobs": []}]', "not json"],
    ids=["not a list of pages", "not objects", "no such key", "not json"],
)
def test_an_answer_of_another_shape_is_github_not_answering(said):
    def ask(command):
        return subprocess.CompletedProcess(command, 0, said, "")

    with pytest.raises(Unavailable):
        collect.Cli(ask).pages("repos/o/r/actions/runs?per_page=100", "workflow_runs")


def test_every_pass_keeps_the_ci_ledger_of_a_project_that_asks_for_its_report(kitchen):
    """A pass that stops keeping `ci.jsonl` leaves the view and `jbus flow` a ledger that ages:
    each pass adds the jobs of the runs that completed since the one before."""
    kitchen.config(own=("ci_report = true",))

    def ran(number, job):
        return {
            "id": number,
            "event": "pull_request",
            "head_branch": "pie",
            "head_sha": "a" * 40,
            "run_attempt": 1,
            "created_at": iso(KITCHEN_NOW - timedelta(minutes=20)),
            "status": "completed",
            "conclusion": "failure",
            "pull_requests": [{"number": 7}],
        }, {
            "id": job,
            "run_attempt": 1,
            "name": "check",
            "head_sha": "a" * 40,
            "status": "completed",
            "conclusion": "failure",
            "created_at": iso(KITCHEN_NOW - timedelta(minutes=20)),
            "started_at": iso(KITCHEN_NOW - timedelta(minutes=19)),
            "completed_at": iso(KITCHEN_NOW - timedelta(minutes=10)),
            "labels": ["ubuntu-latest"],
            "runner_name": "GitHub Actions 1",
            "steps": [{"name": "make check"}],
        }

    first, second = ran(501, 9001), ran(502, 9002)
    kitchen.set("runs.json", {"workflow_runs": [first[0]]})
    kitchen.set("run-jobs.json", {"501": [first[1]]})
    kitchen.poll()
    jobs = ledger.read(kitchen.state / ledger.JOBS)
    assert [(one["job"], one["pr"], one["conclusion"]) for one in jobs] == [(9001, 7, "failure")]
    kitchen.set("runs.json", {"workflow_runs": [second[0], first[0]]})
    kitchen.set("run-jobs.json", {"501": [first[1]], "502": [second[1]]})
    kitchen.poll()
    assert [one["job"] for one in ledger.read(kitchen.state / ledger.JOBS)] == [9001, 9002]


def test_a_ledger_the_pass_cannot_write_is_said_and_the_pass_still_launches(kitchen):
    """Keeping the ledger is bookkeeping: a state directory where `ci.jsonl` cannot be written
    costs the pass that one line, never its launches."""
    kitchen.config(own=("ci_report = true",))
    run, job = (
        {
            "id": 501,
            "event": "pull_request",
            "head_branch": "pie",
            "head_sha": "a" * 40,
            "run_attempt": 1,
            "created_at": iso(KITCHEN_NOW - timedelta(minutes=20)),
            "status": "completed",
            "conclusion": "success",
            "pull_requests": [{"number": 7}],
        },
        {
            "id": 9001,
            "run_attempt": 1,
            "name": "check",
            "head_sha": "a" * 40,
            "status": "completed",
            "conclusion": "success",
            "created_at": iso(KITCHEN_NOW - timedelta(minutes=20)),
            "started_at": iso(KITCHEN_NOW - timedelta(minutes=19)),
            "completed_at": iso(KITCHEN_NOW - timedelta(minutes=10)),
            "labels": ["ubuntu-latest"],
            "runner_name": "GitHub Actions 1",
            "steps": [{"name": "make check"}],
        },
    )
    kitchen.set("runs.json", {"workflow_runs": [run]})
    kitchen.set("run-jobs.json", {"501": [job]})
    (kitchen.state / ledger.JOBS).mkdir(parents=True)
    queued(kitchen, "alpha")
    said = kitchen.poll()
    assert "launched alpha: mcp:thread-1" in said
    assert any(line.startswith("ci: demo: no job kept this pass: ") for line in said), said


def test_a_pass_keeps_no_ci_ledger_for_a_project_that_does_not_ask_for_its_report(kitchen):
    """`ci_report` is off unless the project's table says it, and a project that never asked
    gets no call to GitHub for its CI and no ledger in its state."""
    queued(kitchen, "alpha")
    said = kitchen.poll()
    assert "launched alpha: mcp:thread-1" in said
    asked = [line for line in kitchen.log("gh") if "pulls?state=all" in line or "created=" in line]
    assert asked == []
    assert not (kitchen.state / ledger.JOBS).exists()
    assert not (kitchen.state / ledger.PULLS).exists()
    assert not any(line.startswith("ci: ") for line in said), said


SLICE_START = datetime(2026, 11, 4, 4, 0, tzinfo=UTC)
"""The slice begins at 23:00 on Nov 3 in New York, an hour before midnight there."""
SLICE_NOW = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)
NEW_YORK = ZoneInfo("America/New_York")


def row(job, run, name, pr, sha, minute, *, wait=0, conclusion="success", tests=(), **more):
    """A ci.jsonl row created `minute` minutes into the slice, which waited `wait` seconds and ran
    5 minutes. A job that never started (skipped, or cancelled while it waited) has no start."""
    created = SLICE_START + timedelta(minutes=minute)
    started = None if conclusion == "skipped" or more.pop("queued", False) else created
    started = started and created + timedelta(seconds=wait)
    return {
        "run": run,
        "job": job,
        "attempt": 1,
        "name": name,
        "sha": sha,
        "branch": more.pop("branch", {10: "ten", 20: "twenty", 30: "thirty", 40: "forty"}.get(pr)),
        "pr": pr,
        "event": more.pop("event", "pull_request"),
        "created": iso(created),
        "started": started and iso(started),
        "completed": iso((started or created) + timedelta(minutes=5)),
        "conclusion": conclusion,
        "runner": started and f"GitHub Actions {job}",
        "kind": "hosted",
        "steps": 5 if started else 0,
        "tests": list(tests),
        "signs": [],
        **dict.fromkeys(ledger.TELEMETRY),
    }


OWN_TEST, SHARED_TEST = "tests/test_a.py::test_own", "tests/test_a.py::test_shared"
SLICE = [
    row(1, 101, "check", 10, "a1", 1, conclusion="failure"),
    row(2, 101, "check 1 of 8", 10, "a1", 1, wait=10, conclusion="failure", tests=[OWN_TEST]),
    row(3, 101, "macos 1 of 2", 10, "a1", 1, wait=100),
    row(4, 102, "check", 10, "a2", 30),
    row(5, 102, "check 1 of 8", 10, "a2", 30, wait=20),
    row(6, 103, "check", 10, "a3", 60),
    row(7, 103, "check 1 of 8", 10, "a3", 60, wait=30),
    row(8, 201, "check", 20, "b1", 11, conclusion="failure"),
    row(9, 201, "check 1 of 8", 20, "b1", 11, wait=40, conclusion="failure", tests=[SHARED_TEST]),
    row(10, 202, "check", 20, "b9", 40, conclusion="skipped"),
    row(11, 202, "check 1 of 8", 20, "b9", 40, conclusion="skipped"),
    row(12, 203, "check", 20, "b2", 50),
    row(13, 203, "check 1 of 8", 20, "b2", 50, wait=50),
    row(14, 301, "check", 30, "c1", 21, conclusion="failure"),
    row(15, 301, "check 1 of 8", 30, "c1", 21, wait=60, conclusion="failure", tests=[SHARED_TEST]),
    row(16, 302, "check", 30, "c2", 90, conclusion="cancelled", queued=True),
    row(17, 302, "check 1 of 8", 30, "c2", 90, conclusion="cancelled", queued=True),
    row(18, 401, "check", 40, "d1", 31),
    row(19, 401, "check 1 of 8", 40, "d1", 31, wait=1000),
    row(20, 401, "macos 2 of 2", 40, "d1", 31, wait=300),
    row(21, 501, "check 1 of 8", None, "m1", 5, wait=5000, event="push", branch="main"),
    row(22, 601, "check", None, "e1", 100, conclusion="failure", branch="dependabot"),
]
"""#10 is red at its first head for a test of its own, green at the crew's second, and green again
at the merge of main that jmerge asked GitHub for a minute after GitHub made it. #20 and #30 are red
on the same test, so neither red is its own; #20's draft head was skipped, and #30's second run was
cancelled while it waited. #40 is green at its first check, after the longest waits. A push to main
waits long and counts in no pull request's wait, and a red check of no pull request is no pull
request's red."""


def pull(number, opened, merged=None):
    return {
        "number": number,
        "branch": {10: "ten", 20: "twenty", 30: "thirty", 40: "forty"}[number],
        "head": None,
        "created": iso(SLICE_START + timedelta(minutes=opened)),
        "merged": merged and iso(SLICE_START + timedelta(minutes=merged)),
        "closed": merged and iso(SLICE_START + timedelta(minutes=merged)),
        "merge_commit": None,
        "pushes": [],
    }


def asked(number, minute):
    """jmerge's line for an update-branch it asked GitHub for."""
    return {
        "at": iso(SLICE_START + timedelta(minutes=minute)),
        "event": "jmerge",
        "id": f"ask{number}{minute}",
        "line": f"wait {number} https://github.com/JoshuaHayesWasHere/jstack/pull/{number}: GitHub"
        " was asked to merge main at abc123def456 into it: main moved after its check started",
        "loud": "quiet",
        "slug": f"#{number}",
        "text": "",
    }


@pytest.fixture
def sliced(tmp_path):
    """The facts of the fixed slice, read back from a ci.jsonl and a ci-prs.jsonl as jbus keeps
    them. #20 is also asked for a merge of main that GitHub never made."""
    jobs, pulls = tmp_path / ledger.JOBS, tmp_path / ledger.PULLS
    jobs.write_text("".join(json.dumps(one, sort_keys=True) + "\n" for one in SLICE))
    pulls.write_text(
        "".join(
            json.dumps(one) + "\n"
            for one in (pull(10, 0, 120), pull(20, 10, 370), pull(30, 20), pull(40, 30))
        )
    )
    return numbers.Facts(
        ledger.read(jobs), ledger.read(pulls), [asked(10, 61), asked(20, 200)], SLICE_NOW
    )


HEALTH = (
    "red_share",
    "shas_per_pr",
    "wait_p90_shard",
    "wait_p90_macos",
    "open_to_merge",
    "first_check_own_red",
)


def test_the_slice_gives_each_health_number_its_value_its_n_and_how_it_counts(sliced):
    found = {
        one.key: one for one in numbers.compute(sliced, SLICE_START - timedelta(hours=1), SLICE_NOW)
    }
    health = {key: (round(found[key].value, 6), found[key].shown, found[key].n) for key in HEALTH}
    assert health == {
        "red_share": (0.75, "75% (3 of 4: 1 own, 2 shared)", 4),
        "shas_per_pr": (2.0, "2.00 crew + 0.50 update = 2.50 (2 merged)", 2),
        "wait_p90_shard": (436.0, "436 s (p50 40 s)", 7),
        "wait_p90_macos": (280.0, "280 s (p50 200 s)", 2),
        "open_to_merge": (4.0, "4 h p50, 5.6 h p90", 2),
        "first_check_own_red": (0.25, "25% (1 of 4 first checks, 3 red)", 4),
    }
    for key in HEALTH:
        assert found[key].how and found[key].met is None, key


def test_the_macos_wait_counts_the_mac_parts_and_not_the_linux_gate_macos():
    """macos.yml's Mac runs are its parts, `macos K of N`; the required `macos` is a Linux job
    that waits for them, so its wait is no Mac's queue."""
    jobs = [
        row(1, 101, "macos 1 of 3", 10, "a1", 1, wait=40),
        row(2, 101, "macos 2 of 3", 10, "a1", 1, wait=60),
        row(3, 101, "macos 3 of 3", 10, "a1", 1, wait=80),
        row(4, 101, "macos", 10, "a1", 1, wait=900),
        row(5, 101, "macos-select", 10, "a1", 1, wait=700),
    ]
    found = numbers.wait_p90_macos(numbers.Facts(jobs, [], [], SLICE_NOW), SLICE_START, SLICE_NOW)
    assert (found.value, found.shown, found.n) == (76.0, "76 s (p50 60 s)", 3)


def test_the_health_numbers_have_no_data_in_a_window_with_nothing_in_it(sliced):
    found = numbers.compute(sliced, SLICE_NOW, SLICE_NOW + timedelta(days=1))
    assert [(one.shown, one.n) for one in found if one.key in HEALTH] == [("no data", 0)] * 6


def test_a_health_number_with_no_target_reads_baseline_in_the_report_and_raises_no_alert(sliced):
    week = numbers.compute(sliced, SLICE_NOW - timedelta(days=7), SLICE_NOW)
    text = report.body(
        sliced, week, SLICE_NOW - timedelta(days=7), SLICE_NOW, UTC, report.jsettings.DEFAULTS
    )
    assert (
        "| red share of active PRs | 75% (3 of 4: 1 own, 2 shared) | hosted 7 | baseline |" in text
    )
    assert "| baseline |\n" in text
    assert not {one.key for one in report.missed(week)} & set(HEALTH)


def test_the_report_counts_the_health_numbers_by_day_of_the_users_zone(sliced):
    """23:01 in New York is the 3rd there and the 4th in UTC."""
    window = (SLICE_NOW - timedelta(days=2), SLICE_NOW)
    two = numbers.compute(sliced, *window)

    def days(zone):
        text = report.body(sliced, two, *window, zone, report.jsettings.DEFAULTS)
        return [
            line.split(" | ")[:2] for line in text.splitlines() if line.startswith("| 2026-11-0")
        ]

    assert days(NEW_YORK) == [
        ["| 2026-11-03", "75% (3 of 4: 1 own, 2 shared)"],
        ["| 2026-11-04", "0% (0 of 1: 0 own, 0 shared)"],
    ]
    assert days(UTC) == [
        ["| 2026-11-03", "no data"],
        ["| 2026-11-04", "75% (3 of 4: 1 own, 2 shared)"],
    ]


def test_a_day_is_a_local_day_from_midnight_to_midnight_in_the_machines_zone(monkeypatch):
    """With no zone set, the day is the machine's: in New York, 2026-11-01 has 25 hours."""
    monkeypatch.setenv("TZ", "America/New_York")
    import time as clock

    clock.tzset()
    try:
        days = daily.days(jsettings.Settings(), date(2026, 10, 31), date(2026, 11, 2))
    finally:
        monkeypatch.undo()
        clock.tzset()
    hours = [(end - start) / timedelta(hours=1) for _, start, end in days]
    assert hours == [24, 25, 24]
    assert days[0][1] == datetime(2026, 10, 31, 4, tzinfo=UTC)


def test_a_days_main_red_spell_runs_from_a_failed_runs_creation_to_the_next_successs_update():
    def one(conclusion, created, updated, status="completed"):
        return {
            "conclusion": conclusion,
            "status": status,
            "createdAt": created,
            "updatedAt": updated,
            "headSha": "a" * 40,
        }

    runs = [
        one("success", "2026-11-03T03:00:00Z", "2026-11-03T03:10:00Z"),
        one("failure", "2026-11-03T04:30:00Z", "2026-11-03T04:40:00Z"),
        one("failure", "2026-11-03T04:45:00Z", "2026-11-03T04:55:00Z"),
        one("cancelled", "2026-11-03T04:50:00Z", "2026-11-03T04:51:00Z"),
        one("", "2026-11-03T04:52:00Z", "2026-11-03T04:52:00Z", status="in_progress"),
        one("success", "2026-11-03T05:10:00Z", "2026-11-03T05:30:00Z"),
        one("failure", "2026-11-03T06:00:00Z", "2026-11-03T06:10:00Z"),
    ]
    end = datetime(2026, 11, 3, 6, 30, tzinfo=UTC)
    assert daily.spells(runs, end) == [
        (datetime(2026, 11, 3, 4, 30, tzinfo=UTC), datetime(2026, 11, 3, 5, 30, tzinfo=UTC)),
        (datetime(2026, 11, 3, 6, 0, tzinfo=UTC), end),
    ]
    user = jsettings.Settings(zone=ZoneInfo("America/New_York"))
    (_, first, last), (_, second, third) = daily.days(user, date(2026, 11, 2), date(2026, 11, 3))
    spells = daily.spells(runs, end)
    assert daily.red_minutes(spells, first, last) == 30
    assert daily.red_minutes(spells, second, third) == 30 + 30


def test_a_days_red_share_is_the_prs_with_a_red_check_over_the_prs_with_a_check_run(sliced):
    """#10, #20 and #30 had a red `check`, #40 a green one: 3 of 4. #20's draft head, whose
    `check` was skipped, ran no check, and #30's check cancelled while it waited is none either:
    neither adds a pull request. A red check of no pull request (dependabot's) is none."""
    one = next(m for m in daily.MEASURES if m.key == "red_share")
    cell = one.cell(daily.Ledger(sliced, None, ""), SLICE_START - timedelta(hours=1), SLICE_NOW)
    assert (cell.value, cell.n) == (0.75, 4)


def verdicts(found):
    """What `jbus ci` says each number stands at, after its target and before its runners."""
    return {
        one.name: line.split(f"(held to {one.target}) ", 1)[1].split(";")[0]
        for one, line in zip(found, ci.lines(found)[::2], strict=True)
    }


def test_the_verb_says_baseline_beside_a_health_number_with_a_value_and_no_data_beside_none(
    sliced,
):
    """A health number has no target, so its value is a baseline. A number with no value has
    no data."""
    found = numbers.compute(sliced, SLICE_START - timedelta(hours=1), SLICE_NOW)
    health = [one.name for one in found if one.key in HEALTH]
    assert {name: verdicts(found)[name] for name in health} == dict.fromkeys(health, "baseline")
    empty = numbers.compute(sliced, SLICE_NOW, SLICE_NOW + timedelta(days=1))
    none = [one.name for one in empty if one.value is None]
    assert set(HEALTH) <= {one.key for one in empty if one.value is None}
    assert {name: verdicts(empty)[name] for name in none} == dict.fromkeys(none, "no data")


@pytest.fixture
def new_york_machine():
    """The machine's own zone is New York's, as `TZ` sets it."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    yield
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


def test_the_report_counts_its_days_in_the_machines_zone_where_the_user_set_none(
    kitchen, monkeypatch, new_york_machine, tmp_path
):
    """The user sets no `timezone`. 23:01 on the 3rd in New York is the 4th in UTC."""
    import jbus

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-settings"))
    assert jbus.load().user.zone is None
    project = jbus.load().projects[0]
    state = jbus.load().state(project)
    state.mkdir(parents=True, exist_ok=True)
    (state / ledger.JOBS).write_text(
        "".join(json.dumps(one, sort_keys=True) + "\n" for one in SLICE)
    )
    (state / ledger.PULLS).write_text(
        "".join(json.dumps(pull(n, m)) + "\n" for n, m in ((10, 0), (20, 10), (30, 20), (40, 30)))
    )
    monkeypatch.setattr(collect, "Cli", Replay)
    monkeypatch.setattr(Replay, "pages", lambda self, *args: [])
    subprocess.run(
        [
            "git",
            "-C",
            str(project.checkout),
            "remote",
            "set-url",
            "origin",
            f"https://{HOST}/{REPO}",
        ],
        check=True,
    )
    monkeypatch.setattr(ci.verbs, "clock", lambda: SLICE_NOW)

    code, said = kitchen.main("ci", "--report", "--days", "2")

    assert code in (0, 1), said
    text = next((jbus_home(project) / "reports").glob("ci-week-*.md")).read_text()
    rows = [line.split(" | ")[:2] for line in text.splitlines() if line.startswith("| 2026-11-0")]
    assert rows[-2:] == [
        ["| 2026-11-03", "75% (3 of 4: 1 own, 2 shared)"],
        ["| 2026-11-04", "0% (0 of 1: 0 own, 0 shared)"],
    ]


def test_the_verbs_help_names_the_six_health_numbers_beside_the_nine_targets(kitchen):
    code, said = kitchen.main("--help")
    page = said.splitlines()
    at = next(n for n, line in enumerate(page) if line.split()[:1] == ["ci"])
    rest = itertools.takewhile(lambda line: line.startswith(" " * 20), page[at + 1 :])
    said = " ".join([page[at], *rest])
    assert code == 0
    assert "nine targets" in " ".join(said.split()) and "six health numbers" in " ".join(
        said.split()
    )
    assert "six health numbers" in " ".join(ci.__doc__.split())
