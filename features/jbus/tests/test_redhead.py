"""`jbus.redhead` reads what a red head's failed jobs' logs name: the failed step's own part of a
log, the failed tests in the order the logs name them, and each failed test and lint rule with its
path, or the failed checks where the logs name neither."""

from __future__ import annotations

import pytest

import jbus
from jbus import passes, redhead, watch
from jbus.rebase import Red
from test_jbus_kitchen import NOW, Kitchen

TEST = "features/statechart/tests/test_statechart_overview.py::test_statechart_overview"
OTHER = "features/jbus/tests/test_stall.py::test_hung"
FAILED = "2026-11-12T03:40:00.0000000Z FAILED {} - AssertionError\n"
CAP = (
    "2026-11-12T03:10:00.0000000Z error a-cap-on-size-only-shrinks: features/jbus/src/jbus/"
    "work.py: has 802 lines, over 800: split it\n"
)


@pytest.fixture
def logs(monkeypatch):
    """The job logs GitHub gives, by job id: a job missing from it has no log."""
    given: dict[str, str] = {}
    monkeypatch.setattr(redhead, "job_log", lambda run, repo, job: given.get(str(job)))
    return given


def red(*jobs: str) -> Red:
    return Red(names=("check",), jobs=tuple(("o/r", job) for job in jobs))


def test_failed_step_is_the_part_of_the_log_of_the_step_that_failed_the_job():
    log = (
        "##[group]Run make lint\n"
        "lint ok\n"
        "##[group]Run make test\n"
        "FAILED one\n"
        "##[error]Process completed with exit code 1.\n"
        "##[group]Run cleanup\n"
    )
    assert redhead.failed_step(log) == (
        "##[group]Run make test\nFAILED one\n##[error]Process completed with exit code 1."
    )
    assert redhead.failed_step("no steps\n") == "no steps\n"


def test_named_gives_each_failed_test_once_in_the_order_the_logs_name_them(logs):
    logs["1"] = FAILED.format(OTHER) + FAILED.format(TEST)
    logs["2"] = FAILED.format(TEST)
    assert redhead.named(None, red("1", "2", "3")) == [OTHER, TEST]
    assert redhead.named(None, red("3")) == []


def test_failures_names_tests_and_lint_rules_or_the_checks_where_the_logs_name_neither(logs):
    logs["1"] = FAILED.format(TEST) + CAP
    logs["2"] = "nothing named here\n"
    assert redhead.failures(None, red("1")) == {
        TEST,
        "a-cap-on-size-only-shrinks features/jbus/src/jbus/work.py",
    }
    assert redhead.failures(None, red("2", "3")) == {"check check"}


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def a_pass(kitchen):
    """One jbus pass as its own process has it: a world of its own, so nothing of an earlier pass
    is in memory."""
    config = jbus.load()
    run = passes.Pass(config, config.projects[0], NOW)
    run.world = watch.World()
    return run


def log_reads(kitchen, job):
    return [line for line in kitchen.log("gh") if line.split()[1].endswith(f"/jobs/{job}/logs")]


HEAD, MAIN = "a" * 40, "b" * 40
MERGED = f"HEAD is now at 1234567 Merge {HEAD} into {MAIN}\n"


def test_a_completed_jobs_log_is_asked_of_github_once_across_passes(kitchen):
    """A head waiting on main's check had its failed job's log asked each 10 s pass, 175 times for
    one job in 5 h: a completed job's log never changes, so a later pass reads the first one."""
    kitchen.set("jobs.json", {"901": {"status": "completed", "steps": [], "run_attempt": 1}})
    kitchen.set("logs.json", {"901": MERGED})
    assert redhead.tested(a_pass(kitchen), HEAD, red("901")) == MAIN
    assert redhead.tested(a_pass(kitchen), HEAD, red("901")) == MAIN
    assert len(log_reads(kitchen, "901")) == 1


def test_a_log_of_a_job_not_completed_or_not_given_is_asked_again_each_pass(kitchen):
    """A running job's log grows, and a log GitHub did not give may come later: neither is kept."""
    kitchen.set("jobs.json", {"902": {"status": "in_progress"}, "903": {"status": "completed"}})
    kitchen.set("logs.json", {"902": MERGED})
    assert redhead.tested(a_pass(kitchen), HEAD, red("903", "902")) == MAIN
    assert redhead.tested(a_pass(kitchen), HEAD, red("903", "902")) == MAIN
    assert len(log_reads(kitchen, "902")) == 2
    assert len(log_reads(kitchen, "903")) == 2


def test_the_kept_logs_drop_the_oldest_past_their_bound(kitchen, monkeypatch):
    """The kept logs are bounded: past `KEPT_LOG_BYTES` the oldest is dropped and asked again. The
    kitchen's `gh` ends what it prints with a newline, so each log here is 1000 bytes."""
    monkeypatch.setattr(watch, "KEPT_LOG_BYTES", 2500)
    jobs = ["1", "2", "3", "4", "5"]
    kitchen.set("jobs.json", {job: {"status": "completed"} for job in jobs})
    kitchen.set("logs.json", {job: job * 999 for job in jobs})
    for job in jobs:
        assert watch.job_log(a_pass(kitchen), "o/r", job) == job * 999 + "\n"
    kept = sum(one.stat().st_size for one in (kitchen.state / watch.LOGS).iterdir())
    assert kept <= 2500
    assert watch.job_log(a_pass(kitchen), "o/r", "5") == "5" * 999 + "\n"
    assert watch.job_log(a_pass(kitchen), "o/r", "1") == "1" * 999 + "\n"
    assert (len(log_reads(kitchen, "5")), len(log_reads(kitchen, "1"))) == (1, 2)
