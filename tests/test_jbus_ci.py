"""`jbus ci` keeps CI's jobs and counts the nine targets of the plan from them.

The numbers are checked against a recording of GitHub's Actions API for jstack, 2026-10-14 to
2026-10-17 (`tests/fixtures/ci/jstack`, replayed by `ci_replay`), through the collector as
`jbus ci` runs it, and equal the figures the plan was written from: where one does not, the
test says by how much and why.
"""

import configparser
import json
import shlex
import threading
from datetime import UTC, datetime, timedelta

import pytest

from ci_replay import FOLDER, Replay
from jbus.ci import collect, ledger, notice, numbers, report
from jbus.ci.collect import Unavailable
from test_jbus_kitchen import NOW as KITCHEN_NOW
from test_jbus_kitchen import REPO as CHECKOUT

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


def test_the_nine_targets_come_in_the_order_of_the_plan(nine):
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
    ]


def test_a_green_job_waits_26_6_minutes_for_a_runner_and_runs_9_67_and_the_target_is_missed(nine):
    one = nine["queue"]
    assert (one.shown, one.n, one.met) == ("26.6 vs 9.67 min", 75, False)
    assert one.hosted == "0 vs 6.44 min"


def test_42_9_percent_of_the_local_runners_minutes_go_to_jobs_that_fail_or_are_cancelled(nine):
    assert (nine["waste"].shown, nine["waste"].met) == ("42.9%", False)
    assert nine["waste"].hosted == "31.4%"


def test_7_of_35_local_reds_are_the_pull_requests_own_and_the_rest_are_main_the_runner_or_a_flake(
    nine,
):
    assert nine["own"].shown == "20% (7 of 35: 7 own, 10 main, 16 runner, 2 flake)"
    assert nine["own"].met is False


def test_29_force_pushes_over_62_merged_pull_requests_is_0_47_each(nine):
    assert nine["rebases"].shown == "0.47 (29 over 62)"
    assert nine["rebases"].met is False


def test_time_to_green_is_33_minutes_on_the_local_runner_and_8_6_on_the_hosted(nine):
    assert (nine["green"].shown, nine["green"].hosted, nine["green"].n) == (
        "33 min",
        "8.6 min",
        28,
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


def test_the_rule_finds_2_flaky_tests_where_the_plan_named_9_by_hand(nine):
    assert (nine["flaky"].value, nine["flaky"].met) == (2.0, True)


def test_no_inode_figure_is_kept_until_a_job_writes_one(nine):
    assert (nine["inode"].value, nine["inode"].shown, nine["inode"].met) == (None, "no data", None)


def test_every_number_says_how_it_was_counted(nine):
    for one in nine.values():
        assert one.how and one.target and one.name
    assert "job level" in nine["queue"].how and "local runner" in nine["queue"].how
    assert "cancelled while it waited" in nine["queue"].how


def test_a_target_with_no_job_in_the_window_has_no_data_and_is_not_missed(facts):
    nothing = numbers.compute(facts, START - timedelta(days=60), START - timedelta(days=59))
    assert [one.shown for one in nothing] == ["no data"] * 9
    assert [one.met for one in nothing] == [None] * 9


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
    assert (one.value, one.met) == (0.0, False) and "35 unread" in one.shown


def test_a_log_with_colour_codes_gives_the_same_evidence_as_one_without():
    plain = "2026-10-17T20:00:00.1Z FAILED tests/test_a.py::test_b - boom\n"
    coloured = "2026-10-17T20:00:00.1Z \x1b[31mFAILED\x1b[0m tests/test_a.py::test_b - boom\n"
    assert collect.evidence(coloured) == collect.evidence(plain)
    assert collect.failing_tests(collect.evidence(coloured)) == ["tests/test_a.py::test_b"]


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
    assert "Job level only" in text and "counted apart" in text
    assert "cancelled while it waited" in text
    for one in nine.values():
        assert f"**{one.name}**" in text
    assert "- local:" in text and "- hosted:" in text
    assert "2026-10-16: 43.2 min" in text


def test_only_a_missed_target_is_missed(nine):
    assert [one.key for one in report.missed(list(nine.values()))] == [
        "queue",
        "waste",
        "own",
        "rebases",
        "stale",
        "green",
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
    assert kitchen.webhook.said == [] and said == ["ci: every target met or without data, no alert"]
    late = list(nine.values())
    report.escalate(config, project, late, path, KITCHEN_NOW, said.append)
    report.escalate(config, project, late, path, KITCHEN_NOW, said.append)
    assert len(kitchen.webhook.said) == 1
    (line,) = kitchen.webhook.said[0]
    assert "missed" in line and "queue p50 under exec p50 26.6 vs 9.67 min" in line
    assert "flaky tests" not in line and str(path) in line


def unit(name):
    read = configparser.ConfigParser(interpolation=None)
    read.optionxform = str
    read.read(CHECKOUT / "templates" / name)
    return read


def test_the_timer_runs_every_monday_at_nine_in_new_york_whatever_the_machines_zone():
    timer = unit("jbus-ci.timer")
    assert timer["Timer"]["OnCalendar"] == "Mon *-*-* 09:00:00 America/New_York"
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_the_service_runs_the_collector_and_the_report_for_the_jstack_home():
    service = unit("jbus-ci.service")
    assert service["Service"]["Type"] == "oneshot"
    command = shlex.split(service["Service"]["ExecStart"])
    assert command[1:] == ["--project", "jstack", "ci", "--report"]
    assert command[0].endswith("/.local/bin/jbus")


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
