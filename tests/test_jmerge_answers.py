"""`jmerge` waits until every blocking finding has its answer, on every path, and not only
where a `Second pass:` or `Scoped review:` line says a review of the fix is owed. Run through
`ready.short_of`, the reader the merge goes by, over briefs as the skills write them.

The first three are the briefs the review-determinism-risks scout reproduced, which
`short_of` called ready before this change."""

import pytest

from jmerge import ready
from jsettings import Settings

SAW, FIX = "a" * 40, "b" * 40
RESULT = "\n## Result\nStatus: done\nBranch: alpha   Pull request: https://example.test/pull/7\n"
CODEX = "codex gpt-6-sol xhigh"
CURSOR = "cursor grok-4.7 xhigh"


def section(findings, by="", head=SAW):
    listed = "".join(f"- {one}\n" for one in findings) or "- none\n"
    who = f"By: {by}\n" if by else ""
    verdict = "findings" if findings else "clean"
    return f"\n## Review\n{who}Verdict: {verdict}\nHead: {head}\nFindings:\n{listed}Dropped: 0\n"


OLD = ["error a.py:3 it runs twice", "warning b.py:9 the name lies"]


def test_a_fixed_pull_request_with_no_answer_to_either_finding_waits():
    brief = RESULT + f"Fixed: {FIX}\n" + section(OLD)
    assert ready.short_of(brief, FIX) == ready.UNENDED.format(left=2, found=2)


def test_an_error_declined_because_of_one_character_waits():
    answers = "Finding: fixed, it runs twice\nFinding: not fixed, the name lies, because .\n"
    brief = RESULT + answers + f"Fixed: {FIX}\n" + section(OLD)
    assert ready.short_of(brief, FIX) == ready.UNENDED.format(left=1, found=2)


def test_fixed_none_needed_with_no_answers_waits():
    brief = RESULT + "Fixed: none needed, they are all wrong\n" + section(OLD)
    assert ready.short_of(brief, SAW) == ready.UNENDED.format(left=2, found=2)


def test_a_brief_from_before_ids_reads_as_it_did_its_answers_matched_by_count():
    answers = (
        "Finding: fixed, it runs twice\n"
        "Finding: not fixed, the name lies, because the brief asks for that name\n"
    )
    assert ready.short_of(RESULT + answers + f"Fixed: {FIX}\n" + section(OLD), FIX) == ""


ACT = "error src/a.py:10 it runs twice (principle: none) (bucket: Act on)"
CONSIDER = "info src/b.py:4 a shorter name reads better (principle: none) (bucket: Consider)"


def by_id(*answers):
    return "".join(f"Finding {answer}\n" for answer in answers)


def test_only_an_act_on_finding_blocks_and_it_waits_for_its_answer_by_id():
    brief = RESULT + f"Fixed: {FIX}\n" + section([ACT, CONSIDER])
    assert ready.short_of(brief, FIX) == ready.UNANSWERED.format(ids="F1")
    answered = RESULT + by_id("F1: fixed, it runs twice") + f"Fixed: {FIX}\n"
    assert ready.short_of(answered + section([ACT, CONSIDER]), FIX) == ""


def test_an_answer_with_no_id_does_not_answer_a_finding_that_has_one():
    brief = RESULT + "Finding: fixed, it runs twice\n" + f"Fixed: {FIX}\n" + section([ACT])
    assert ready.short_of(brief, FIX) == ready.UNANSWERED.format(ids="F1")


@pytest.mark.parametrize(
    ("reason", "counts"),
    [
        ("because .", False),
        ("because I disagree", False),
        ("because src/a.py:12 already guards it", True),
        ("because `uv run pytest tests/test_a.py` passes over the case", True),
        ("because question 41 was answered: leave it", True),
    ],
)
def test_a_decline_counts_only_with_a_reason_that_cites_a_path_line_or_a_command(reason, counts):
    answered = (
        RESULT
        + "Noticed: a gate | Gate: question 41\n"
        + by_id(f"F1: not fixed, it runs twice, {reason}")
        + "Fixed: none needed, x\n"
    )
    said = ready.short_of(answered + section([ACT]), SAW)
    counted = ready.DECLINES_UNRULED.format(ids="F1")
    assert said == (counted if counts else ready.UNCITED.format(ids="F1"))


def test_the_same_reason_given_twice_is_refused_after_the_first():
    other = "warning src/c.py:40 it leaks the handle (principle: none) (bucket: Act on)"
    why = "because src/a.py:1 says so"
    answers = by_id(f"F1: not fixed, runs twice, {why}", f"F2: not fixed, leaks, {why}")
    brief = RESULT + answers + "Fixed: none needed, x\n" + section([ACT, other])
    assert ready.short_of(brief, SAW) == ready.REPEATED.format(ids="F2", first="F1")


