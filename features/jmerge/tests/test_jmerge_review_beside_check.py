"""A rebase that changed the content is said while its required check can still pass, so jbus
launches the scoped review beside the check and not after it. A failed check and a conflict
are still said first, and the pull request merges only once both the check passed and the
scoped review is in, whichever comes first.

The tests rebase a reviewed branch over a main that moved (`test_jmerge_rangediff.Rebased`)
and run `jmerge` as `features/jmerge/tests/test_jmerge_run.py` runs it."""

import os

import pytest

import test_home_merge as merge
import test_jmerge_run as run
from jbus import rebase as asks
from jmerge import cli, ready
from test_jmerge_fresh import PROTECTED
from test_jmerge_rangediff import BOTH, LATER, Rebased

LIVE = {"__typename": "CheckRun", "name": "shard", "workflowName": "check"}
STILL_TO_PASS = {
    "not passed": ((merge.RUNNING,), "check has not passed"),
    "a live run": (({**LIVE, "status": "IN_PROGRESS", "conclusion": ""},), "running"),
    "no run": ((), "check has no run at"),
}


def changed(proven_merged, checks, mergeable="MERGEABLE"):
    """A rebase that changed the content after its review, at a head GitHub lists `checks` of."""
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    reopen(proven_merged, rebased, checks, mergeable)
    return rebased


def reopen(proven_merged, rebased, checks, mergeable="MERGEABLE"):
    proven_merged.home.open_pull_request(
        rebased.head, checks=checks, mergeable=mergeable, files=list(rebased.files)
    )


def scoped(rebased):
    """The scoped review of the rebased head is in the brief."""
    rebased.brief(merge.review("clean", rebased.before) + run.proven("clean", rebased.head))


def judged(proven_merged, monkeypatch):
    """The judgement `jmerge` makes of the one pull request, in this process."""
    home = proven_merged.home
    monkeypatch.setenv("PATH", f"{home.stub}:{os.environ['PATH']}")
    monkeypatch.setenv("STUB", str(home.stub))
    monkeypatch.setenv("ORIGIN", str(home.origin))
    home.desk_checked()
    repo = cli.Repo(home.main, home.state, merge.ME, False, PROTECTED, user=run.ET)
    (listed,) = merge.json.loads((home.stub / "list.json").read_text())
    return repo.judge(ready.pull_request(listed), "main")


@pytest.mark.parametrize("state", STILL_TO_PASS, ids=list(STILL_TO_PASS))
def test_a_changed_rebase_is_said_while_its_check_can_still_pass(
    proven_merged, rules, monkeypatch, state
):
    checks, said = STILL_TO_PASS[state]
    rebased = changed(proven_merged, checks)
    (line,) = run.jmerge(proven_merged, rules)
    assert line == rebased.waits()
    assert run.merges(proven_merged) == []
    found = judged(proven_merged, monkeypatch)
    assert ready.code_of(found.why) == ready.CONTENT_CHANGED.code
    assert said in found.note
    number, _, ask = asks.content(line)
    assert (number, ask.kind, ask.head) == (7, "rereview", rebased.head)


def test_a_failed_check_is_said_before_a_changed_rebase(proven_merged, rules):
    """GitHub has not decided whether it merges, so the failed check is not all that holds it,
    and `judge` does not judge it again as if the check had passed (#529)."""
    changed(proven_merged, (merge.FAILED,), mergeable="UNKNOWN")
    assert run.jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: check has failed"]


def test_a_conflict_is_said_before_a_changed_rebase(proven_merged, rules):
    changed(proven_merged, (LATER,), mergeable="CONFLICTING")
    assert run.jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: it conflicts with its base"]


def test_a_conflict_while_the_check_runs_is_not_said_to_wait_on_the_scoped_review(
    proven_merged, rules
):
    changed(proven_merged, (merge.RUNNING,), mergeable="CONFLICTING")
    assert run.jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: check has not passed"]


def test_the_check_passing_first_still_waits_for_the_scoped_review(proven_merged, rules):
    rebased = changed(proven_merged, (merge.RUNNING,))
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    reopen(proven_merged, rebased, (LATER,))
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    assert run.merges(proven_merged) == []
    scoped(rebased)
    (said,) = run.jmerge(proven_merged, rules)
    assert said.startswith("merged 7 alpha ")
    assert len(run.merges(proven_merged)) == 1


def test_the_scoped_review_in_first_still_waits_for_the_check(proven_merged, rules):
    rebased = changed(proven_merged, (merge.RUNNING,))
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    scoped(rebased)
    assert run.jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: check has not passed"]
    assert run.merges(proven_merged) == []
    reopen(proven_merged, rebased, (LATER,))
    (said,) = run.jmerge(proven_merged, rules)
    assert said.startswith("merged 7 alpha ")
    assert len(run.merges(proven_merged)) == 1
