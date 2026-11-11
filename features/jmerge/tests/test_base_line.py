"""The head of a base's line, kept on a pull request's record in `base-merges.json`
(`rejudge.BaseMerge`), outlives a move of main. A red pull request at the head of its line is
judged again at each new tip (`cli.Repo.again` reads `repeats`), and that kept a record of the
new head and tip in place of the old one, with no line and the user's word kept: `holders` then
named nobody, and the next pull request in line took a merge of main while the accepted one
waited on its check (st-implicit, finding 2, 2026-11-10).

What `jmerge` did about a run GitHub kept queued (`stuck`) is about the pull request's head: a
move of the tip alone starts no new run at that head, so it stays, and a new head ends it."""

import json
from datetime import UTC, datetime

import pytest

from jmerge import ready, rejudge

WORD = "accepted by user at 2026-11-10 on thread/message"


def pull(head: str = "a" * 40, number: int = 7, base: str = "main") -> ready.PullRequest:
    url = f"https://github.com/o/r/pull/{number}"
    return ready.PullRequest(number, url, "t", "b", head, base, "MERGEABLE", (), (), False, 1)


@pytest.fixture
def merges(tmp_path):
    """A `BaseMerge` of a run that asks GitHub nothing, so no `gh` is called."""
    return rejudge.BaseMerge(tmp_path, tmp_path, [], run=False)


def test_an_accepted_holder_keeps_its_line_when_it_is_judged_at_a_new_tip(merges):
    one = pull()
    merges.of(one, "1" * 40, line=True)
    merges.accept(one, WORD)
    merges.keep(one, "2" * 40, repeated={"check": []})
    assert merges.holders([one]) == {"main": 7}
    assert merges.accepted(7) == WORD


def test_a_holder_keeps_its_line_when_it_is_judged_at_a_new_head(merges):
    one = pull()
    merges.of(one, "1" * 40, line=True)
    moved = pull(head="b" * 40)
    merges.keep(moved, "1" * 40, repeated={"check": []})
    assert merges.holders([moved]) == {"main": 7}


def test_the_word_goes_with_the_line(merges):
    one = pull()
    merges.of(one, "1" * 40, line=True)
    merges.accept(one, WORD)
    merges.release(7)
    merges.keep(one, "2" * 40, repeated={"check": []})
    assert merges.holders([one]) == {}
    assert merges.accepted(7) == ""


def test_an_accept_gives_the_head_of_the_line_of_the_pull_requests_base(merges):
    one = pull(base="stack")
    merges.accept(one, WORD)
    assert merges.holders([one]) == {"stack": 7}
    assert merges.accepted(7) == WORD


def test_what_was_done_about_a_queued_run_stays_across_a_move_of_the_tip_alone(merges):
    one = pull()
    merges.keep(one, "1" * 40)
    merges.keep_stuck(one, since=datetime.now(UTC).isoformat(), took="then", gave_up=True)
    stuck = merges.stuck(one)
    merges.keep(one, "2" * 40, repeated={"check": []})
    assert merges.stuck(one) == stuck


def test_what_was_done_about_a_queued_run_ends_with_a_new_head(merges):
    one = pull()
    merges.keep(one, "1" * 40)
    merges.keep_stuck(one, took="then", gave_up=True)
    moved = pull(head="b" * 40)
    merges.keep(moved, "1" * 40)
    assert merges.stuck(moved) == {}
    assert merges.known()["7"].get("stuck") is None


def test_a_word_kept_with_no_line_before_this_gives_no_line(tmp_path):
    record = {"head": "a" * 40, "tip": "1" * 40, "base": "main", "line": False, "accepted": WORD}
    (tmp_path / rejudge.NAME).write_text(json.dumps({"7": record}))
    merges = rejudge.BaseMerge(tmp_path, tmp_path, [], run=True)
    merges.keep(pull(), "2" * 40, repeated={"check": []})
    assert merges.accepted(7) == ""
    assert "accepted" not in json.loads((tmp_path / rejudge.NAME).read_text())["7"]
