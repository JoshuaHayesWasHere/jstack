from __future__ import annotations

import functools
import re
import string
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from jbriefs import findings, meets, proved, skills
from jbriefs.findings import CLEANUP, NONE, REVIEW, TWICE
from jmerge.rangediff import Verdict
from jmerge.stacked import Stacked
from jsettings import Settings

_COMMIT = re.compile(r"[0-9a-f]{40}")
_CHECKED = re.compile(r"Checked: .+ exit (\d+) at ([0-9a-f]{40})")
_RANKS = {"clean": 0, "findings": 1}
_ACK = re.compile(
    r"Dropped on rebase: (.+?), (\d+) of main's, (\d+) of its own, at ([0-9a-f]{12}): (.+)"
)
_UPHELD = "Drops: upheld "
_NOT_UPHELD = "Drops: not upheld "

_MIGRATION = re.compile(r"(\d+)_")
_VALUE = ".+"


class Reason(str):
    """A reason `jmerge` gives for a pull request that does not merge: its text, the step it
    puts the pull request on, and its code. The code is the fixed name a `wait` or `hold` line
    carries beside the text (`lines.waits`), the constant's name in kebab case, so a reader
    tells one reason from another without reading the text. `format` keeps the step and the
    code, so a filled-in reason still says which one it is."""

    step: str
    code: str = ""

    def __new__(cls, step: str, text: str, code: str = "") -> Reason:
        made = super().__new__(cls, text)
        made.step = step
        made.code = code
        return made

    def format(self, *args: object, **kwargs: object) -> Reason:
        return Reason(self.step, super().format(*args, **kwargs), self.code)

    @functools.cached_property
    def pattern(self) -> str:
        """The reason's text as a pattern, each field a value. It is made once for each reason:
        the view reads a step of every line of the logs, and making it on each read held each
        of its answers for seconds."""
        return "".join(
            re.escape(literal) + (_VALUE if name is not None else "")
            for literal, name, _, _ in string.Formatter().parse(self)
        )


def reasons() -> dict[str, Reason]:
    return {name: value for name, value in globals().items() if isinstance(value, Reason)}


UNKNOWN = "unknown"
"""The code of a reason that no rule of `rules` names: the view shows it in its Unknown lane."""
ELSEWHERE = (
    ("fresh-check", "check", r"^a fresh check "),
    ("unfetched", "check", r"could not be fetched"),
)
"""The code, step and pattern of each reason `jmerge` writes as plain text, from outside
`Reason` (its range-diff and its fetch of the base), and of the fresh check an older `jmerge`
queued, which the last week of a log still has. The fresh check's pattern holds to the start of
the text, so that `MAIN_CHANGED`, which also ends `a fresh check`, keeps its own code."""


def rules() -> tuple[tuple[str, str, str], ...]:
    """The `(code, step, pattern)` of each reason `jmerge` writes, in the order `code_of` tries
    them: `ELSEWHERE` first, then each `Reason` in the order this module declares it, those whose
    text starts with a field (`<check> has failed`) after the rest. Each pattern matches from the
    start of the reason. `ELSEWHERE` comes first so that the plain text of a reason no `Reason`
    made is on its own step, and a field comes last since it matches the start of any text: a
    refused merge whose error says `the required check has failed` is `BASE_MERGE_REFUSED`'s,
    not `CHECK_FAILED`'s."""
    named = sorted(reasons().values(), key=lambda one: one.pattern.startswith(_VALUE))
    return ELSEWHERE + tuple((one.code, one.step, "^" + one.pattern) for one in named)


def code_of(why: str) -> str:
    """The code of a reason: a `Reason`'s own, and for plain text the code of the first rule of
    `rules` whose pattern matches it. A line from before the codes is read this way too.
    `UNKNOWN` where no rule names it."""
    if isinstance(why, Reason) and why.code:
        return why.code
    return next((code for code, _, pattern in rules() if re.search(pattern, why)), UNKNOWN)


