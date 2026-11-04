"""One review round blocks a merge only on what a run, a check, a doc line or a `Done when` line
shows. A blocking finding carries that evidence in a `(proof: ...)` tag, and `jmerge` holds a
pull request whose blocking finding has none under a reason that names the finding. The crew
clears it by answering the finding, and a decline of it needs no cited reason. A finding whose
proof is a run that exited non-zero at the head holds the merge until its answer counts.

The tests drive `ready.short_of`, the function `jmerge` calls before a merge, over briefs as the
review skill writes them."""

import pytest

from jbriefs import findings, proofs
from jmerge import ready

SAW, FIX = "a" * 40, "b" * 40
RESULT = "\n## Result\nStatus: done\nBranch: alpha   Pull request: https://example.test/pull/7\n"
RAN = "`uv run pytest -q tests/test_a.py::test_retry`, exit 1, 1 failed"
FINDING = "error src/a.py:10 the retry never stops (principle: none) (bucket: Act on)"


def section(*found):
    listed = "".join(f"- {one}\n" for one in found)
    return f"\n## Review\nBy: inherit #1\nVerdict: findings\nHead: {SAW}\nFindings:\n{listed}"


def proved(proof):
    return f"{FINDING} (proof: {proof})"


def answered(answer, fixed=f"Fixed: {FIX}\n"):
    return RESULT + f"Finding F1: {answer}\n" + fixed


def test_a_blocking_finding_with_no_proof_holds_the_merge_and_names_the_finding():
    brief = RESULT + f"Fixed: {FIX}\n" + section(FINDING)
    assert ready.short_of(brief, FIX) == ready.UNPROVEN.format(ids="F1")
    assert "F1" in ready.short_of(brief, FIX)


def test_a_finding_whose_proof_exits_non_zero_at_the_head_holds_until_answered():
    brief = RESULT + f"Fixed: {FIX}\n" + section(proved(RAN))
    assert ready.short_of(brief, FIX) == ready.UNANSWERED.format(ids="F1")
    assert ready.short_of(answered("fixed, the retry") + section(proved(RAN)), FIX) == ""


@pytest.mark.parametrize(
    "proof",
    [
        "`uv run pytest -q tests/test_a.py`, exit 0, 3 passed",
        "the retry can loop for ever",
        "",
        "measured 1 runs, 3.9 s, spread 0, limited by a core, decided before the run: 2 s",
        "measured 5 runs at the base and the head, 1.2 s and 3.9 s",
    ],
    ids=["a run that passed", "prose", "empty", "one run", "no spread or limiter"],
)
def test_a_proof_of_no_shape_one_round_takes_is_no_proof(proof):
    brief = RESULT + f"Fixed: {FIX}\n" + section(proved(proof))
    assert ready.short_of(brief, FIX) == ready.UNPROVEN.format(ids="F1")


@pytest.mark.parametrize(
    "proof",
    [
        RAN,
        "check full failed at aaaaaaaaaaaa: tests/test_a.py::test_retry",
        "doc features/a/README.md:12 still says the retry stops after 3",
        "unmet 2: the retry stops after 3 tries",
        "measured 5 runs at the base and the head, 1.2 s and 3.9 s, spread 0.1 s, limited by "
        "one core in jmerge.ready.said_of, decided before the run: over 2 s blocks",
    ],
    ids=["run", "check", "doc", "unmet", "measured"],
)
def test_each_shape_of_proof_blocks_and_a_bare_decline_of_it_does_not_count(proof):
    declined = answered("not fixed, the retry, because I disagree") + section(proved(proof))
    assert proofs.proven(proof)
    assert ready.short_of(declined, FIX) == ready.UNCITED.format(ids="F1")


def test_a_decline_of_an_unproven_finding_counts_with_any_reason():
    declined = answered("not fixed, the retry, because I disagree", "Fixed: none needed, x\n")
    assert ready.short_of(declined + section(FINDING), SAW) == ""


def test_a_risky_unproven_finding_is_still_declined_only_on_a_gate():
    risky = FINDING.replace("(bucket: Act on)", "(bucket: Act on) (risk: auth)")
    declined = answered("not fixed, the retry, because I disagree", "Fixed: none needed, x\n")
    assert ready.short_of(declined + section(risky), SAW) == ready.RISK_UNASKED.format(
        ids="F1", risks="auth"
    )


def test_a_consider_finding_needs_no_proof_and_holds_nothing():
    consider = "info src/b.py:4 a shorter name (principle: none) (bucket: Consider)"
    brief = RESULT + "Fixed: none needed, x\n" + section(consider)
    brief += "Finding F1: not fixed, a name, because consider: left for a follow-up\n"
    assert ready.short_of(brief, SAW) == ""


def test_the_crew_s_list_shows_each_finding_s_proof_or_that_it_has_none():
    brief = RESULT + section(proved(RAN), FINDING.replace("src/a.py:10", "src/c.py:90"))
    shown = "\n".join(findings.listed(findings.triage(brief)))
    assert f"  proof: {RAN}" in shown
    assert "  proof: none, so a decline of it needs no cited reason" in shown
