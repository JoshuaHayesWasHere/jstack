from __future__ import annotations

import ast
import re
import string
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from jbriefs import findings, skills
from jmerge.rangediff import Verdict
from jsettings import Settings

_COMMIT = re.compile(r"[0-9a-f]{40}")
_RANKS = {"clean": 0, "findings": 1}
_REBASE = re.compile(
    r"Rebase: patch (unchanged|changed in (.+)), before ([0-9a-f]{40}), head ([0-9a-f]{40})"
)
_ACK = re.compile(
    r"Dropped on rebase: (.+?), (\d+) of main's, (\d+) of its own, at ([0-9a-f]{12}): (.+)"
)
_UPHELD = "Drops: upheld "
_NOT_UPHELD = "Drops: not upheld "

_CI_FIX = re.compile(r"CI fix: ([0-9a-f]{40}), after the review of ([0-9a-f]{40})")
_MIGRATION = re.compile(r"(\d+)_")
_VALUE = ".+"


class Reason(str):
    step: str

    def __new__(cls, step: str, text: str) -> Reason:
        made = super().__new__(cls, text)
        made.step = step
        return made

    @property
    def pattern(self) -> str:
        return "".join(
            re.escape(literal) + (_VALUE if name is not None else "")
            for literal, name, _, _ in string.Formatter().parse(self)
        )


def reasons() -> dict[str, Reason]:
    return {name: value for name, value in globals().items() if isinstance(value, Reason)}


OTHER_HOME = Reason("", "another home's")
REQUIRED = ("check",)
MERGE_OFF = Reason("hold", "auto-merge is off for this repo")
NO_BRIEF = Reason("result", "no brief has a Result that names it")
DRAFT = Reason("", "draft")
RULES = "features/jmerge/src/jmerge/"
GRAMMAR = "features/jmerge/docs/jmerge.md#patterns"
RULES_CHANGED = Reason("check", "jmerge's rules changed in this run")
MAIN_MOVED = Reason("check", "{base} moved while it was judged")
MERGE_FAILED = Reason("check", "the merge failed")
NO_MESSAGES = Reason("check", "its commit messages could not be read for the squash")
NO_SETTINGS = Reason("check", "the repo's merge settings could not be read")
LANDING_UNALLOWED = Reason("hold", "the repo allows {allowed} only, not a merge commit or a squash")
KEPT = "every line kept"
PASSED = "passed"
FAILED = "failed"
TIMED_OUT = "timed out"
FRESH_QUEUED = Reason("check", "a fresh check is queued")
FRESH_CONFLICT = Reason("rebase", "it conflicts with today's main")
NO_HEAD = Reason("second", "its review names no head to compare its rebase with")

