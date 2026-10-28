"""The cause of a task: each row says why it is where it is, since when, and whether it moves."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from jbus import work
from jbus.view.cause import Cause, cause

NOW = datetime(2026, 10, 26, 12, 6, tzinfo=UTC)
NOT_PASSED = "check has not passed"
_TWICE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def task(kind: str, say: str = "", since: str | None = None, **more) -> dict:
    return {"state": {"kind": kind, "say": say}, "reason": say, "since": since} | more


def checked(name: str, state: str, started: int, completed: int | None = None) -> dict:
    done = ago(completed) if completed is not None else None
    return {"check": {"name": name, "state": state, "started": ago(started), "completed": done}}


def stacked(parent: str) -> str:
    """jmerge's reason for a row stacked on `parent` (`ready.STACKED_ON`)."""
    return (
        f"it is stacked on {parent}, and merges after {parent} merged and jbus moved it onto main"
    )


CAPTURE = {
    "ux-glance-pr": (NOT_PASSED, 8, checked("check 4 of 4", "passed", 14, 2)),
    "ux-telemetry-pr": (NOT_PASSED, 11, checked("check 3 of 4", "passed", 13, 2)),
    "ux-milestones-pr": (NOT_PASSED, 13, checked("check 2 of 4", "passed", 15, 4)),
    "ux-asks-count": (NOT_PASSED, 12, checked("check 4 of 4", "passed", 14, 4)),
    "ux-homes-board-pr": (NOT_PASSED, 15, checked("check 1 of 4", "passed", 17, 6)),
    "fl-base-red-fix": (NOT_PASSED, 51, checked("check 2 of 4", "failed", 30, 14)),
    "cleanup-ux-homes-board-pr": (
        stacked("ux-homes-board-pr"),
        8,
        checked("check 2 of 4", "pending", 7),
    ),
    "cleanup-ux-asks-count": (stacked("ux-asks-count"), 6, checked("check 1 of 4", "pending", 5)),
    "ux-look-pr": (NOT_PASSED, 13, checked("check 1 of 4", "pending", 3)),
    "ux-inbox-pr": (NOT_PASSED, 7, checked("check 1 of 4", "pending", 13)),
    "mac-room-cores": (NOT_PASSED, 6, checked("check 4 of 4", "pending", 4)),
    "ux-find": (NOT_PASSED, 5, checked("check 1 of 4", "pending", 11)),
}


def test_each_row_in_check_says_what_its_check_did_and_since_when():
    """`CAPTURE` is the 12 rows in Check on the live `/state.json` at 08:06 EDT 2026-10-26, as
    the scout kept them: each said only "check has not passed", whatever its check had done."""
    found = {
        slug: cause(task("check", reason, ago(minutes), seen=seen), NOW)
        for slug, (reason, minutes, seen) in CAPTURE.items()
    }
    passed = ", jmerge has not moved it on"
    assert found == {
        "ux-glance-pr": Cause(f"check passed 2m ago{passed}", ago(2), False),
        "ux-telemetry-pr": Cause(f"check passed 2m ago{passed}", ago(2), False),
        "ux-milestones-pr": Cause(f"check passed 4m ago{passed}", ago(4), False),
        "ux-asks-count": Cause(f"check passed 4m ago{passed}", ago(4), False),
        "ux-homes-board-pr": Cause(f"check passed 6m ago{passed}", ago(6), False),
        "fl-base-red-fix": Cause("check failed 14m ago", ago(14), False),
        "cleanup-ux-homes-board-pr": Cause("merges after ux-homes-board-pr", ago(8), False),
        "cleanup-ux-asks-count": Cause("merges after ux-asks-count", ago(6), False),
        "ux-look-pr": Cause("check 1 of 4 running 3m", ago(3), True),
        "ux-inbox-pr": Cause("check 1 of 4 running 13m", ago(13), True),
        "mac-room-cores": Cause("check 4 of 4 running 4m", ago(4), True),
        "ux-find": Cause("check 1 of 4 running 11m", ago(11), True),
    }
    assert sum(not one.moving for one in found.values()) == 8


def test_a_row_in_check_with_no_check_seen_gives_what_the_view_says():
    assert cause(task("check", NOT_PASSED, ago(3)), NOW) == Cause(NOT_PASSED, ago(3), False)


