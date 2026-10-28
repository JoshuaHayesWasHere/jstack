"""What a pull request's review waits on: the class of a wait `jmerge` gives (`class_of`), and
whether a reviewer the crew launched has yet to write its `## Review` (`reviewing`).

`jbus.clock` keeps a clock for each class, `jbus.rebase` and `jbus.stack` wait on a review that is
running, and the outbox holds a message to a crew whose review is running (`outbox.RULES`). This
module imports nothing of jbus, so that each of them can import it.
"""

from __future__ import annotations

import re

from jbriefs import below, findings
from jmerge import ready

FIXES = (ready.FIX_UNREVIEWED, ready.DECLINES_UNRULED)
CLASSES = (
    ("result", (ready.NO_BRIEF,)),
    ("scoped", (*FIXES, ready.SCOPED_UNRULED, ready.CONTENT_CHANGED)),
    ("review", (ready.NO_REVIEW, ready.NO_VERDICT, ready.TWICE_UNWRITTEN, ready.SECOND_UNWRITTEN)),
)
"""Each class with the reasons of `jmerge` it takes, matched by each reason's own pattern, so a
reason that `jmerge` rewords keeps its clock."""


def matches(reason: str, reasons: tuple[ready.Reason, ...]) -> bool:
    """Say whether a wait `jmerge` gives is one of `reasons`, by each reason's own pattern."""
    return any(re.fullmatch(one.pattern, reason) for one in reasons)


def class_of(reason: str) -> str:
    """Return the class of a wait `jmerge` gives, or nothing for a wait that has no clock."""
    return next((name for name, reasons in CLASSES if matches(reason, reasons)), "")


def reviewing(brief: str) -> bool:
    """Say whether a reviewer the crew launched has not written its `## Review` yet."""
    return launched(brief) > reviewed(brief)


def launched(brief: str) -> int:
    """Return how many reviewer lines of the brief name a reviewer the crew launched."""
    said = (one for kind in below.REVIEWERS for one in below.reviewers(brief, kind))
    return sum(map(below.launched, said))


def reviewed(brief: str) -> int:
    """Return how many `## Review` sections of the brief name the head they saw."""
    return sum(1 for one in findings.triage(brief).sections if one.head)