BASE = Reason("hold", "its base is {base}, not {default}")
IN_STACK = Reason("hold", "it is in the stack {stack}, which the user lands")
IN_UNNAMED_STACK = Reason("hold", "it is in a stack its brief does not name, which the user lands")
REVIEW, NONE, AFTER, TWICE = "review", "none", "after", "twice"
REVIEW_NONE = Reason("hold", "its brief says Review: none, so it needs the user's word")
NO_REVIEW = Reason("review", "it has no review yet")
SKILLS_UNRUN = Reason(
    "result",
    "its Result has no artifact under Skills run: for {names}, which its brief names",
)
NO_VERDICT = Reason("review", "its review has no verdict")
NO_FIXED = Reason("findings", "its findings are not handled: the Result has no Fixed line")
NOT_PUSHED = Reason("findings", "its findings are not handled: nothing was pushed after them")
SECOND_UNWRITTEN = Reason(
    "second",
    "its fix changed more than the findings named: the second pass is not written",
)
TWICE_UNWRITTEN = Reason("second", "its second review is not written at {head}")
FIX_UNREVIEWED = Reason("second", "its fix is not reviewed: the scoped review of it is not written")
DECLINES_UNRULED = Reason("second", "the scoped review has not ruled on the declines of {ids}")
DECLINES_OVERRULED = Reason(
    "findings",
    "its findings are not handled: the scoped review did not uphold the decline of {ruled}",
)
RISKY_OVERRULED = Reason(
    "hold",
    "needs {user}, the scoped review did not uphold the decline of {ruled} on {risks}",
)
UNENDED = Reason("findings", "its findings are not handled: {left} of {found} have no Finding line")
UNANSWERED = Reason("findings", "its findings are not handled: {ids} have no answer by id")
UNCITED = Reason(
    "findings",
    "its findings are not handled: the decline of {ids} cites no path:line, command or gate",
)
REPEATED = Reason(
    "findings",
    "its findings are not handled: the decline of {ids} gives the reason of {first}",
)
RISK_UNASKED = Reason(
    "findings",
    "its findings are not handled: {ids} on {risks} declined with no gate question",
)
FIXED_NO_COMMIT = Reason("findings", "its Fixed line names no commit")
REBASE_UNSAID = Reason("rebase", "its Rebase line does not say what the rebase did to the patch")
REBASE_UNTRUE = Reason(
    "rebase",
    "its Rebase line says the patch is unchanged, and the rebase changed it",
)
CANNOT_CHECK = Reason(
    "rebase",
    "its Rebase line cannot be checked: "
    "the patch of {commit} cannot be worked out in the main checkout",
)
DROPPED = Reason("rebase", "the rebase dropped {lost} with no Dropped on rebase line at {head}")
NOT_UPHELD = Reason("hold", "needs {user}, the review did not uphold the drop in {refused}")
UNRULED_DROPS = Reason(
    "hold",
    "needs {user}, the review of {head} did not rule on the drops in {files}",
)
SCOPED_UNRULED = Reason("second", "the scoped review has not ruled on the drops in {files}")
CONTENT_CHANGED = Reason(
    "second",
    "the rebase changed the content after its review; scoped review of {command}",
)
NOT_PASSED = Reason("check", "{check} has not passed")
CONFLICTS = Reason("rebase", "it conflicts with its base")
UNDECIDED = Reason("check", "GitHub has not decided whether it merges")
TOUCHES = Reason("hold", "needs {user}, touches {path}")
RENAMES_UNSAID = Reason("hold", "needs {user}, GitHub did not say which paths its renames left")
UNLISTED = Reason("hold", "needs {user}, GitHub listed {listed} of the {changed} files it changes")
NO_START = Reason("check", "its check has no start time")
NOT_SEEN = Reason("second", "its head is not the one its review saw")
MAIN_CHANGED = Reason(
    "check",
    "{default} changed {paths} after its check started at {since}; it needs {needs}",
)
FRESH_CHECK = "a fresh check"
FRESH_FAILS = Reason("rebase", "{command} fails on {head} over today's main {tip}")
ROW_HELD = Reason("hold", "its queue row is held: approve it again to let it merge")
MERGES_AFTER = Reason("check", "merges after {slug} ({open}), not merged yet")
STACKED_ON = Reason(
    "check",
    "it is stacked on {branch}, and merges after {slug} merged and jbus moved it onto {default}",
)
STACKED_UNMOVED = Reason(
    "check",
    "{slug} merged as {sha}, which its head does not hold: it merges after its crew rebased it "
    "onto {default}",
)
CARRIES_AFTER = Reason(
    "check",
    "carries {carried}'s commits (#{number}), which merges after {slug} ({open}), not merged yet",
)
CARRIES_UNKNOWN = Reason(
    "check", "its head or {carried}'s (#{number}) cannot be read to see whether it carries it"
)
QUEUE_UNREADABLE = Reason(
    "hold",
    "its queue cannot be read, so its holds and merge order are not known",
)
MIGRATION_TAKEN = Reason(
    "rebase",
    "its migration {name} takes number {number}, which {default} has: renumber it to {free}",
)
MIGRATION_MERGING = Reason(
    "check",
    "it adds a migration, and #{number}, which merges before it, is merging",
)
MIGRATION_REBASING = Reason(
    "check",
    "it adds a migration, and #{number}, which merges before it, is being rebased",
)
MAIN_RED = Reason("check", "main is red at {sha}, its fix merges first")
BASE_RED = Reason("check", "{base} is red at {sha}: its latest check failed")
BASE_MERGE_ASKED = Reason(
    "check",
    "GitHub was asked to merge {base} at {tip} into it: its check failed before {base} moved",
)
BASE_MERGE_REFUSED = Reason("check", "GitHub did not merge {base} at {tip} into it: {why}")
BASE_MERGE_DUE = Reason(
    "check", "its check failed before {base} moved: GitHub is to merge {base} at {tip} into it"
)
GATE_FAILED = Reason("hold", "its merge gate failed: {first}")
GATE_UNSTARTED = Reason("hold", "its merge gate could not start: {why}")
GATE_TIMED_OUT = Reason("hold", "its merge gate ran over {limit} and was stopped")
GATE_BUSY = Reason(
    "check", "its merge gate waits for the next run: this run's gates used their time"
)
GATE_LOCKED = Reason("check", "its merge gate waits for another run's gate to end")
GATE_HELD = re.compile(
    "|".join(one.pattern for one in (GATE_FAILED, GATE_UNSTARTED, GATE_TIMED_OUT))
)

_MAINS_LOST = "{count} of main's lines in {file}"
_OWN_LOST = "{count} of its own in {file}"
_REFUSED = "{file}: {why}"
_RULED = "{id}: {why}"
_MORE = " and {more} more"
_CARRIED = "review carried over: range-diff {old} {new} clean"
_FRESH_NOTE = "fresh: {command} {passed} on {head} over {tip}"
_FRESH_KEPT = ", kept over {tip}: main's change since meets none of its tests"
_FRESH_SKIPPED = "fresh: skipped, tree {tree} passed in {at}, on {head} over {tip}"
_RELATED_NOTE = "fresh: none, main changed related {paths}; no fresh-check file"


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    title: str
    branch: str
    head: str
    base: str
    mergeable: str
    waiting: tuple[str, ...]
    files: tuple[str, ...]
    renamed: bool
    changed: int
    draft: bool = False
    started: datetime | None = None
    added: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


def _at(text: str | None) -> datetime | None:
    try:
        at = datetime.fromisoformat(text or "")
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo is not None and at.year > 1 else None


def latest(rollup: list[dict], name: str | None) -> list[dict]:
    named = [one for one in rollup if (one.get("name") or one.get("context")) == name]
    end = datetime.max.replace(tzinfo=UTC)

    def when(one: dict) -> tuple[datetime, datetime]:
        return (_at(one.get("startedAt")) or end, _at(one.get("completedAt")) or end)

    last = max(map(when, named), default=None)
    return [one for one in named if when(one) == last]


