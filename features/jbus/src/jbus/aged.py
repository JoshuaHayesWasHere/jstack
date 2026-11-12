"""Every wait of a row on a reason of `jmerge`'s has an owner and a bound, and a wait that outlives
its bound is escalated, whatever step was meant to clear it.

Each code of `jmerge`'s reasons (`ready.Reason`) has one row of `BOUNDS`: its owner, the one who
clears it, and its bound, the minutes a row may wait on it with its `why` unchanged. The owner is
a jbus act (`ACT`: jbus, `jmerge` or GitHub are at work on it, as on a run in CI or a run GitHub
kept queued), the row's crew or reviewer (`CREW`, or the crew of the row ahead the reason names),
the row's home (`HOME`: nothing at work moves it), or the user (`USER`: a code on the `hold` step,
which `waiting.holds` lists for the user from its first pass, so it has no bound here).
`jbus.clock.held` reads the owner: a thread at work drops a hold only where its code is a crew's,
since a busy crew starts no run GitHub keeps queued.

`aged` is the backstop over every remedy: a row whose `why`, a `wait` of `jmerge`'s, is unchanged
past its code's bound, read with its `since` from `waits.jsonl`, is aged, whoever owns the code
and whatever step was meant to clear it. It is a guard by design, for a state no step has a remedy
for: each remedy stays the act of its own module (`cancelled`, `rebase`, `expedite`, `jbus.clock`'s
clocks), and `aged` only escalates what none of them moved. `jbus clear` prints an aged row as its
home's `fix wait:<slug>`, and as a decision once the home's fixes of it reach `retry_cap`
(`jbus.blockers`), and the view lists it as an `aged` wrong (`jbus.view.state.wrongs`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jbus import queue, work
from jmerge import ready

HOME_MINUTES = 30
"""The minutes a wait nothing at work moves may stand: `jbus.clock.HOLD_MINUTES` too."""
AHEAD = (
    (ready.MERGES_AFTER, "slug"),
    (ready.STACKED_ON, "slug"),
    (ready.CARRIES_AFTER, "slug"),
    (ready.MIGRATION_REBASING, "number"),
    (ready.IN_LINE, "number"),
)
"""The waits on a row ahead, each with the field that names that row. While its pull request is
open, what holds it is its own wait, which the merge runner, a thread, `jbus.clock.held` or a clock
of `jbus.clock` is on, so the rows behind it are no hold of their own."""

ACT, CREW, HOME, USER = "jbus act", "crew", "home", "user"
OWNERS = (ACT, CREW, HOME, USER)
"""Who clears a wait: see the module."""


@dataclass(frozen=True)
class Bound:
    """Who clears a wait on one code, and the minutes it may stand unchanged before it is aged,
    or None for a code the user's list carries from its first pass."""

    owner: str
    minutes: int | None


