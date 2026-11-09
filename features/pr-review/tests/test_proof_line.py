"""The review template's `Proof:` line, filled in with the brief's `Proves it:` check and the part
of it that could not run, is read by `jmerge` (`jmerge.proof.fact`) as the proof it was before."""

import re

from jmerge import proof
from testing.paths import REPO

REVIEW = REPO / "features" / "pr-review" / "templates" / "review.md"
HEAD = "a" * 40
COMMAND = "sh /tmp/pr-review-x/proof.sh"
LAST = "172 passed, 317 deselected"
NOT_RUN = "not run: the count on main, which needs the base branch"


def section(code):
    """A `## Review` section whose `Proof:` line is the template's passed side, filled in."""
    line = next(one for one in REVIEW.read_text().splitlines() if "Proof:" in one)
    passed = line.split("Proof: ", 1)[1].split(" | unproven")[0]
    parts = [COMMAND, f"exit {code}", LAST, NOT_RUN]
    filled = re.sub(r"<[^<>]*>", "{}", passed.replace("exit <its exit code>", "{}"))
    return f"## Review\nHead: {HEAD}\nReviewers: 1, 0   Proof: {filled.format(*parts)}\n"


def test_a_proof_that_names_the_part_it_could_not_run_is_still_a_proven_fact():
    assert proof.fact(section(0), HEAD) == (f"{LAST}, {NOT_RUN}", COMMAND)


def test_a_failed_proof_in_that_form_is_still_refused():
    assert proof.fact(section(1), HEAD) is None
