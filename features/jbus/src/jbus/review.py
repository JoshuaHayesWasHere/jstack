"""What a pull request's review waits on: the class of a wait `jmerge` gives (`class_of`),
whether a reviewer the crew launched has yet to write its `## Review` (`reviewing`), and whether a
crew waits on the review that comes before its pull request (`awaited`), and the two ranges of a
scoped review (`ranges`).

`jbus.clock` keeps a clock for each class, `jbus.rebase` and `jbus.stack` wait on a review that is
running, and the outbox holds a message to a crew whose review is running (`outbox.RULES`). This
module imports nothing of jbus, so that each of them can import it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jbriefs import below, findings
from jmerge import ready

if TYPE_CHECKING:
    from jbus.passes import Pass

AFTER = "after the review"
"""What a crew's Result says on its `Branch:` line, `Pull request: after the review`, when its desk
proof is on record and its pull request waits for the review jbus launches (`jbus.prereview`)."""

FIXES = (ready.FIX_UNREVIEWED,)
CLASSES = (
    ("result", (ready.NO_BRIEF,)),
    ("scoped", (*FIXES, ready.SCOPED_UNRULED, ready.CONTENT_CHANGED)),
    ("review", (ready.NO_REVIEW, ready.NO_VERDICT)),
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


def ran(brief: str) -> int:
    """Return how many `## Review` sections of the brief ran (`Verdict: clean` or `findings`) at
    the head they name. A section that says `Verdict: not run` is no review."""
    return sum(1 for one in findings.triage(brief).sections if one.ran and one.head)


_CHECKED_AT = re.compile(r"^Checked: .* at ([0-9a-f]{40})\s*$", re.M)


def desk_head(brief: str) -> str:
    """The head the brief's last `Checked:` line names, the desk proof's head, or nothing."""
    found = _CHECKED_AT.findall(brief)
    return found[-1] if found else ""


def before_pull(result: str) -> bool:
    """Say whether a Result says that its pull request opens after its review."""
    return below.line(result, "Branch:").endswith(f"Pull request: {AFTER}")


def awaited(brief: str, result: str) -> bool:
    """Say whether the crew waits on jbus for the review before its pull request: its last Result
    says the pull request opens after the review, the brief asks for one, and jbus has launched
    no reviewer yet or one it launched has not written a section that ran. jbus tells the crew
    once all have (`jbus.prereview`), so no carry-on goes to it meanwhile, and the clock asks a
    reviewer that wrote `Verdict: not run` again."""
    if not before_pull(result) or findings.mode_of(brief) == findings.NONE:
        return False
    return not launched(brief) or launched(brief) > ran(brief)


_OWED = re.compile(r"^Scoped review: needed since ([0-9a-f]{40}),", re.M)


def _kept(run: Pass, slug: str) -> str:
    """Return the head the crew kept before its last rebase, or nothing where it kept none.
    That head is the newest commit under the slug's `refs/jstack/pre-rebase/` directory."""
    ref = f"refs/jstack/pre-rebase/{slug}/"
    asked = ("git", "for-each-ref", "--sort=-committerdate", "--count=1", "--format=%(objectname)")
    kept = run.run(*asked, ref)
    return "" if kept.returncode else kept.stdout.strip()


def ranges(run: Pass, slug: str, head: str, kind: str, brief: str) -> tuple[str, str] | None:
    """Return the two ranges of a scoped review that ends on `head`: the patch before it and
    the patch after. Each patch starts where its branch left the default branch.

    The patch before ends on one commit. For a rebase, that commit is the newest head the crew
    kept under `refs/jstack/pre-rebase/<slug>/`, which `jmerge` reads too: the crew's keep step
    writes the ref, and a `Rebase:` line an older brief has is read as no line. For a fix, it is
    the head the brief's last `Scoped review: needed since` line names, the one the last review
    saw."""
    before = (_OWED.findall(brief) or [""])[-1] if kind == "fix" else _kept(run, slug)
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if not before or default.returncode:
        return None
    old, new = (run.run("git", "merge-base", default.stdout.strip(), to) for to in (before, head))
    if old.returncode or new.returncode:
        return None
    return f"{old.stdout.strip()}..{before}", f"{new.stdout.strip()}..{head}"