ACT_MINUTES = 60
"""Two of `jmerge`'s `QUEUED_MINUTES`: time for a run to start, and for one restart of it."""
CREW_MINUTES = 120
"""Time for the clocks above to ask the thread twice and give its stall to the home."""
AHEAD_MINUTES = 240
"""A wait on a row ahead: that row's own wait ages first, and these rows only if it does not."""
_CODES: tuple[tuple[str, int | None, tuple[str, ...]], ...] = (
    (
        ACT,
        ACT_MINUTES,
        tuple(
            one.code
            for one in (
                ready.MAIN_MOVED,
                ready.MERGE_FAILED,
                ready.NO_MESSAGES,
                ready.NOT_PASSED,
                ready.NO_RUN,
                ready.CANCELLED_UNRUN,
                ready.LIVE_RUN,
                ready.UNDECIDED,
                ready.MAIN_CHANGED,
                ready.CARRIES_UNKNOWN,
                ready.MIGRATION_MERGING,
                ready.BASE_MERGE_ASKED,
                ready.BASE_MERGE_DUE,
                ready.BASE_MOVED_ASKED,
                ready.BASE_MOVED_DUE,
                ready.QUEUED_RESTARTED,
                ready.QUEUED_UNOPENED,
                ready.QUEUED_UNCLOSED,
                ready.MERGED_TREE_UNENDED,
                ready.MERGED_TREE_UNBUILT,
                ready.MERGED_TREE_NO_TIME,
                ready.MERGED_TREE_NO_SLOT,
                ready.RULE_UNRUN,
                ready.MERGING,
                ready.IN_BATCH,
                ready.BATCH_FIRST,
                ready.BATCH_STOPPED,
                ready.MAIN_BROWSER_RED,
            )
        )
        + tuple(code for code, _, _ in ready.ELSEWHERE),
    ),
    (
        CREW,
        CREW_MINUTES,
        tuple(
            one.code
            for one in (
                ready.NO_BRIEF,
                ready.HAND_DRAFT,
                ready.FRESH_CONFLICT,
                ready.NO_HEAD,
                ready.BASE,
                ready.NO_REVIEW,
                ready.SKILLS_UNRUN,
                ready.PROVED_MISSING,
                ready.PROVED_UNREAD,
                ready.PROVED_NOT_EXEMPT,
                ready.PROVED_NOT_KIND,
                ready.PROVED_UNNAMED,
                ready.PROVED_BASE_PASSED,
                ready.PROVED_HEAD_FAILED,
                ready.PROVED_STALE,
                ready.CHECKED_MISSING,
                ready.CHECKED_STALE,
                ready.CHECKED_CUT,
                ready.CHECKED_FAILED,
                ready.CHECKED_PART,
                ready.NO_VERDICT,
                ready.NO_FIXED,
                ready.NOT_PUSHED,
                ready.FIX_UNREVIEWED,
                ready.DECLINES_OVERRULED,
                ready.MEETS_NO,
                ready.MEETS_UNREAD,
                ready.MEETS_MISCOUNTED,
                ready.UNENDED,
                ready.UNANSWERED,
                ready.UNPROVEN,
                ready.UNCITED,
                ready.REPEATED,
                ready.RISK_UNASKED,
                ready.CANNOT_CHECK,
                ready.DROPPED,
                ready.SCOPED_UNRULED,
                ready.CONTENT_CHANGED,
                ready.CHECK_FAILED,
                ready.CONFLICTS,
                ready.STACKED_UNMOVED,
                ready.MIGRATION_TAKEN,
                ready.UNMERGED,
                ready.MERGED_TREE_FAILS,
                ready.RULE_BREAKS,
                ready.BROWSER_RED,
            )
        ),
    ),
    (CREW, AHEAD_MINUTES, tuple(one.code for one, _ in AHEAD)),
    (
        HOME,
        HOME_MINUTES,
        (
            *(
                one.code
                for one in (
                    ready.OTHER_HOME,
                    ready.CANCELLED_TWICE,
                    ready.BASE_MERGE_REFUSED,
                    ready.QUEUE_UNREADABLE,
                    ready.QUEUED_GAVE_UP,
                    ready.QUEUED_UNRESTARTED,
                    ready.QUEUED_UNREOPENED,
                )
            ),
            ready.UNKNOWN,
        ),
    ),
    (USER, None, tuple(one.code for one in ready.reasons().values() if one.step == "hold")),
)


BOUNDS: dict[str, Bound] = {
    code: Bound(owner, minutes) for owner, minutes, codes in _CODES for code in codes
}
"""Each code of `jmerge`'s reasons, its owner and its bound: see the module. A code `jmerge`
gains with no row here fails `test_jbus_held_aged`."""


def bound(reason: str) -> Bound:
    """The row of `BOUNDS` of a reason `jmerge` gives, by its code (`ready.code_of`)."""
    return BOUNDS[ready.code_of(reason)]


@dataclass(frozen=True)
class Aged:
    """A row whose wait is unchanged past its code's bound: its reason, the row of `BOUNDS`, and
    since when it has waited on it, from `waits.jsonl`."""

    slug: str
    reason: str
    bound: Bound
    since: datetime
    minutes: int

    @property
    def said(self) -> str:
        """The wait as a blocker says it."""
        return (
            f"it has waited {self.minutes} minutes on {self.reason}, past its bound of "
            f"{self.bound.minutes}, and the {self.bound.owner} that clears it has not"
        )


def aged(rows: list[queue.Row], waits: list[dict[str, Any]], now: datetime) -> dict[str, Aged]:
    """By slug, each open row whose `why` is a `wait` of `jmerge`'s that has not changed past its
    code's bound. Its `since` is the `at` of the row's last line of `waits.jsonl` (`waits`), which
    the pass writes before the table: a row whose last line is not its `why` has no known `since`,
    and is not aged. A code of the user's (`USER`) is never aged here. It reads only what it is
    given, so `jbus clear` and the view read the same rows the same way."""
    last: dict[str, dict[str, Any]] = {}
    for one in waits:
        if isinstance(one, dict) and isinstance(one.get("slug"), str):
            last[one["slug"]] = one
    found = {}
    for row in rows:
        why, slug = str(row.get("why") or ""), row["slug"]
        word, _, reason = why.partition(": ")
        line = last.get(slug) or {}
        if work.over(row) or word != "wait" or not reason or line.get("why") != why:
            continue
        rule, since = bound(reason), datetime.fromisoformat(line["at"])
        minutes = int((now - since).total_seconds() // 60)
        if rule.minutes is not None and minutes >= rule.minutes:
            found[slug] = Aged(slug, reason, rule, since, minutes)
    return found