def test_a_check_that_has_not_started_waits_for_a_runner_and_is_not_running():
    seen = {"check": {"name": "check", "state": "pending", "started": None, "completed": None}}
    said = cause(task("check", NOT_PASSED, ago(9), seen=seen), NOW)
    assert said == Cause("check queued, waits for a runner", ago(9), False)


def test_a_row_whose_checks_failed_says_so_while_its_newest_check_still_runs():
    """The newest check, a lint, runs, and `check` failed before it: the row is red."""
    seen = checked("lint", "pending", 2)
    said = cause(task("check", NOT_PASSED, ago(20), seen=seen, checks="failed"), NOW)
    assert said == Cause("a check failed", ago(20), False)


@pytest.mark.parametrize(
    ("given", "said"),
    [
        (task("working", "the thread is working", ago(20)), Cause("thread working", ago(20), True)),
        (
            task("quiet", "x", ago(30), seen={"wrote": ago(12)}),
            Cause("thread silent 12m", ago(12), False),
        ),
        (
            task("hung", "x", ago(200), seen={"thread_updated": ago(95)}),
            Cause("turn silent 1h35, may be hung", ago(95), False),
        ),
        (
            task("behind", "x", ago(11), blocked={"by": "mac-a", "what": "mac-a", "state": "Run"}),
            Cause("behind mac-a", ago(11), False),
        ),
        (task("behind", "x", ago(11), blockers=["mac-b"]), Cause("behind mac-b", ago(11), False)),
        (
            task("review", "no reviewer has started", ago(14)),
            Cause("no reviewer has started in 14m", ago(14), False),
        ),
        (
            task("review", "no review yet", ago(3), seen={"reviewer": True}),
            Cause("review running 3m", ago(3), True),
        ),
        (
            task("review", "no review yet", ago(3), seen={"reviewer": False}),
            Cause("no reviewer has started in 3m", ago(3), False),
        ),
        (
            task("review", "no review yet", ago(3), seen={"reviewer": None}),
            Cause("on review 3m, with no list of threads to show a reviewer", ago(3), False),
        ),
        (task("asking", "which base?", ago(2)), Cause("asks you: which base?", ago(2), False)),
        (task("launching", "x", ago(1)), Cause("thread starting", ago(1), True)),
        (
            task("lost", "x", ago(40)),
            Cause("thread gone with nothing written, needs your word", ago(40), False),
        ),
        (task("unapproved", "x", ago(9)), Cause("waits for your approval", ago(9), False)),
        (
            task("leftover", "x", ago(50)),
            Cause("ended with something left: close it or say why", ago(50), False),
        ),
        (task("second", "x", ago(6)), Cause("second review not written yet", ago(6), False)),
        (
            task("findings", "x", ago(8)),
            Cause("findings not handled yet by its crewmate", ago(8), False),
        ),
        (
            task("rebase", "it conflicts with its base", ago(4)),
            Cause("needs a rebase by its crewmate: it conflicts with its base", ago(4), False),
        ),
        (
            task("proof", "the guard needs a proof", ago(4)),
            Cause("needs a proof from its reviewer: the guard needs a proof", ago(4), False),
        ),
        (
            task("hold", "needs Josh, touches CI", ago(7)),
            Cause("held for your word: needs Josh, touches CI", ago(7), False),
        ),
        (task("merged", "it merged", ago(1)), Cause("it merged", ago(1), False)),
        (task("ready", "", ago(1)), Cause("ready", ago(1), False)),
    ],
)
def test_a_value_says_its_line(given, said):
    assert cause(given, NOW) == said


@pytest.mark.parametrize("value", work.VALUES)
@pytest.mark.parametrize("full", [True, False], ids=["full", "bare"])
def test_every_value_says_something_plain(value, full):
    """Every value of `work.VALUES`, with every fact the view could have or with none."""
    given = task(value, "")
    if full:
        seen = checked("check 1 of 4", "pending", 2) | {"wrote": ago(9)}
        given = task(value, "jmerge said: needs Josh, touches CI", ago(5), seen=seen)
        given |= {"blockers": ["front-row"], "blocked": {"what": "front-row"}}
    said = cause(given, NOW)
    assert said.text.strip()
    assert not _TWICE.search(said.text), said.text
    assert said.since is None or datetime.fromisoformat(said.since)
    assert isinstance(said.moving, bool)
