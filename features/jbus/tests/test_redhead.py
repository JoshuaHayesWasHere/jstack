"""`jbus.redhead` reads what a red head's failed jobs' logs name: the failed step's own part of a
log, the failed tests in the order the logs name them, and each failed test and lint rule with its
path, or the failed checks where the logs name neither."""

from __future__ import annotations

import pytest

from jbus import redhead
from jbus.rebase import Red

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