def passed(rollup: list[dict], name: str) -> bool:
    runs = latest(rollup, name)
    return bool(runs) and all(
        one.get("state") == "SUCCESS"
        or (one.get("status") == "COMPLETED" and one.get("conclusion") == "SUCCESS")
        for one in runs
    )


def required_of(text: str) -> tuple[str, ...]:
    """The checks that a repo's `required-checks` file names, one to a line, or `REQUIRED`
    where it names none."""
    return tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())) or (
        REQUIRED
    )


def waiting(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> tuple[str, ...]:
    """The required checks whose latest run has not passed, in `required`'s order."""
    return tuple(name for name in required if not passed(rollup, name))


def failed(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> tuple[str, ...]:
    """The required checks whose latest run ended and failed, in `required`'s order. A run
    still going, or one cancelled, is not failed."""
    return tuple(
        name
        for name in required
        if (runs := latest(rollup, name))
        and all(
            one.get("state") in ("FAILURE", "ERROR")
            or (one.get("status") == "COMPLETED" and one.get("conclusion") == "FAILURE")
            for one in runs
        )
    )


def red_only(one: PullRequest) -> bool:
    """Whether the one thing GitHub holds against the pull request is a required check that
    ran and failed: every required check that has not passed failed, and it merges cleanly."""
    return bool(one.waiting) and one.waiting == one.failed and one.mergeable == "MERGEABLE"


_RUN = re.compile(r"/actions/runs/(\d+)/")


def started(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> datetime | None:
    """When the latest run of the first required check started. A check that waits on other
    jobs of its workflow run (the check workflow's four parts) starts when they have ended, so
    the earliest start of a job in the same workflow run counts as its start."""
    runs = latest(rollup, required[0])
    if not runs:
        return None
    first = _at(runs[0].get("startedAt"))
    run = _RUN.search(runs[0].get("detailsUrl") or "")
    if first is None or run is None:
        return first
    times = [
        _at(one.get("startedAt"))
        for one in rollup
        if (other := _RUN.search(one.get("detailsUrl") or "")) and other[1] == run[1]
    ]
    return min((at for at in times if at is not None), default=first)


def pull_request(listed: dict, required: tuple[str, ...] = REQUIRED) -> PullRequest:
    return PullRequest(
        number=listed["number"],
        url=listed["url"],
        title=listed.get("title") or "",
        branch=listed["headRefName"],
        head=listed["headRefOid"],
        base=listed.get("baseRefName") or "",
        mergeable=listed.get("mergeable") or "",
        waiting=waiting(listed.get("statusCheckRollup") or [], required),
        files=tuple(one["path"] for one in listed["files"]),
        renamed=any(one.get("changeType") == "RENAMED" for one in listed["files"]),
        changed=listed["changedFiles"],
        draft=bool(listed.get("isDraft")),
        started=started(listed.get("statusCheckRollup") or [], required),
        added=tuple(one["path"] for one in listed["files"] if one.get("changeType") == "ADDED"),
        failed=failed(listed.get("statusCheckRollup") or [], required),
    )


def listed_in_full(one: PullRequest, every: list[dict]) -> PullRequest:
    """`one` with the files of GitHub's files endpoint, which pages through up to 3000 of them,
    where `gh pr list` lists the first 100. Its `status` is the change type in lower case."""
    if len(every) <= len(one.files):
        return one
    return replace(
        one,
        files=tuple(file["filename"] for file in every),
        renamed=any(file.get("status") == "renamed" for file in every),
        added=tuple(file["filename"] for file in every if file.get("status") == "added"),
    )


def _fields(line: str) -> list[str]:
    return line.split()


def _second(line: str) -> str:
    fields = _fields(line)
    return fields[1] if len(fields) > 1 else ""


def brief_of(url: str, tasks: Path) -> Path | None:
    for task in sorted(tasks.glob("*.md")):
        try:
            lines = task.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            fields = _fields(line)
            if fields and fields[0] == "Branch:" and fields[-1] == url:
                return task
    return None


def stack_of(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Stack:"):
            return "".join(line.removeprefix("Stack:").split()[:1])
    return None


STACKED = "Stacked on:"


@dataclass(frozen=True)
class Stacked:
    """What a brief's `Stacked on:` line says, the one record of a link jbus stacked: the row it
    builds on, the branch its pull request sits on, and, once that row merged and jbus moved the
    link onto the default branch, the commit of that branch that merged it (`at`).

    jbus writes the line at the launch, `Stacked on: <slug> <its branch>`, and again once the
    row merged, `Stacked on: <slug> <default branch> at <commit>` (`jbus.stack`)."""

    slug: str
    branch: str
    at: str = ""


def stacked_of(text: str) -> Stacked | None:
    """The `Stacked on:` line in the head of a brief, above its first `## `, or None."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(STACKED):
            words = line.removeprefix(STACKED).split()
            if len(words) == 2:
                return Stacked(*words)
            if len(words) == 4 and words[2] == "at" and _COMMIT.fullmatch(words[3]):
                return Stacked(words[0], words[1], words[3])
            return None
    return None


def unmoved(text: str) -> bool:
    """Whether a brief is of a link that still sits on its base's branch: its branch holds its
    base's commits and its own, so a rebase onto the default branch would replay them."""
    stacked = stacked_of(text)
    return stacked is not None and not stacked.at


def stacked_line(stacked: Stacked) -> str:
    at = f" at {stacked.at}" if stacked.at else ""
    return f"{STACKED} {stacked.slug} {stacked.branch}{at}"


def integration_of(text: str) -> tuple[str, ...]:
    """The integration branches that a project's `integration` file names, one to a line."""
    return tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def held(
    one: PullRequest,
    default: str,
    stack: str | None,
    land: str | None,
    integration: tuple[str, ...] = (),
    stacked: Stacked | None = None,
) -> str:
    """Why a pull request is held by its base or its stack, or nothing. A link jbus stacked sits
    on its base's branch until that row merged: it is not held for it, and waits (`on_stack`)."""
    on_base = stacked is not None and one.base == stacked.branch
    if one.base != default and one.base not in integration and not on_base:
        return BASE.format(base=one.base, default=default)
    if stack is None or (stack and stack == land):
        return ""
    return IN_STACK.format(stack=stack) if stack else IN_UNNAMED_STACK


def migrations(one: PullRequest, directory: str) -> tuple[str, ...]:
    if not directory:
        return ()
    found = (Path(path) for path in one.added)
    names = (path.name.split(".")[0] for path in found if path.parent == Path(directory))
    return tuple(dict.fromkeys(sorted(names)))


def migration_number(name: str) -> str:
    found = _MIGRATION.match(name)
    return found[1] if found else ""


def short_on_migration(names: tuple[str, ...], on_default: set[int], default: str) -> str:
    for name in names:
        digits = migration_number(name)
        if digits and int(digits) in on_default:
            free = str(max(on_default) + 1).zfill(len(digits))
            return MIGRATION_TAKEN.format(name=name, number=digits, default=default, free=free)
    return ""


_TAKEN = re.compile(MIGRATION_TAKEN.pattern + "$")


def being_rebased(why: str) -> bool:
    return why in (CONFLICTS, FRESH_CONFLICT) or bool(_TAKEN.match(why))


@dataclass
class Round:
    verdict: str = ""
    head: str = ""
    found: int = 0
    by: str = ""
    scoped: bool = False


def _worst(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda verdict: _RANKS.get(verdict, len(_RANKS)))


@dataclass
class Said:
    mode: str = REVIEW
    written: bool = False
    verdict: str = ""
    ran: int = 0
    reviewed: str = ""
    fixed: str = ""
    rebased: str = ""
    pushed: str = ""
    saw: str = ""
    wider: bool = False
    since: str = ""
    owed: bool = False
    asked: str = ""
    asked_at: int = -1
    found: int = 0
    ended: int = 0
    second: bool = False
    scoped: bool = False
    rounds: list[Round] = field(default_factory=list)
    triage: findings.Triage = field(default_factory=findings.Triage)


def said_of(text: str) -> Said:
    said = Said()
    triage = findings.triage(text)
    said.triage = triage
    said.written = bool(triage.sections)
    said.rounds = [
        Round(one.verdict, one.head, one.found, one.by, one.scoped)
        for one in triage.roster.counted(triage.sections)
    ]
    said.reviewed = next((one.head for one in reversed(triage.sections) if one.head), "")
    sent = [one for one in triage.findings if one.blocks]
    said.found, said.ended = len(sent), sum(one.ended for one in sent)
    seen = False
    for at, line in enumerate(text.splitlines()):
        if line.startswith("Review:") and not seen:
            seen = True
            said.mode = _mode(line)
        if line.startswith("Fixed:"):
            said.fixed = _second(line)
        if line.startswith("Second pass:"):
            fields = _fields(line)
            said.wider = fields[2:3] == ["needed"]
            said.second = said.second or said.wider
            said.since = fields[4].rstrip(",") if said.wider and len(fields) > 4 else ""
        if line.startswith("Scoped review:"):
            fields = _fields(line)
            said.owed = fields[2:3] == ["needed"] and fields[5:] != ["guarded"]
            said.scoped = said.scoped or fields[2:3] == ["needed"]
            said.asked = fields[4].rstrip(",") if said.owed and len(fields) > 4 else ""
            said.asked_at = at
        if line.startswith("Rebase:"):
            said.rebased = _fields(line)[-1]
        if line.startswith("CI fix:"):
            named = _CI_FIX.fullmatch(line.strip())
            said.pushed, said.saw = (named[1], named[2]) if named else ("", "")
    _round(said)
    return said


def _mode(line: str) -> str:
    """A brief's review mode, from its first `Review:` line: `none`, `after`, `twice`, or
    `review`. Any other word reads as `review`. Older briefs, written before the reviewer
    stopped running tests, use other words."""
    said = _second(line)
    return said if said in (NONE, AFTER, TWICE) else REVIEW


def after(text: str) -> bool:
    """Whether the brief says `Review: after`. Such a brief merges once its check passes, and
    its review's findings go to a cleanup row (`jbus cleanup`), so no review holds it."""
    return said_of(text).mode == AFTER


def asks_no_ruling(text: str) -> bool:
    """Whether the brief's mode needs no ruling from any review after the first. A brief in
    `after` mode merges once its check passes, and `twice` merges once its second review is
    written. So neither mode asks for a scoped review of the fix, a ruling on a decline or a
    drop, or a range-diff review after a rebase."""
    return said_of(text).mode in (AFTER, TWICE)


def _first_head(said: Said) -> str:
    """The head of a brief's first review. The first review is the first section that ran, so
    a section that wrote `Verdict: not run` and ran again at a later head is still the first."""
    return next((one.head for one in said.triage.sections if one.ran and one.head), "")


def second_review(text: str) -> tuple[str, ...]:
    """The heads of a `twice` brief's second review, or none for a brief in another mode. They
    are the heads that a section ran at, except the head of the first review. These are the
    heads that the fix pushed. `jbus cleanup` files the second review's findings as a
    cleanup row, and nobody answers them."""
    said = said_of(text)
    if said.mode != TWICE:
        return ()
    first = _first_head(said)
    ran = (one.head for one in said.triage.sections if one.ran and one.head not in ("", first))
    return tuple(dict.fromkeys(ran))


def _twice(said: Said, text: str) -> str:
    """What a `twice` brief still lacks. It needs the first review, then one fix round in which
    the crew answers that review's findings and pushes the fix, then a second review of a
    later head. A clean first review, or a round that declined every finding and pushed
    nothing, needs no second review, because nothing changed after the first review."""
    if not said.written:
        return NO_REVIEW
    first = _first_head(said)
    verdicts = [one.verdict for one in said.rounds if one.head == first]
    owed = said.triage.roster.owed(said.triage.sections)
    verdict = "" if owed or not verdicts else _worst(verdicts)
    if verdict not in ("clean", "findings"):
        return NO_VERDICT
    if verdict == "clean":
        return ""
    if not said.fixed:
        return NO_FIXED
    if said.fixed == first:
        return NOT_PUSHED
    pushed = bool(_COMMIT.fullmatch(said.fixed))
    if said.fixed != "none" and not pushed:
        return FIXED_NO_COMMIT
    found = [one for one in said.triage.findings if one.lead.head == first]
    short = unanswered(replace(said, triage=replace(said.triage, findings=found)))
    if short:
        return short
    if pushed and not second_review(text):
        return TWICE_UNWRITTEN.format(head=said.fixed[:12])
    return ""


def unanswered(said: Said) -> str:
    blocking = said.triage.blocking()
    old = [one for one in blocking if one.legacy]
    if old:
        found = sum(1 for one in said.triage.findings if one.blocks and one.legacy)
        return UNENDED.format(left=len(old), found=found)
    for why, reason in (
        (findings.UNANSWERED, UNANSWERED),
        (findings.UNCITED, UNCITED),
        (findings.REPEATED, REPEATED),
        (findings.UNASKED, RISK_UNASKED),
    ):
        named = [one for one in blocking if one.refused == why]
        if named:
            ids = ", ".join(one.id for one in named)
            risks = ", ".join(dict.fromkeys(one.risk for one in named))
            return reason.format(ids=ids, first=named[0].first, risks=risks)
    return ""


def _round(said: Said) -> None:
    if not said.rounds:
        return
    heads: dict[str, dict[tuple[str, bool], str]] = {}
    for number, one in enumerate(said.rounds):
        heads.setdefault(one.head or f"#{number}", {})[(one.by, one.scoped)] = one.verdict
    last = heads[said.rounds[-1].head or f"#{len(said.rounds) - 1}"]
    said.verdict = _worst(list(last.values()))
    said.ran = sum(
        any(verdict in ("clean", "findings") for verdict in one.values()) for one in heads.values()
    )
    if said.triage.roster.owed(said.triage.sections):
        said.verdict = ""


def _ci_fix(said: Said) -> tuple[str, str]:
    if said.pushed and said.saw == said.reviewed and not _COMMIT.fullmatch(said.fixed):
        return said.pushed, said.saw
    return "", ""


def short_of(text: str, head: str) -> str:
    said = said_of(text)
    verdict, reviewed, fixed = said.verdict, said.reviewed, said.fixed
    unrun = skills.missing(text)
    if unrun:
        return SKILLS_UNRUN.format(names=", ".join(unrun))
    if said.mode == NONE:
        return REVIEW_NONE
    if said.mode == AFTER:
        return ""
    if said.mode == TWICE:
        return _twice(said, text)
    if not said.written:
        return NO_REVIEW
    if verdict not in ("clean", "findings"):
        return NO_VERDICT
    if verdict == "findings" and not fixed:
        return NO_FIXED
    if verdict == "findings" and fixed == reviewed:
        return NOT_PUSHED
    if said.wider and (not reviewed or said.since in ("", reviewed)):
        return SECOND_UNWRITTEN
    if said.owed and not _scoped_since(said) and (not reviewed or said.asked in ("", reviewed)):
        return FIX_UNREVIEWED
    if fixed not in ("", "none") and not _COMMIT.fullmatch(fixed):
        return FIXED_NO_COMMIT
    if verdict == "findings" and _COMMIT.fullmatch(fixed) and head != fixed:
        if head == reviewed:
            return NOT_PUSHED
    return unanswered(said) or unruled(said)


def _scoped_since(said: Said) -> bool:
    """Whether a scoped pass that ran is written after the last `Scoped review:` line. That
    line names the review that the brief needs. When the crew pushed nothing, the pass may be
    of the head that the review saw, and the brief needs the pass only to rule on its
    declines."""
    return any(one.scoped and one.ran and one.line > said.asked_at for one in said.triage.sections)


def _ruled(named: tuple[findings.Finding, ...]) -> str:
    return " and ".join(_RULED.format(id=one.id, why=one.ruling.why) for one in named)


def unruled(said: Said) -> str:
    """Why the declines keep the pull request waiting on its crew, or nothing. The first cause
    is a blocking decline that no scoped pass has ruled on. The next is a decline that the
    pass did not uphold and that is on none of `findings.RISKS`. The crew fixes such a
    finding, and where the crew keeps its decline, the home decides. A decline on a risk is
    the user's to decide (`declines`)."""
    triage = said.triage
    left = triage.declines(findings.UNRULED)
    if left:
        return DECLINES_UNRULED.format(ids=", ".join(one.id for one in left))
    overruled = tuple(one for one in triage.declines(findings.OVERRULED) if not one.risk)
    return DECLINES_OVERRULED.format(ruled=_ruled(overruled)) if overruled else ""


def declines(text: str, *, user: Settings) -> tuple[str, str]:
    """The scoped pass's ruling on a risky decline, as a hold. It returns `hold` and the reason
    when the scoped pass did not uphold the crew's decline of a finding on one of
    `findings.RISKS`, which are review-triage's categories. Otherwise it returns two empty
    strings. Only such a decline is the user's to decide. The crew and its home decide a decline
    that concerns none of the risks, through `unruled`."""
    if asks_no_ruling(text):
        return "", ""
    named = tuple(one for one in findings.triage(text).declines(findings.OVERRULED) if one.risk)
    if not named:
        return "", ""
    risks = ", ".join(dict.fromkeys(one.risk for one in named))
    return "hold", RISKY_OVERRULED.format(user=user.user, ruled=_ruled(named), risks=risks)


def _named(said: Said, head: str) -> bool:
    if said.mode == TWICE:
        return head in (said.reviewed, said.fixed, said.rebased)
    if _COMMIT.fullmatch(said.fixed):
        return head == said.fixed
    return head in (said.reviewed, _ci_fix(said)[0], said.rebased)


def _covered(said: Said) -> str:
    if _COMMIT.fullmatch(said.fixed) and not (said.verdict == "clean" and said.ran > 1):
        return said.fixed
    return said.reviewed


def under_fix(rebase: Rebase | None, text: str, head: str) -> str:
    said = said_of(text)
    reviewed = said.reviewed
    if said.mode == TWICE:
        return ""
    if rebase is None and said.fixed == head != reviewed and _COMMIT.fullmatch(reviewed):
        return reviewed if _COMMIT.fullmatch(head) else ""
    return ""


def _seen(text: str) -> set[str]:
    heads = set()
    review = False
    for line in text.splitlines():
        if line.startswith("## "):
            review = line == "## Review"
        elif review and line.startswith("Head:"):
            heads.add(_second(line))
    return heads


@dataclass(frozen=True)
class Rebase:
    did: str
    files: tuple[str, ...]
    before: str
    head: str


def _told(text: str) -> Rebase | None:
    found = None
    for line in text.splitlines():
        if line.startswith("Rebase: patch "):
            said = _REBASE.fullmatch(line.strip())
            if not said:
                found = Rebase("", (), "", "")
            elif said[2]:
                found = Rebase("changed", tuple(said[2].split()), said[3], said[4])
            else:
                found = Rebase("unchanged", (), said[3], said[4])
        elif line.startswith("Rebase:"):
            found = None
    pushed, saw = _ci_fix(said_of(text))
    if found is None and pushed:
        return Rebase("changed", (), saw, pushed)
    return found


def rebase_of(text: str, head: str) -> Rebase | None:
    return _told(text) if _named(said_of(text), head) else None


def to_compare(rebase: Rebase | None) -> tuple[str, ...]:
    if rebase is None or rebase.did != "unchanged":
        return ()
    return (rebase.before, rebase.head)


def short_on_rebase(rebase: Rebase | None, patches: list[str | None]) -> str:
    if rebase is None:
        return ""
    if not rebase.did:
        return REBASE_UNSAID
    for commit, patch in zip(to_compare(rebase), patches, strict=True):
        if patch is None:
            return cannot_check(commit)
    if len(set(patches)) > 1:
        return REBASE_UNTRUE
    return ""


def cannot_check(commit: str) -> str:
    return CANNOT_CHECK.format(commit=commit)


def _changed(diff: str) -> tuple[Counter[str], Counter[str]]:
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    hunks = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            hunks = True
        elif hunks and line[:1] in ("+", "-") and line[1:].strip():
            (added if line[0] == "+" else removed)[line[1:].rstrip()] += 1
    return added, removed


def dropped(main: str, own: str, head: str) -> tuple[int, int]:
    theirs, gone_on_main = _changed(main)
    ours, gone_here = _changed(own)
    there = Counter(line.rstrip() for line in head.splitlines() if line.strip())
    return (theirs - gone_here - there).total(), (ours - gone_on_main - there).total()


@dataclass(frozen=True)
class NoPatch:
    commit: str


@dataclass(frozen=True)
class Drop:
    file: str
    mains: int
    own: int


def _lost(lost: tuple[Drop, ...]) -> str:
    mains = [_MAINS_LOST.format(count=one.mains, file=one.file) for one in lost if one.mains]
    own = [_OWN_LOST.format(count=one.own, file=one.file) for one in lost if one.own]
    return " and ".join([*mains, *own])


def acks(text: str, head: str) -> dict[str, tuple[int, int, str]]:
    found = {}
    for line in text.splitlines():
        said = _ACK.fullmatch(line.strip())
        if said and said[4] == head[:12]:
            found[said[1]] = (int(said[2]), int(said[3]), said[5])
    return found


def answered(text: str, head: str) -> tuple[Drop, ...]:
    return tuple(Drop(file, said[0], said[1]) for file, said in acks(text, head).items())


def _rulings(text: str, head: str) -> tuple[set[str], dict[str, str]] | None:
    rebase = _told(text)
    heads = {head, rebase.head} if rebase and rebase.head else {head}
    found = None
    review = covers = False
    ruled: dict[str, str | None] = {}
    said: dict[str, str | None] = {}
    for line in [*text.splitlines(), "## "]:
        if line.startswith("## "):
            if review and covers:
                found = True
                ruled |= said
            review, covers, said = line == "## Review", False, {}
        elif review and line.startswith("Head:"):
            covers = _second(line) in heads
        elif review and line.startswith(_NOT_UPHELD):
            file, _, why = line.removeprefix(_NOT_UPHELD).partition(": ")
            said[file.strip()] = why.strip()
        elif review and line.startswith(_UPHELD):
            said |= {file.strip(): None for file in line.removeprefix(_UPHELD).split(", ")}
    if not found:
        return None
    kept = {file for file, why in ruled.items() if why is None}
    return kept, {file: why for file, why in ruled.items() if why is not None}


def upheld(text: str, head: str) -> set[str]:
    ruled = _rulings(text, head)
    return ruled[0] if ruled else set()


def unexplained(lost: tuple[Drop, ...], text: str, head: str) -> tuple[Drop, ...]:
    said = acks(text, head)
    return tuple(one for one in lost if said.get(one.file, ())[:2] != (one.mains, one.own))


def drops(lost: tuple[Drop, ...], text: str, head: str, *, user: Settings) -> tuple[str, str]:
    lost = tuple(one for one in lost if one.mains or one.own)
    silent = unexplained(lost, text, head)
    if silent:
        return "wait", DROPPED.format(lost=_lost(silent), head=head[:12])
    if asks_no_ruling(text):
        return "", ""
    ruled = _rulings(text, head)
    kept, against = ruled or (set(), {})
    refused = [
        _REFUSED.format(file=one.file, why=against[one.file]) for one in lost if one.file in against
    ]
    if refused:
        return "hold", NOT_UPHELD.format(user=user.user, refused=" and ".join(refused))
    unruled = ", ".join(one.file for one in lost if one.file not in kept)
    if unruled and ruled:
        return "hold", UNRULED_DROPS.format(user=user.user, head=head[:12], files=unruled)
    if unruled:
        return "wait", SCOPED_UNRULED.format(files=unruled)
    return "", ""


def to_range_diff(rebase: Rebase | None, text: str, head: str) -> str | None:
    said = said_of(text)
    if said.mode in (AFTER, TWICE):
        return None
    fixed = bool(_COMMIT.fullmatch(said.fixed))
    if _ci_fix(said)[0] == head:
        return said.reviewed
    if rebase is None:
        if _named(said, head) or head == said.reviewed:
            return None
        covered, told = _covered(said), _told(text)
        if fixed and told and told.did and told.head == covered and covered not in _seen(text):
            covered = told.before
        return covered if _COMMIT.fullmatch(covered) else ""
    if not rebase.did or {rebase.head, head} & _seen(text):
        return None
    if fixed:
        return rebase.before if rebase.did == "changed" else None
    return said.reviewed if _COMMIT.fullmatch(said.reviewed) else ""


def _short(commits: str) -> str:
    return "..".join(commit[:12] for commit in commits.split(".."))


def rebase_note(verdict: Verdict | None) -> str:
    if verdict is None or not verdict.clean:
        return ""
    return _CARRIED.format(old=_short(verdict.old), new=_short(verdict.new))


def short_on_content(verdict: Verdict | None) -> str:
    if verdict is None or verdict.clean:
        return ""
    return CONTENT_CHANGED.format(command=verdict.command)


def short_on_github(one: PullRequest) -> str:
    if one.waiting:
        return NOT_PASSED.format(check=one.waiting[0])
    if one.mergeable == "MERGEABLE":
        return ""
    if one.mergeable == "CONFLICTING":
        return CONFLICTS
    return UNDECIDED


def patterns_of(text: str) -> tuple[str, ...]:
    lines = (line.strip() for line in text.splitlines())
    patterns = tuple(line for line in lines if line and not line.startswith("#"))
    for pattern in patterns:
        parts = pattern.removeprefix("/").removesuffix("/").split("/")
        if (
            any(part in ("", ".", "..") or "**" in part for part in parts)
            or pattern.startswith("!")
            or "\\" in pattern
        ):
            raise ValueError(f"{pattern} (the grammar: {GRAMMAR})")
    return patterns


def _protects(pattern: str, path: str) -> bool:
    *directories, name = path.split("/")
    wanted = pattern.strip("/").split("/")
    rooted = "/" in pattern.removesuffix("/")

    def same(parts: list[str]) -> bool:
        return len(parts) == len(wanted) and all(map(fnmatchcase, parts, wanted))

    if not pattern.endswith("/"):
        return same([*directories, name]) if rooted else fnmatchcase(name, pattern)
    if rooted:
        return same(directories[: len(wanted)])
    return any(fnmatchcase(directory, wanted[0]) for directory in directories)


def needs_the_user(
    one: PullRequest,
    patterns: tuple[str, ...],
    left: tuple[str, ...] | None = (),
    *,
    user: Settings,
) -> str:
    for path in (*one.files, *(left or ())):
        if any(_protects(pattern, path) for pattern in patterns):
            return TOUCHES.format(user=user.user, path=path)
    if left is None:
        return RENAMES_UNSAID.format(user=user.user)
    if len(one.files) < one.changed:
        return UNLISTED.format(user=user.user, listed=len(one.files), changed=one.changed)
    return ""


@dataclass(frozen=True)
class Judged:
    path: str = ""
    tip: str = ""
    rules: bool = False
    fresh: str = ""
    gate: str = ""


def guarded_path(one: PullRequest, patterns: tuple[str, ...], left: tuple[str, ...] = ()) -> str:
    for path in (*one.files, *left):
        if any(_protects(pattern, path) for pattern in patterns):
            return path
    return ""


def changes_the_rules(one: PullRequest, left: tuple[str, ...] = ()) -> bool:
    return bool(guarded_path(one, (RULES,), left))


def short_of_guarded(one: PullRequest, text: str, rebase: Rebase | None, carried: str) -> str:
    if one.started is None:
        return NO_START
    said = said_of(text)
    if carried or one.head in (said.reviewed, said.fixed):
        return ""
    if rebase is not None and rebase.did == "unchanged" and rebase.head == one.head:
        return ""
    return NOT_SEEN


def stale_paths(
    pr_files: tuple[str, ...],
    renamed_from: tuple[str, ...],
    main_paths: tuple[str, ...],
    ci_paths: tuple[str, ...],
) -> tuple[str, ...]:
    ours = {*pr_files, *renamed_from}
    stale = (
        path
        for path in main_paths
        if path in ours or any(_protects(pattern, path) for pattern in ci_paths)
    )
    return tuple(dict.fromkeys(stale))


def modules(path: str) -> tuple[str, ...]:
    if not path.endswith(".py"):
        return ()
    parts = path[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return ()
    return tuple(".".join(parts[start:]) for start in range(len(parts)))


def imports(path: str, text: str) -> set[str]:
    if not path.endswith(".py"):
        return set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    package = path.endswith("/__init__.py") or path == "__init__.py"
    full = modules(path)[:1]
    homes = [name.split(".") if package else name.split(".")[:-1] for name in full]
    loaded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                up = node.level - 1
                bases = [home[: len(home) - up] for home in homes if len(home) >= up]
                froms = [
                    ".".join([*base, *(node.module or "").split(".")]).strip(".") for base in bases
                ]
            else:
                froms = [node.module or ""]
            named = [f"{base}.{alias.name}".strip(".") for base in froms for alias in node.names]
            named += froms
        else:
            continue
        for name in filter(None, named):
            parts = name.split(".")
            loaded.update(".".join(parts[:end]) for end in range(1, len(parts) + 1))
    return loaded


def uses(path: str, text: str, other: str) -> bool:
    if other.endswith("conftest.py") and path.endswith(".py"):
        if path.startswith(other[: -len("conftest.py")]):
            return True
    if "/" in other and other in text:
        return True
    return bool(imports(path, text) & set(modules(other)))


def callers_and_dependencies(ours: dict[str, str], theirs: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        path
        for path, text in theirs.items()
        if any(uses(path, text, own) or uses(own, ours[own], path) for own in ours)
    )


def short_on_main(
    stale: tuple[str, ...],
    since: datetime,
    default: str = "main",
    needs: str = FRESH_CHECK,
    *,
    user: Settings,
) -> str:
    if not stale:
        return ""
    paths = _first_five(stale)
    return MAIN_CHANGED.format(default=default, paths=paths, since=user.clock(since), needs=needs)


def related_note(stale: tuple[str, ...]) -> str:
    return _RELATED_NOTE.format(paths=_first_five(stale))


def _first_five(paths: tuple[str, ...]) -> str:
    more = _MORE.format(more=len(paths) - 5) if len(paths) > 5 else ""
    return " ".join(paths[:5]) + more


def fresh_note(command: str, head: str, tip: str) -> str:
    return _FRESH_NOTE.format(command=command, passed=PASSED, head=head[:12], tip=tip[:12])


def fresh_kept(command: str, head: str, was: str, tip: str) -> str:
    return fresh_note(command, head, was) + _FRESH_KEPT.format(tip=tip[:12])


def fresh_skipped(tree: str, at: str, head: str, tip: str) -> str:
    return _FRESH_SKIPPED.format(tree=tree, at=at, head=head[:12], tip=tip[:12])


def short_on_fresh(result: str, command: str, head: str, tip: str) -> str:
    if result == PASSED:
        return ""
    return FRESH_FAILS.format(command=command, head=head[:12], tip=tip[:12])


def fresh_command(text: str) -> str:
    return "".join(text.strip().splitlines()[:1]).strip()


def gate_held(why: str) -> bool:
    """Whether a reason is the merge gate's hold, which only a passing gate lifts."""
    return bool(GATE_HELD.fullmatch(why))


def first_line(output: str, code: int) -> str:
    """The gate's first line of output, or its exit code where it printed none."""
    return next((line.strip() for line in output.splitlines() if line.strip()), f"exit {code}")