def test_two_reviewers_on_one_place_are_one_finding_and_one_answer():
    one = ACT.replace("principle: none", "principle: model-the-domain")
    near = "warning src/a.py:13 the loop runs twice (principle: model-the-domain) (bucket: Act on)"
    pair = "Reviewer: mcp:1\nReviewer: mcp:2\n" + section([one], CODEX) + section([near], CURSOR)
    assert ready.short_of(RESULT + f"Fixed: {FIX}\n" + pair, FIX) == ready.UNANSWERED.format(
        ids="F1"
    )
    answered = RESULT + by_id("F1: fixed, it runs twice") + f"Fixed: {FIX}\n" + pair
    assert ready.short_of(answered, FIX) == ""


def test_a_risky_finding_declined_waits_for_the_gate_that_asks_the_user():
    risky = (
        "error src/auth.py:5 the token is logged (principle: none) (bucket: Act on) (risk: auth)"
    )
    declined = by_id("F1: not fixed, the token is logged, because src/log.py:3 redacts it")
    brief = RESULT + declined + "Fixed: none needed, x\n" + section([risky])
    assert ready.short_of(brief, SAW) == ready.RISK_UNASKED.format(ids="F1", risks="auth")
    asked = by_id("F1: not fixed, the token is logged, because question 52: Josh left it")
    unparked = RESULT + asked + "Fixed: none needed, x\n" + section([risky])
    assert ready.short_of(unparked, SAW) == ready.RISK_UNASKED.format(ids="F1", risks="auth")
    parked = unparked.replace("Fixed:", "Gate: question 52\nFixed:")
    assert ready.short_of(parked, SAW) == ready.DECLINES_UNRULED.format(ids="F1")


USER = Settings("Josh")
DECLINED = by_id("F1: not fixed, it runs twice, because src/a.py:12 already guards it")


def scoped(*rulings, by=CODEX, head=SAW, verdict="clean"):
    said = "".join(f"Declines: {one}\n" for one in rulings)
    return (
        f"\n## Review\nBy: {by}\nVerdict: {verdict}\nScope: range-diff x y\n{said}"
        f"Head: {head}\nFindings:\n- none\nDropped: 0\n"
    )


def test_a_decline_with_nothing_pushed_waits_for_the_scoped_pass_and_merges_once_upheld():
    owed = f"Scoped review: needed since {SAW}, to rule on the declines of F1\n"
    brief = RESULT + DECLINED + owed + "Fixed: none needed, x\n" + section([ACT], CODEX)
    assert ready.short_of(brief, SAW) == ready.FIX_UNREVIEWED
    ruled = brief + scoped("upheld F1")
    assert ready.short_of(ruled, SAW) == ""
    assert ready.declines(ruled, user=USER) == ("", "")


def test_a_decline_not_upheld_waits_on_the_crew_until_fixed_and_a_new_decline_does_not_lift_it():
    brief = RESULT + DECLINED + "Fixed: none needed, x\n" + section([ACT], CODEX)
    overruled = brief + scoped("not upheld F1: src/a.py:12 guards another path")
    said = ready.DECLINES_OVERRULED.format(ruled="F1: src/a.py:12 guards another path")
    assert ready.short_of(overruled, SAW) == said
    assert ready.declines(overruled, user=USER) == ("", "")
    again = overruled + by_id("F1: not fixed, it runs twice, because src/b.py:3 guards it too")
    assert ready.short_of(again, SAW) == said
    fixed = overruled + by_id("F1: fixed, it runs twice")
    assert ready.short_of(fixed, SAW) == ""


def test_a_risky_decline_not_upheld_is_the_users_and_no_other_is():
    risky = ACT.replace("(bucket: Act on)", "(bucket: Act on) (risk: auth)")
    declined = by_id("F1: not fixed, it runs twice, because question 52: Josh left it")
    brief = RESULT + "Gate: question 52\n" + declined + "Fixed: none needed, x\n"
    overruled = brief + section([risky], CODEX) + scoped("not upheld F1: the token still logs")
    assert ready.short_of(overruled, SAW) == ""
    kind, why = ready.declines(overruled, user=USER)
    assert kind == "hold"
    assert why == ready.RISKY_OVERRULED.format(
        user="Josh", ruled="F1: the token still logs", risks="auth"
    )


def test_a_scoped_pass_at_the_first_reviews_head_by_the_same_model_keeps_its_findings():
    brief = RESULT + "Fixed: none needed, x\n" + section([ACT], CODEX) + scoped()
    assert ready.short_of(brief, SAW) == ready.UNANSWERED.format(ids="F1")


def test_every_new_wait_is_a_reason_the_view_places_on_the_findings_step():
    from jbus import merge

    for reason in (ready.UNANSWERED, ready.UNCITED, ready.REPEATED, ready.RISK_UNASKED):
        assert reason.step == "findings"
        said = "wait: " + reason.format(ids="F1", first="F1", risks="auth")
        assert merge.step(said) == "findings"
