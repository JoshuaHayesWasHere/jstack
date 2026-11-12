"""A brief whose proof is the user's own judgement holds its pull request at the merge until the
user's word. rh-root-split-skill's `Proves it:` line said "judged: only a person can say the
skill reads as the root's goal and duties, so the user reviews the diff in the pull request",
and jmerge merged #1828 on 2026-11-12 on its green checks and clean review alone: the review the
user asked for was lost without a word.

The hold is lifted by the user's own message, which jbus reads and checks (`--accept --message`),
or by a `Waived:` line for the judged clause whose word jbus checked. A `judged:` clause that
names no user, a reviewer or a measure, holds nothing.

The tests run the command against a real origin and a fake `gh`, with the kitchen of
`test_jmerge_accept_act`, whose fake T3 Code gives jbus the user's own message.
"""

import test_jmerge_accept_act as accept_act
from jmerge import ready
from test_jmerge_fresh import LINES

kitchen = accept_act.kitchen

CLAUSE = "only a person can say the skill reads as the root's goal, so the user reviews the diff"
PROVES = f"`make check` passes; judged: {CLAUSE}"


def opened(kitchen, proves, extra=""):
    """Pull request #6 of `alpha`, its checks green and its review clean, with this `Proves it:`
    line in its brief's head, and `extra` added to its Result."""
    kitchen.crew("alpha", 6, {"a.txt": "ours\n" + LINES})
    task = kitchen.home.tasks / "alpha.md"
    text = task.read_text().replace("Task:", f"Proves it: {proves}\nTask:", 1)
    task.write_text(text + accept_act.PROOF + extra)


def test_a_brief_the_user_judges_is_held_on_green_checks_and_a_clean_review(kitchen):
    opened(kitchen, PROVES)
    (said,) = kitchen.run()
    assert said.startswith("hold 6 "), said
    assert ready.USER_JUDGED in said, said
    assert kitchen.calls() == [], "it merged"


def test_the_users_own_message_lifts_the_hold_and_it_merges(kitchen):
    opened(kitchen, PROVES)
    kitchen.run()
    ref = accept_act.said(kitchen, "reviewed the diff, merge 6")
    out = accept_act.jmerge(kitchen, "--accept", "6", "--as", "user", "--message", ref)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert [call.split()[2] for call in kitchen.calls()] == ["6"]


def test_a_homes_typed_accept_does_not_stand_for_the_users_judgement(kitchen):
    opened(kitchen, PROVES)
    kitchen.run()
    out = accept_act.accept(kitchen, 6)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out[-1].startswith("refused 6 "), out
    assert ready.USER_JUDGED in out[-1], out
    assert kitchen.calls() == [], "it merged"


def test_a_waived_line_for_the_judged_clause_whose_word_jbus_checked_lets_it_merge(kitchen):
    ref = accept_act.said(kitchen, "alpha: waive only a person can say the skill reads")
    opened(kitchen, PROVES, f"Waived: only a person can say the skill reads, {ref}\n")
    (said,) = kitchen.run()
    assert said.startswith("merged 6 "), said


def test_a_waived_line_with_no_word_of_the_users_behind_it_waives_nothing(kitchen):
    ref = accept_act.said(kitchen, "alpha: looks fine")
    opened(kitchen, PROVES, f"Waived: only a person can say the skill reads, {ref}\n")
    (said,) = kitchen.run()
    assert said.startswith("hold 6 ") and ready.USER_JUDGED in said, said


def test_a_judged_clause_that_names_no_user_holds_nothing(kitchen):
    opened(kitchen, "`make check` passes; judged: the reviewer reads the skill as the root's goal")
    (said,) = kitchen.run()
    assert said.startswith("merged 6 "), said


def test_a_judged_clause_on_a_measure_holds_nothing(kitchen):
    opened(kitchen, "judged: the share of rows held drops to at most 1 in the first week")
    (said,) = kitchen.run()
    assert said.startswith("merged 6 "), said
