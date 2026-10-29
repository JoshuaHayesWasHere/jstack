from __future__ import annotations

import functools
import re
import string
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from jbriefs import findings, skills
from jbriefs.findings import AFTER, CLEANUP, NONE, REVIEW, TWICE
from jmerge.rangediff import Verdict
from jmerge.stacked import Stacked
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
    """A reason `jmerge` gives for a pull request that does not merge: its text, the step it
    puts the pull request on, and its code. The code is the fixed name a `wait` or `hold` line
    carries beside the text (`lines.waits`), the constant's name in kebab case, so a reader
    tells one reason from another without reading the text. `format` keeps the step and the
    code, so a filled-in reason still says which one it is: `NOT_PASSED` and `CHECK_FAILED`
    read alike and differ only in their code."""

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
    ("no-proof", "proof", r"no proven safety fact"),
    ("patch-changed", "second", r"the rebase changed the patch after"),
    ("needs-rebase", "rebase", r"needs a rebase"),
    ("check-unfinished", "check", r"check has not finished"),
    ("fresh-check", "check", r"fresh check"),
    ("unfetched", "check", r"could not be fetched"),
    ("rules-behind", "check", r"jmerge's own rules"),
    ("head-moved", "findings", r"^its head moved after"),
    ("findings-unended", "findings", r"^\d+ of its \d+ findings have no Finding line"),
)
"""The code, step and pattern of each reason `jmerge` writes as plain text, from outside
`Reason` (its run, its proof and its range-diff), and of the reasons an older `jmerge` wrote,
which a log may still have."""
_GUARDED = re.compile(r"^guarded \(touches [^)]*\), ")


def rules() -> tuple[tuple[str, str, str], ...]:
    """The `(code, step, pattern)` of each reason `jmerge` writes, in the order `code_of` tries
    them: `ELSEWHERE` first, then each `Reason` in the order this module declares it. Each
    pattern matches from the start of the reason. `ELSEWHERE` comes first so that the plain
    text of a reason no `Reason` made is on its own step."""
    return ELSEWHERE + tuple((one.code, one.step, "^" + one.pattern) for one in reasons().values())


def code_of(why: str) -> str:
    """The code of a reason: a `Reason`'s own, and for plain text the code of the first rule of
    `rules` whose pattern matches it, past a `guarded (touches <path>), ` before it, which an
    older `jmerge` wrote. A line from before the codes is read this way too. `UNKNOWN` where no
    rule names it."""
    if isinstance(why, Reason) and why.code:
        return why.code
    reason = _GUARDED.sub("", why)
    return next((code for code, _, pattern in rules() if re.search(pattern, reason)), UNKNOWN)


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
DRAFT = Reason("findings", "draft")
UNREADIED = Reason("findings", "draft, and gh pr ready refused it: {said}")
READIED = Reason("check", "reviewed and fixed, so marked ready, and CI runs its check at {head}")
GRAMMAR = "features/jmerge/docs/jmerge.md#patterns"
MAIN_MOVED = Reason("check", "{base} moved while it was judged")
MERGE_FAILED = Reason("check", "the merge failed")
NO_MESSAGES = Reason("check", "its commit messages could not be read for the squash")
NO_SETTINGS = Reason("check", "the repo's merge settings could not be read")
LANDING_UNALLOWED = Reason("hold", "the repo allows {allowed} only, not a merge commit or a squash")
KEPT = "every line kept"
FRESH_CONFLICT = Reason("rebase", "it conflicts with today's main")
NO_HEAD = Reason("second", "its review names no head to compare its rebase with")

BASE = Reason("hold", "its base is {base}, not {default}")
IN_STACK = Reason("hold", "it is in the stack {stack}, which the user lands")
IN_UNNAMED_STACK = Reason("hold", "it is in a stack its brief does not name, which the user lands")
REVIEW_NONE = Reason("hold", "its brief says Review: none, so it needs the user's word")
READY_ON = (DRAFT, REVIEW_NONE)
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
SCOPED_UNRULED = Reason(
    "second",
    "the scoped review has not ruled on the drops in {files}; scoped review of {command}",
)
CONTENT_CHANGED = Reason(
    "second",
    "the rebase changed the content after its review; scoped review of {command}",
)
NOT_PASSED = Reason("check", "{check} has not passed")
CHECK_FAILED = Reason("check", "{check} has not passed")
NO_RUN = Reason("check", "{check} has no run at {head}")
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
ROW_HELD = Reason("hold", "its queue row is held: approve it again to let it merge")
NO_GO = Reason(
    "hold",
    "its queue row has no go: the user's go, or the bot's, lets it merge (jbus queue approve)",
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
BASE_MOVED_ASKED = Reason(
    "check",
    "GitHub was asked to merge {base} at {tip} into it: {base} moved after its check started",
)
BASE_MOVED_DUE = Reason(
    "check", "{base} moved after its check started: GitHub is to merge {base} at {tip} into it"
)
UNMERGED = Reason("check", "its head could not be merged over today's base ({why})")
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
    )


