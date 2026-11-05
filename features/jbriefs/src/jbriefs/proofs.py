"""The evidence one review round blocks a merge on: the shapes of a blocking finding's
`(proof: ...)` tag, which `jbriefs.findings` reads and pr-review's "The review", step 4, writes."""

import re

PROOFS = (
    re.compile(r"`[^`]+`, exit [1-9]\d*\b.*"),
    re.compile(r"check \S.* failed\b.*"),
    re.compile(r"doc [\w./-]+:\d+\b.*"),
    re.compile(r"unmet \d+\b.*"),
    re.compile(r"measured [2-9]\d* runs\b.*\bspread\b.*\blimited by\b.*\bdecided before\b.*"),
)
"""The shapes of a blocking finding's `(proof: ...)` tag, the one evidence one round blocks on:
a command in backticks that exited non-zero at the head, a check that failed, a doc line the
pull request made wrong, the number of a `Done when` line it does not meet, or, for a change
that is not optimized, a measure of the base and the head: its run count, its spread, its
limiter and the decision written before the run (principle-explain-the-number)."""


def proven(proof: str) -> bool:
    """Whether a finding's `(proof: ...)` tag has one of the `PROOFS` shapes."""
    return any(shape.fullmatch(proof.strip()) for shape in PROOFS)