def codes() -> frozenset[str]:
    """Every code a line can carry: each rule's, and `UNKNOWN`."""
    return frozenset(code for code, _, _ in rules()) | {UNKNOWN}


def step_of(code: str) -> str:
    """The step a code puts a pull request on, or nothing for `UNKNOWN`, `other-home`, and a
    code no rule has."""
    return next((step for one, step, _ in rules() if one == code), "")


OTHER_HOME = Reason("", "another home's")
REQUIRED = ("check",)
MERGE_OFF = Reason("hold", "auto-merge is off for this repo")
NO_BRIEF = Reason("result", "no brief has a Result that names it")
HAND_DRAFT = Reason("result", "a draft, which jmerge never marks ready")
GRAMMAR = "features/jmerge/docs/jmerge.md#patterns"
MAIN_MOVED = Reason("check", "{base} moved while it was judged")
MERGE_FAILED = Reason("check", "the merge failed")
NO_MESSAGES = Reason("check", "its commit messages could not be read for the squash")
KEPT = "every line kept"
FRESH_CONFLICT = Reason("rebase", "it conflicts with today's main")
NO_HEAD = Reason("second", "its review names no head to compare its rebase with")

BASE = Reason("rebase", "its base is {base}, not {default}")
REVIEW_NONE = Reason("hold", "its brief says Review: none, so it needs the user's word")
NO_REVIEW = Reason("review", "it has no review yet")
SKILLS_UNRUN = Reason(
    "result",
    "its Result has no artifact under Skills run: for {names}, which its brief names",
)
PROVED_MISSING = Reason(
    "result",
    "it changes {tests}, and its Result has no Proved: line that shows them fail at its base "
    "and pass at its head",
)
PROVED_UNREAD = Reason("result", "its Result's Proved: line {fault}")
PROVED_NOT_EXEMPT = Reason(
    "result", "its Proved: line says it changes no test, and it changes {tests}"
)
PROVED_NOT_KIND = Reason("result", "its Proved: line says none, {kinds}, and it changes {path}")
PROVED_UNNAMED = Reason("result", "its Proved: line does not name {tests}, which it changes")
PROVED_BASE_PASSED = Reason(
    "result",
    "its Proved: line says its tests exit {exit} at its base {base}, not 1: they prove nothing "
    "there",
)
PROVED_HEAD_FAILED = Reason(
    "result", "its Proved: line says its tests exit {exit} at its head {head}, not 0"
)
PROVED_STALE = Reason(
    "result",
    "its Proved: line is of {at}, and its patch changed after it: the proof block runs again at "
    "{head}",
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
MEETS_NO = Reason(
    "findings",
    "its review at {head} says the brief is not met, {met} of {count}: Done when {lines} unmet, "
    "so a fix and a scoped review whose line says yes, or the user's Waived: line",
)
MEETS_UNREAD = Reason(
    "review",
    "its review at {head} has no Meets the brief line of the shape yes, <n> of <n> or no, <m> of "
    "<n>",
)
MEETS_MISCOUNTED = Reason(
    "review", "its review at {head} counts {said} Done when lines, and its brief has {count}"
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
CANNOT_CHECK = Reason(
    "rebase",
    "its rebase cannot be checked: the patch of {commit} cannot be worked out in the main checkout",
)
DROPPED = Reason("rebase", "the rebase dropped {lost} with no Dropped on rebase line at {head}")
NOT_UPHELD = Reason("hold", "needs {user}, the review did not uphold the drop in {refused}")
UNRULED_DROPS = Reason(
    "hold",
    "needs {user}, the review of {head} did not rule on the drops in {files}",
)
SCOPED_UNRULED = Reason(
    "second",
    "the scoped review has not ruled on the drops in {files}; scoped review of {command}",
)
CONTENT_CHANGED = Reason(
    "second",
    "the rebase changed the content after its review; scoped review of {command}",
)
NOT_PASSED = Reason("check", "{check} has not passed")
CHECK_FAILED = Reason("check", "{check} has failed")
NO_RUN = Reason("check", "{check} has no run at {head}")
CANCELLED_UNRUN = Reason("check", "its {check} was cancelled, and GitHub did not run it again")
LIVE_RUN = Reason("check", "{check}'s run at {head} is {state}")
CONFLICTS = Reason("rebase", "it conflicts with its base")
UNDECIDED = Reason("check", "GitHub has not decided whether it merges")
TOUCHES = Reason("hold", "needs {user}, touches {path}")
RENAMES_UNSAID = Reason("hold", "needs {user}, GitHub did not say which paths its renames left")
UNLISTED = Reason("hold", "needs {user}, GitHub listed {listed} of the {changed} files it changes")
MAIN_CHANGED = Reason(
    "check",
    "{default} changed {paths} after its check started at {since}; it needs a fresh check",
)
"""The wait an older `jmerge` wrote for a check that main moved under, which the last week of a
log still has, and which jbus still reads as a rebase (`jbus.rebase.STALE`)."""
ROW_HELD = Reason("hold", "its queue row is held: approve it again to let it merge")
NO_GO = Reason(
    "hold",
    "its queue row has no go: the user's go (jbus plan go <entry> --message <thread>/<message>), "
    "or the bot's, lets it merge",
)
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
    "check",
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
BASE_MERGE_ASKED = Reason(
    "check",
    "GitHub was asked to merge {base} at {tip} into it: its check failed before {base} moved",
)
BASE_MERGE_REFUSED = Reason("check", "GitHub did not merge {base} at {tip} into it: {why}")
BASE_MERGE_DUE = Reason(
    "check", "its check failed before {base} moved: GitHub is to merge {base} at {tip} into it"
)
BASE_MOVED_ASKED = Reason(
    "check",
    "GitHub was asked to merge {base} at {tip} into it: {base} moved after its check started",
)
BASE_MOVED_DUE = Reason(
    "check", "{base} moved after its check started: GitHub is to merge {base} at {tip} into it"
)
UNMERGED = Reason("check", "its head could not be merged over today's base ({why})")
_MAINS_LOST = "{count} of main's lines in {file}"
_OWN_LOST = "{count} of its own in {file}"
_REFUSED = "{file}: {why}"
_RULED = "{id}: {why}"
_CARRIED = "review carried over: range-diff {old} {new} clean"


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
    unrun: tuple[str, ...] = ()
    live: tuple[tuple[str, str], ...] = ()
    """Each required check with no run of its own listed at the head whose workflow GitHub is
    running there, with `queued` or `running` (`live`)."""
    passed_at: datetime | None = None
    """The second the last of the required checks passed at the head (`passed_at`)."""
    removed: tuple[str, ...] = ()
    """The files it deletes, which `files` lists too."""


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


def passed_at(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> datetime | None:
    """The second every required check had passed at the head: the latest end of the run
    `latest` picks of each, or None while one has not passed or GitHub gives no end of one. A
    status names no end, so its start is when it was set."""
    if waiting(rollup, required):
        return None
    ends = [
        _at(one.get("completedAt")) or (_at(one.get("startedAt")) if one.get("state") else None)
        for name in required
        for one in latest(rollup, name)
    ]
    return None if not ends or None in ends else max(at for at in ends if at is not None)


def required_of(text: str) -> tuple[str, ...]:
    """The checks that a repo's `required-checks` file names, one to a line, or `REQUIRED`
    where it names none."""
    return tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())) or (
        REQUIRED
    )


def waiting(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> tuple[str, ...]:
    """The required checks whose latest run has not passed, in `required`'s order."""
    return tuple(name for name in required if not passed(rollup, name))


def live(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> tuple[tuple[str, str], ...]:
    """The required checks GitHub lists no run of at the head while it runs other jobs of the
    workflow of that name there, each with `running` where one of those jobs is in progress and
    `queued` where they all wait. GitHub lists a job only once the jobs it needs have ended, so
    the check workflow's `check` is not listed while its shards run (merge-wait-1, 2026-10-28)."""
    found = []
    for name in required:
        if latest(rollup, name):
            continue
        states = {
            one.get("status")
            for one in rollup
            if one.get("workflowName") == name and one.get("status") != "COMPLETED"
        }
        if "IN_PROGRESS" in states:
            found.append((name, "running"))
        elif states:
            found.append((name, "queued"))
    return tuple(found)


def unrun(rollup: list[dict], required: tuple[str, ...] = REQUIRED) -> tuple[str, ...]:
    """The required checks GitHub lists no run of at the head, and no job of their workflow at
    work there, in `required`'s order: no runner is at work on them, as for a workflow the head's
    merge with its base does not have."""
    at_work = dict(live(rollup, required))
    return tuple(name for name in required if not latest(rollup, name) and name not in at_work)


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


def unrun_only(one: PullRequest) -> bool:
    """Whether the one thing GitHub holds against the pull request is a required check with no
    run at its head: every required check that has not passed has no run, and it merges
    cleanly."""
    return bool(one.waiting) and one.waiting == one.unrun and one.mergeable == "MERGEABLE"


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
        unrun=unrun(listed.get("statusCheckRollup") or [], required),
        live=live(listed.get("statusCheckRollup") or [], required),
        passed_at=passed_at(listed.get("statusCheckRollup") or [], required),
        removed=tuple(one["path"] for one in listed["files"] if one.get("changeType") == "DELETED"),
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
        removed=tuple(file["filename"] for file in every if file.get("status") == "removed"),
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


def held(
    one: PullRequest,
    default: str,
    stacked: Stacked | None = None,
    bases: tuple[str, ...] = (),
) -> str:
    """Why a pull request is held by its base, or nothing. It merges into the default branch, or
    into a merge base its project names (`bases`, `jbus project bases --add`), on the same
    rules. A link jbus stacked sits on its base's branch until that row merged: it is not held
    for it, and waits (`on_stack`)."""
    on_base = stacked is not None and one.base == stacked.branch
    if one.base != default and one.base not in bases and not on_base:
        return BASE.format(base=one.base, default=default)
    return ""


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
    wider: bool = False
    since: str = ""
    owed: bool = False
    asked: str = ""
    asked_at: int = -1
    found: int = 0
    ended: int = 0
    second: bool = False
    scoped: bool = False
    owes: bool = False
    rounds: list[Round] = field(default_factory=list)
    triage: findings.Triage = field(default_factory=findings.Triage)
    decided: bool = False
    checked: dict[str, str] = field(default_factory=dict)


def said_of(text: str) -> Said:
    said = Said()
    triage = findings.triage(text)
    said.triage = triage
    said.mode = triage.mode
    said.written = bool(triage.sections)
    said.rounds = [
        Round(one.verdict, one.head, one.found, one.by, one.scoped)
        for one in triage.roster.counted(triage.sections)
    ]
    said.reviewed = next((one.head for one in reversed(triage.sections) if one.head), "")
    sent = [one for one in triage.findings if one.blocks]
    said.found, said.ended = len(sent), sum(one.ended for one in sent)
    first = triage.sections[0].line if triage.sections else -1
    fixed_at = -1
    for at, line in enumerate(text.splitlines()):
        fixed = _second(line).rstrip(",") if line.startswith("Fixed:") else ""
        if _COMMIT.fullmatch(fixed) or fixed == "none":
            said.fixed, fixed_at = fixed, at
        if line.startswith(("Second pass:", "Scoped review:")) and 0 <= first < at:
            said.decided = True
        checked = _CHECKED.fullmatch(line.strip())
        if checked:
            said.checked[checked[2]] = checked[1]
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
    if said.mode == REVIEW and _stale(triage.sections, said.reviewed, fixed_at):
        said.fixed = ""
    _round(said)
    said.owes = _owes(said)
    return said


def _stale(sections: list[findings.Section], reviewed: str, at: int) -> bool:
    """Whether the `Fixed:` line at index `at` answers an earlier round than the last: a review
    is written above it, and the first section of the last round, the head `reviewed`, below
    it. Such a line is read as no line for the last round, so `unwritten_fixed` reads the one
    that round is owed. A `twice` brief's line answers its first review, and is read as it is."""
    if at < 0 or not reviewed:
        return False
    starts = [one.line for one in sections if one.head == reviewed]
    return any(one.line < at for one in sections) and min(starts, default=at) > at


def _owes(said: Said) -> bool:
    """Whether the last round's verdict owes the crew a line: a `Fixed:` line, and a push for
    what it fixed. `findings.owes` decides it, the rule `jbriefs --findings --left` reads too."""
    if said.verdict != "findings":
        return False
    sections = said.triage.sections
    return findings.owes(
        said.triage, {n for n, one in enumerate(sections) if one.head == said.reviewed}
    )


def asks_no_ruling(text: str) -> bool:
    """Whether the brief's mode needs no ruling from any review after the first: a `twice`
    brief has two reviews and no more, and the day's warnings row (`cleanup`) gets one, so
    neither asks for a scoped review of the fix, a ruling on a decline or a drop, or a range-diff
    review after a rebase."""
    return said_of(text).mode in (TWICE, CLEANUP)


def _first_head(said: Said) -> str:
    """The head of a brief's first review. The first review is the first section that ran, so
    a section that wrote `Verdict: not run` and ran again at a later head is still the first."""
    return next((one.head for one in said.triage.sections if one.ran and one.head), "")


def second_review(text: str) -> tuple[str, ...]:
    """The heads of a brief's reviews after the first: the heads a later section ran at
    (`findings.Section.later`). For a `twice` brief they are the heads that the fix pushed."""
    ran = (one.head for one in findings.triage(text).sections if one.ran and one.later)
    return tuple(dict.fromkeys(ran))


def _twice(said: Said, text: str, meets_short: str = "") -> str:
    """What a `twice` brief still lacks. It needs the first review, then one fix round in which
    the crew answers that review's findings and pushes the fix, then a second review of a
    later head, whose errors the crew answers too, by id and with a push after it,
    and no third review follows. A clean first review, or a round that declined every finding
    and pushed nothing, needs no second review, because nothing changed after the first review.
    A clean first review whose judgement of the brief holds the merge (`meets_short`) is owed
    what one with findings is: a fix, and the second review of the head it pushed."""
    if not said.written:
        return NO_REVIEW
    first = _first_head(said)
    verdicts = [one.verdict for one in said.rounds if one.head == first]
    owed = said.triage.roster.owed(said.triage.sections)
    verdict = "" if owed or not verdicts else _worst(verdicts)
    if verdict not in ("clean", "findings"):
        return NO_VERDICT
    if verdict == "clean" and not (meets_short and said.reviewed == first):
        return ""
    if not said.fixed:
        return NO_FIXED
    if said.fixed == first:
        return NOT_PUSHED
    second = second_review(text)
    if second and said.verdict not in ("clean", "findings"):
        return NO_VERDICT
    if second and said.owes and said.fixed == said.reviewed:
        return NOT_PUSHED
    short = unanswered(said)
    if short or second:
        return short
    if _COMMIT.fullmatch(said.fixed):
        return TWICE_UNWRITTEN.format(head=said.fixed[:12])
    return ""


def _cleanup(said: Said) -> str:
    """What the day's warnings row still lacks. It gets one review, of its own diff, and only
    that review's errors go to the crew, so it waits on a `Fixed:` line, a push and an answer by
    id only for an error. No scoped review follows the fix and no pass rules on a decline."""
    if not said.written:
        return NO_REVIEW
    if said.verdict not in ("clean", "findings"):
        return NO_VERDICT
    if not said.owes:
        return ""
    if not said.fixed:
        return NO_FIXED
    if said.fixed == said.reviewed:
        return NOT_PUSHED
    return unanswered(said)


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


def short_on_meets(text: str, heard: Collection[meets.Waiver] = ()) -> str:
    """Why the last round's judgement of the brief holds the merge, or nothing
    (`jbriefs.meets.reading`): it says `no`, or a section of it has no line `jmerge` reads, or
    one whose count is not the brief's. `heard` holds the brief's `Waived:` lines whose word jbus
    checked."""
    said = meets.reading(text, heard)
    head = said.head[:12]
    if said.word == meets.NO:
        lines = ", ".join(map(str, said.unmet))
        return MEETS_NO.format(head=head, met=said.met, count=said.count, lines=lines)
    if said.word == meets.UNREAD:
        return MEETS_UNREAD.format(head=head)
    if said.word == meets.MISCOUNTED:
        return MEETS_MISCOUNTED.format(head=head, said=said.said, count=said.count)
    return ""


def short_of(text: str, head: str, heard: Collection[meets.Waiver] = ()) -> str:
    """What the pull request is short of at `head`, by its brief, or nothing. Every path that
    reads a review ends on the last round's judgement of the brief (`short_on_meets`), with the
    waivers whose words are in `heard`."""
    said = said_of(text)
    unrun = skills.missing(text)
    if unrun:
        return SKILLS_UNRUN.format(names=", ".join(unrun))
    if said.mode == NONE:
        return REVIEW_NONE
    if said.mode == TWICE:
        short = _twice(said, text, short_on_meets(text, heard))
    elif said.mode == CLEANUP:
        short = _cleanup(said)
    else:
        short = _review(said, head)
    return short or short_on_meets(text, heard)


_TEST = re.compile(r"(?:test_[^/]*|[^/]*_test)\.py")


def changed_tests(one: PullRequest) -> tuple[str, ...]:
    """The test files the pull request adds or changes: each `test_*.py` or `*_test.py` it lists
    and does not delete."""
    gone = set(one.removed)
    return tuple(
        path for path in one.files if path not in gone and _TEST.fullmatch(path.rsplit("/", 1)[-1])
    )


def _of_kind(path: str, kind: str) -> bool:
    parts = path.split("/")
    return any(
        any(fnmatchcase("/".join(parts[at:]), pattern) for at in range(len(parts)))
        if "/" in pattern
        else fnmatchcase(parts[-1], pattern)
        for pattern in proved.EXEMPT[kind]
    )


def short_on_proved(
    text: str, one: PullRequest, carries: Callable[[str], bool] = lambda at: False
) -> str:
    """Why the brief's `Proved:` line does not prove the pull request, or nothing
    (`proved.proved`). A pull request that changes tests needs the line to name each of them,
    with their run over its merge-base's code ending 1, a failure, and at its head ending 0. A
    run that passes at the base, or ends on anything but a failure there (no test collected, a
    time limit), passes vacuously. One that changes no test needs no line, and where it says
    `none, <kind>` each file it changes is of a kind it names. A line of another head holds
    where the head carries that head's patch unchanged (`carries`, the range-diff `jmerge` reads
    after a rebase or a merge of the base): a push that changed the patch, a fix for a review's
    finding most of all, may have changed the tests too."""
    tests = changed_tests(one)
    said = proved.proved(text)
    if said is None:
        return PROVED_MISSING.format(tests=", ".join(tests)) if tests else ""
    if said.fault:
        return PROVED_UNREAD.format(fault=said.fault)
    if said.kinds:
        if tests:
            return PROVED_NOT_EXEMPT.format(tests=", ".join(tests))
        other = next(
            (path for path in one.files if not any(_of_kind(path, kind) for kind in said.kinds)),
            "",
        )
        kinds = " and ".join(said.kinds)
        return PROVED_NOT_KIND.format(kinds=kinds, path=other) if other else ""
    unnamed = [path for path in tests if path not in said.tests]
    if unnamed:
        return PROVED_UNNAMED.format(tests=", ".join(unnamed))
    if said.base_exit != 1:
        return PROVED_BASE_PASSED.format(exit=said.base_exit, base=said.base[:12])
    if said.head_exit != 0:
        return PROVED_HEAD_FAILED.format(exit=said.head_exit, head=said.head[:12])
    if said.head != one.head and not carries(said.head):
        return PROVED_STALE.format(at=said.head[:12], head=one.head[:12])
    return ""


def _review(said: Said, head: str) -> str:
    verdict, reviewed, fixed = said.verdict, said.reviewed, said.fixed
    if not said.written:
        return NO_REVIEW
    if verdict not in ("clean", "findings"):
        return NO_VERDICT
    if said.owes and not fixed:
        return NO_FIXED
    if said.owes and fixed == reviewed:
        return NOT_PUSHED
    if said.wider and (not reviewed or said.since in ("", reviewed)):
        return SECOND_UNWRITTEN
    if said.owed and not _scoped_since(said) and (not reviewed or said.asked in ("", reviewed)):
        return FIX_UNREVIEWED
    if said.owes and _COMMIT.fullmatch(fixed) and head != fixed:
        if head == reviewed:
            return NOT_PUSHED
    return unanswered(said) or unruled(said)


@dataclass(frozen=True)
class Unwritten:
    """The `Fixed:` line a crew did not write, as `jmerge` reads it from the brief and git
    instead. A `reason` is `Fixed: none needed, <reason>`, and with none the line names the
    commit pushed for the findings after `reviewed`, the head the last review saw, which git
    gives (`cli.Repo.kept_fix`). `jmerge` judges the brief with the line and writes nothing
    back."""

    reviewed: str
    reason: str = ""


def unwritten_fixed(text: str, head: str) -> Unwritten | None:
    """The `Fixed:` line the brief has not got at `head`, or None. It is read where the last
    round's verdict owes the crew one (`_owes`), the brief has no `Fixed:` line that names a
    full commit or the word none, `jbriefs --findings --left` says `write Fixed:` (its shape is
    `findings.fixed_shape`), a `Checked:`
    line says the check command exited 0 at `head`, and, in `review` mode, a `Second pass:` or
    `Scoped review:` line says whether the fix is owed a review."""
    said = said_of(text)
    if said.mode == NONE or not said.owes or said.fixed:
        return None
    if said.checked.get(head) != "0" or (said.mode == REVIEW and not said.decided):
        return None
    shape = findings.fixed_shape(said.triage)
    if shape is None:
        return None
    pushed, why = shape
    if not pushed:
        return Unwritten(said.reviewed, why)
    return Unwritten(said.reviewed) if _COMMIT.fullmatch(said.reviewed) else None


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
    if said.mode in (TWICE, CLEANUP):
        return head in (said.reviewed, said.fixed)
    if _COMMIT.fullmatch(said.fixed):
        return head == said.fixed
    return head == said.reviewed


def _covered(said: Said) -> str:
    if _COMMIT.fullmatch(said.fixed) and not (said.verdict == "clean" and said.ran > 1):
        return said.fixed
    return said.reviewed


def under_fix(text: str, head: str) -> str:
    """The head the last review saw, where the `Fixed:` commit after it is `head` or the commit
    `jmerge` compares `head` with (`to_range_diff`), or empty. That commit may be the one a
    rebase made of the fix, and then `jmerge` compares from the head the crew kept before that
    rebase, as for a `Fixed:` line it reads from git (`cli.Repo.kept_fix`)."""
    said = said_of(text)
    reviewed, fixed = said.reviewed, said.fixed
    if said.mode in (TWICE, CLEANUP) or fixed == reviewed or not _COMMIT.fullmatch(reviewed):
        return ""
    if fixed == head:
        return reviewed if _COMMIT.fullmatch(head) else ""
    return reviewed if to_range_diff(text, head) == fixed else ""


@dataclass(frozen=True)
class Rebase:
    """A move of the patch from the head `before` to the head `head`, and the files either
    patch changes. `jmerge` works each one out from git (`cli.Repo.rebase_since_review`): a
    crew writes nothing about its rebase or about a push for a failed check, and a `Rebase:` or
    `CI fix:` line in a brief is read as no line."""

    files: tuple[str, ...]
    before: str
    head: str


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
    """The drops ruled on by a review of `head`, or of the head a push after the review left:
    the reviewed head where the `Fixed:` line names `head`. None where no such review is
    written."""
    told = said_of(text)
    heads = {head, told.reviewed if told.fixed == head else ""} - {""}
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


def drops(
    lost: tuple[Drop, ...], text: str, head: str, *, user: Settings, command: str = "nothing"
) -> tuple[str, str]:
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
        return "wait", SCOPED_UNRULED.format(files=unruled, command=command)
    return "", ""


def to_range_diff(text: str, head: str) -> str | None:
    """The commit the review covers, which `jmerge` compares `head` with, or None where the
    review is of `head` itself. That commit is the `Fixed:` commit or the head the last review
    saw (`_covered`), also for a push for a failed check that no line names. An empty string is
    a review that names no commit to compare with."""
    said = said_of(text)
    if said.mode in (TWICE, CLEANUP):
        return None
    if _named(said, head) or head == said.reviewed:
        return None
    covered = _covered(said)
    return covered if _COMMIT.fullmatch(covered) else ""


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
    if one.waiting and one.waiting[0] in one.unrun:
        return NO_RUN.format(check=one.waiting[0], head=one.head[:12])
    if one.waiting and (state := dict(one.live).get(one.waiting[0])):
        return LIVE_RUN.format(check=one.waiting[0], head=one.head[:12], state=state)
    if one.waiting:
        failed = one.waiting[0] in one.failed
        return (CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])
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


def protected_path(one: PullRequest, patterns: tuple[str, ...], left: tuple[str, ...] = ()) -> str:
    for path in (*one.files, *left):
        if any(_protects(pattern, path) for pattern in patterns):
            return path
    return ""


def needs_the_user(
    one: PullRequest,
    patterns: tuple[str, ...],
    left: tuple[str, ...] | None = (),
    *,
    user: Settings,
) -> str:
    path = protected_path(one, patterns, left or ())
    if path:
        return TOUCHES.format(user=user.user, path=path)
    if left is None:
        return RENAMES_UNSAID.format(user=user.user)
    if len(one.files) < one.changed:
        return UNLISTED.format(user=user.user, listed=len(one.files), changed=one.changed)
    return ""


@dataclass(frozen=True)
class Judged:
    tip: str = ""


MERGING = Reason("check", "another run of jmerge is merging into its base")
BROWSER = "browser"
"""The check browser.yml's job reports. It runs on a pull request into main that changes the view,
and is no required check: a head with no run of it waits for none (`browser`)."""
BROWSER_FAILED = "failed"
BROWSER_PENDING = "pending"
MAIN_BROWSER_RED = Reason("check", "its browser run failed at {head}, as main's did at {sha}")
"""Declared before `BROWSER_RED`, whose text starts its own, so that `code_of` reads a line of
it with no code as this one: jbus tells no crew to fix main's red."""
BROWSER_RED = Reason("check", "its browser run failed at {head}")


def browser(rollup: list[dict]) -> str:
    """The state of the head's browser run (`BROWSER`): `BROWSER_FAILED` where its latest run
    ended and failed, `BROWSER_PENDING` where it has not ended, and nothing where there is none,
    or it passed, was skipped or was cancelled."""
    if failed(rollup, (BROWSER,)):
        return BROWSER_FAILED
    going = ("PENDING", "EXPECTED")
    for one in latest(rollup, BROWSER):
        if one.get("state") in going or one.get("status") not in ("COMPLETED", None):
            return BROWSER_PENDING
    return ""


def _name_codes() -> None:
    """Give each `Reason` its code: its name in lower case, words joined by `-`."""
    for name, reason in reasons().items():
        reason.code = name.lower().replace("_", "-")


_name_codes()