def unchecked_into(one: PullRequest, integration: tuple[str, ...]) -> PullRequest:
    """`one` with no wait on the pull request's own check where its base is an integration
    branch. check.yml runs that check on a pull request into main alone: work into an
    integration branch is checked on each push to the branch, whose red hold stands for it, and
    at main's gate when the branch lands."""
    if one.base not in integration:
        return one
    return replace(
        one,
        waiting=tuple(name for name in one.waiting if name not in REQUIRED),
        failed=tuple(name for name in one.failed if name not in REQUIRED),
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
    owes: bool = False
    rounds: list[Round] = field(default_factory=list)
    triage: findings.Triage = field(default_factory=findings.Triage)


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
    for at, line in enumerate(text.splitlines()):
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
    said.owes = _owes(said)
    return said


def _owes(said: Said) -> bool:
    """Whether the last round's verdict owes the crew a line: a `Fixed:` line, and a push for
    what it fixed. A last round with a first review in it owes one on `Verdict: findings`. A
    last round of later reviews alone owes one only where it sends the crew a finding, which
    is an error (`findings.route`): its warnings go to the cleanup row and the rest are
    dropped. A cleanup row's one review is read the same way."""
    if said.verdict != "findings":
        return False
    sections = said.triage.sections
    last = {n for n, one in enumerate(sections) if one.head == said.reviewed}
    if said.mode != CLEANUP and not all(sections[n].later for n in last):
        return True
    return any(one.sent and one.lead.section in last for one in said.triage.findings)


def after(text: str) -> bool:
    """Whether the brief says `Review: after`. Such a brief merges once its check passes, and
    its review's findings go to a cleanup row (`jbus cleanup`), so no review holds it."""
    return said_of(text).mode == AFTER


def asks_no_ruling(text: str) -> bool:
    """Whether the brief's mode needs no ruling from any review after the first. A brief in
    `after` mode merges once its check passes, `twice` merges once its second review is
    written, and a cleanup row gets one review. So none of them asks for a scoped review of
    the fix, a ruling on a decline or a drop, or a range-diff review after a rebase."""
    return said_of(text).mode in (AFTER, TWICE, CLEANUP)


def _first_head(said: Said) -> str:
    """The head of a brief's first review. The first review is the first section that ran, so
    a section that wrote `Verdict: not run` and ran again at a later head is still the first."""
    return next((one.head for one in said.triage.sections if one.ran and one.head), "")


def second_review(text: str) -> tuple[str, ...]:
    """The heads of a brief's reviews after the first: the heads a later section ran at
    (`findings.Section.later`). For a `twice` brief they are the heads that the fix pushed.
    `jbus cleanup` files the warnings of such a review as a cleanup row, and of a `twice`
    brief its errors too."""
    ran = (one.head for one in findings.triage(text).sections if one.ran and one.later)
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
    short = unanswered(said)
    if short:
        return short
    if pushed and not second_review(text):
        return TWICE_UNWRITTEN.format(head=said.fixed[:12])
    return ""


def _cleanup(said: Said) -> str:
    """What a cleanup row still lacks. It gets one review, and only that review's errors go
    to the crew, so it waits on a `Fixed:` line, a push and an answer by id only for an
    error. No scoped review follows the fix and no pass rules on a decline."""
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
    if said.fixed != "none" and not _COMMIT.fullmatch(said.fixed):
        return FIXED_NO_COMMIT
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
    if said.mode == CLEANUP:
        return _cleanup(said)
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
    if fixed not in ("", "none") and not _COMMIT.fullmatch(fixed):
        return FIXED_NO_COMMIT
    if said.owes and _COMMIT.fullmatch(fixed) and head != fixed:
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
    if said.mode in (TWICE, CLEANUP):
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
    if said.mode in (TWICE, CLEANUP):
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


def to_range_diff(rebase: Rebase | None, text: str, head: str) -> str | None:
    said = said_of(text)
    if said.mode in (AFTER, TWICE, CLEANUP):
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
    fresh: str = ""
    gate: str = ""


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


def short_on_main(
    stale: tuple[str, ...],
    since: datetime,
    default: str = "main",
    *,
    user: Settings,
) -> str:
    if not stale:
        return ""
    paths = _first_five(stale)
    return MAIN_CHANGED.format(default=default, paths=paths, since=user.clock(since))


def _first_five(paths: tuple[str, ...]) -> str:
    more = _MORE.format(more=len(paths) - 5) if len(paths) > 5 else ""
    return " ".join(paths[:5]) + more


def fresh_command(text: str) -> str:
    return "".join(text.strip().splitlines()[:1]).strip()


def gate_held(why: str) -> bool:
    """Whether a reason is the merge gate's hold, which only a passing gate lifts."""
    return bool(GATE_HELD.fullmatch(why))


def first_line(output: str, code: int) -> str:
    """The gate's first line of output, or its exit code where it printed none."""
    return next((line.strip() for line in output.splitlines() if line.strip()), f"exit {code}")


MERGING = Reason("check", "another run of jmerge is merging into its base")
BROWSER = "browser"
"""The check browser.yml's job reports. It runs on a pull request into main that changes the view,
and is no required check: a head with no run of it waits for none (`browser`)."""
BROWSER_FAILED = "failed"
BROWSER_PENDING = "pending"
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
