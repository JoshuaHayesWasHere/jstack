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

from jbriefs import below, checked, findings, meets, proved, skills
from jbriefs.findings import CLEANUP, NONE, REVIEW
from jbriefs.stacked import Stacked
from jmerge.rangediff import Verdict
from jsettings import Settings
from jsettings.brief import head_lines

_COMMIT = re.compile(r"[0-9a-f]{40}")
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
    code, so a filled-in reason still says which one it is. `earlier` holds each text the reason
    had before it was reworded: a line `jmerge` wrote in it is still the reason's, so its code
    and step outlive the rewording (tests/reason_wordings.txt keeps every wording)."""

    step: str
    code: str = ""
    earlier: tuple[str, ...] = ()

    def __new__(cls, step: str, text: str, code: str = "", earlier: tuple[str, ...] = ()) -> Reason:
        made = super().__new__(cls, text)
        made.step = step
        made.code = code
        made.earlier = earlier
        return made

    def format(self, *args: object, **kwargs: object) -> Reason:
        return Reason(self.step, super().format(*args, **kwargs), self.code)

    @functools.cached_property
    def pattern(self) -> str:
        """The reason's text as a pattern, each field a value. It is made once for each reason:
        the view reads a step of every line of the logs, and making it on each read held each
        of its answers for seconds."""
        return _pattern(self)

    @functools.cached_property
    def patterns(self) -> tuple[str, ...]:
        """The pattern of the reason's text, then of each of its `earlier` texts."""
        return (self.pattern, *(_pattern(text) for text in self.earlier))

    def fields(self, text: str) -> dict[str, str] | None:
        """The value of each field of the reason in `text`, a reason it made, or None for text
        it did not make."""
        parts = list(string.Formatter().parse(self))
        found = re.fullmatch(
            "".join(
                re.escape(literal) + ("(.+)" if name is not None else "")
                for literal, name, _, _ in parts
            ),
            text,
        )
        names = [name for _, name, _, _ in parts if name is not None]
        return dict(zip(names, found.groups(), strict=True)) if found else None


def _pattern(text: str) -> str:
    return "".join(
        re.escape(literal) + (_VALUE if name is not None else "")
        for literal, name, _, _ in string.Formatter().parse(text)
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
    start of the reason, and a reason has one for its text and one for each `earlier` text.
    `ELSEWHERE` comes first so that the plain text of a reason no `Reason`
    made is on its own step, and a field comes last since it matches the start of any text: a
    refused merge whose error says `the required check has failed` is `BASE_MERGE_REFUSED`'s,
    not `CHECK_FAILED`'s."""
    named = sorted(reasons().values(), key=lambda one: one.pattern.startswith(_VALUE))
    return ELSEWHERE + tuple(
        (one.code, one.step, "^" + pattern) for one in named for pattern in one.patterns
    )


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
USER_JUDGED = Reason("hold", "the user judges it: waits for the user's word")
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
_PROVED_CODE = "says tests only, and it changes {path}, which is no test file, docs or config"
_PROVED_NOT_FORK = (
    "says fork patches, and it changes {path}, which is no fork patch, docs or config"
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
_RUN_THE_BLOCK = (
    "the crew's check block (features/crew/do-the-task.md), which runs `make check-fast "
    "PART=touched`, the lint, the touched tests, the cross-cutting tests and the tests that read "
    "the change, and writes its line (a `PART=guards` line of an earlier head binds too)"
)
_RAN_THE_BLOCK = (
    "the crew's check block (features/crew/do-the-task.md), which runs `make check-fast "
    "PART=touched`, the lint, the touched tests and the repo-guards tests, and writes its line "
    "(a `PART=guards` line of an earlier head binds too)"
)
"""`_RUN_THE_BLOCK` in its words from before #1715, which the lines of the five reasons below
written before it carry."""


def _checked(text: str) -> Reason:
    """A reason on the result step whose `<block>` names the crew's check block: in today's
    words, and in the words from before #1715 as its earlier text."""
    return Reason(
        "result",
        text.replace("<block>", _RUN_THE_BLOCK),
        earlier=(text.replace("<block>", _RAN_THE_BLOCK),),
    )


CHECKED_MISSING = _checked("its brief has no Checked: line: <block>, runs at {head} and writes it")
CHECKED_STALE = _checked(
    "its last Checked: line is of {at}, and its patch changed after it: <block>, runs again at "
    "{head}"
)
CHECKED_CUT = _checked(
    "its last Checked: line ends 124 at {at}, a time limit, which is no pass: <block>, runs "
    "again at {head}"
)
CHECKED_FAILED = _checked(
    "its last Checked: line ends {exit} at {at}, a failure: fix it, and <block>, runs again at "
    "{head}"
)
CHECKED_PART = _checked(
    "its last Checked: line names {command}, not the desk's check: <block>, runs at {head}"
)
NO_VERDICT = Reason("review", "its review has no verdict")
NO_FIXED = Reason("findings", "its findings are not handled: the Result has no Fixed line")
NOT_PUSHED = Reason("findings", "its findings are not handled: nothing was pushed after them")
FIX_UNREVIEWED = Reason("second", "its fix is not reviewed: the scoped review of it is not written")
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
UNPROVEN = Reason(
    "findings",
    "its findings are not handled: {ids} block with no proof tag, so answer each by id, and a "
    "decline of one needs no cited reason",
)
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
CANCELLED_TWICE = Reason("check", "its {check} was cancelled twice")
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
ROW_OVER = Reason(
    "hold",
    "its queue row is {status}, and a row that is over waits for no merge: accept it to merge it",
)
MERGES_AFTER = Reason("check", "merges after {slug} ({open}), not merged yet")
STACKED_ON = Reason(
    "stacked",
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
IN_LINE = Reason(
    "check",
    "it is in line behind #{number}: {base} moved after its check started, and GitHub merges"
    " {base} into the branch of one pull request at a time, the one to merge next",
)
QUEUED_RESTARTED = Reason(
    "check",
    "GitHub queued its {check} run at {head} {minutes} minutes ago and started none: jmerge "
    "closed and reopened it to start a new run",
)
QUEUED_UNOPENED = Reason(
    "check",
    "GitHub queued its {check} run at {head} {minutes} minutes ago and started none: jmerge "
    "closed it to start a new run, and its reopen failed ({why}), which the next run asks again",
)
QUEUED_UNCLOSED = Reason(
    "check",
    "GitHub queued its {check} run at {head} {minutes} minutes ago and started none: jmerge "
    "could not close and reopen it to start a new run ({why})",
)
QUEUED_GAVE_UP = Reason(
    "check",
    "GitHub queued its {check} run at {head} again after jmerge closed and reopened it, and "
    "started none in {minutes} minutes: it gave the head of the line to the next pull request",
)
QUEUED_UNRESTARTED = Reason(
    "check",
    "GitHub queued its {check} run at {head} and started none, and jmerge could not close and "
    "reopen it in {minutes} minutes of tries ({why}): it gave the head of the line to the next "
    "pull request",
)
QUEUED_UNREOPENED = Reason(
    "check",
    "GitHub queued its {check} run at {head} and started none: jmerge closed it to start a new "
    "run, and its reopen failed for {minutes} minutes of tries ({why}), so it asks no more and "
    "the pull request stays closed until a hand reopens it",
)
QUEUED_MINUTES = 30
"""The minutes a required run at the head of the line may sit in GitHub's queue, not started,
before `jmerge` restarts it, and the new run after the restart before it gives up the line. The
queue waits `jbus ci` kept in `ci.jsonl` from 2026-10-28 to 2026-11-04 have a p99 of 1566
seconds for macos, 290 for check and 278 for borders: 30 minutes is above each, and well under
the hour #1028's macos run sat queued on 2026-11-04 while other branches' macos runs ran."""
RESTART_MINUTES = 10
"""The minutes a restart of a queued run (`cli.Repo.unstuck`) has to take: `jmerge` tries a close
or a reopen that failed again on each run for this long from its first try, and once both took,
GitHub has this long to list the new run before the line goes to the next pull request. GitHub
lists the new run within seconds of the reopen, so a run of `jmerge` in the same minute still
sees the old one."""
UNMERGED = Reason("check", "its head could not be merged over today's base ({why})")
MERGED_TREE_FAILS = Reason(
    "rebase",
    "merged over today's {base} at {tip}, it fails {guard}: its crew rebases it onto {base}, "
    "runs the check, and fixes what fails",
)
"""The wait on a pull request whose tree merged over today's base fails the fast guards
(`jmerge.treeguards`): a clash with what merged since its check, which only its crew can fix."""
MERGED_TREE_UNENDED = Reason(
    "check",
    "the guards on its tree merged over today's {base} at {tip} ran past {minutes} minutes and "
    "were stopped",
)
MERGED_TREE_UNBUILT = Reason(
    "check",
    "its tree merged over today's {base} at {tip} could not be built for the guards ({why})",
)
MERGED_TREE_NO_TIME = Reason(
    "check",
    "the guards of this run's other merges took its time: the next run runs them on its tree "
    "merged over {base} at {tip}",
)
MERGED_TREE_NO_SLOT = Reason(
    "check",
    "every full test slot stayed taken for {seconds} s, so the guards did not start on its tree "
    "merged over {base} at {tip}: the next run tries again",
)
RULE_BREAKS = Reason(
    "result",
    "its tests {tests} fail on open pull requests merged with it, {breaks}: carry the fix (an "
    "exemption or a changed rule), or name each on a Breaks: line of its Result, and jbus tells "
    "their crews when it merges",
)
"""The wait on a pull request that adds or tightens a test that another open pull request, merged
with it, fails (`jmerge.preflight`): its crew fixes the rule or names the pull requests it
breaks, so no crew finds the red alone after it lands (#1702 on 2026-11-12)."""
RULE_UNRUN = Reason(
    "check",
    "its tests {tests} have run on {ran} of the {open} open pull requests merged with it: the "
    "next run goes on",
)
"""The wait while the rule preflight has not yet run on every open pull request once: a wait on
the runner that ends by itself (`jmerge.preflight.RUN_SECONDS`)."""
_MAINS_LOST = "{count} of main's lines in {file}"
_OWN_LOST = "{count} of its own in {file}"
_REFUSED = "{file}: {why}"
_RULED = "{id}: {why}"
_CARRIED = "review carried over: range-diff {old} {new} clean"
_PUSH_KEPT = "review kept: {old}..{new} changes only tests, docs or config"
_REBASE_KEPT = "review kept: {old} rebased as {new}, which its checks verify"


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
    queued: tuple[tuple[str, datetime], ...] = ()
    """Each required check GitHub queued at the head and started none of, with when it queued
    its latest run (`queued`)."""


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


def _ended(one: dict, conclusion: str) -> bool:
    return one.get("status") == "COMPLETED" and one.get("conclusion") == conclusion


def _skip_decided(rollup: list[dict], one: dict) -> bool:
    """Whether a skipped job was skipped by its own workflow's choice: every other job of its
    workflow at the head ended passed or skipped, and one at least passed. macos.yml skips its
    `macos` job by an `if:` where its `macos-select` job finds no Mac test the change reaches.
    A skip with no job of its workflow that passed beside it, or one beside a failed job, is no
    pass."""
    workflow, name = one.get("workflowName"), one.get("name")
    if not _ended(one, "SKIPPED") or not workflow:
        return False
    others = [
        run
        for other in dict.fromkeys(
            r.get("name") for r in rollup if r.get("workflowName") == workflow
        )
        if other != name
        for run in latest(rollup, other)
    ]
    return any(_ended(run, "SUCCESS") for run in others) and all(
        _ended(run, "SUCCESS") or _ended(run, "SKIPPED") for run in others
    )


def passed(rollup: list[dict], name: str) -> bool:
    runs = latest(rollup, name)
    return bool(runs) and all(
        one.get("state") == "SUCCESS" or _ended(one, "SUCCESS") or _skip_decided(rollup, one)
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


NOT_STARTED = frozenset({"QUEUED", "PENDING", "WAITING", "REQUESTED"})
"""The states of a check run GitHub has not started (`queued`)."""


def queued(
    rollup: list[dict], required: tuple[str, ...] = REQUIRED
) -> tuple[tuple[str, datetime], ...]:
    """The required checks GitHub queued at the head and started none of, each with when it
    queued its latest run: the check's latest runs, or where it lists none of the check yet the
    jobs of its workflow, all wait, and no job of its workflow is in progress. A queued check
    run's `startedAt` is when GitHub queued it. A check whose workflow runs other jobs is going,
    and a run that started is no queued one, however long it runs."""
    found = []
    for name in required:
        workflow = [one for one in rollup if one.get("workflowName") == name]
        if any(one.get("status") == "IN_PROGRESS" for one in workflow):
            continue
        runs = latest(rollup, name) or [one for one in workflow if one.get("status") != "COMPLETED"]
        if not runs or any(one.get("status") not in NOT_STARTED for one in runs):
            continue
        times = [at for one in runs if (at := _at(one.get("startedAt")))]
        if times:
            found.append((name, max(times)))
    return tuple(found)


@dataclass(frozen=True)
class StuckRun:
    """A required workflow run at a head that GitHub has kept from starting for
    `QUEUED_MINUTES` (`stuck_runs`): `run` is its id, `check` the required check it is the
    workflow of, `since` when GitHub queued what has not started, `attempt` the run's attempt,
    and `ended` whether the run itself ended, so that GitHub would refuse to cancel it."""

    run: int
    check: str
    since: datetime
    attempt: int
    ended: bool


def stuck_runs(
    runs: list[dict], jobs: dict[str, list[dict]], required: tuple[str, ...], now: datetime
) -> tuple[StuckRun, ...]:
    """The required workflow runs at a head, as GitHub's REST `actions/runs` gives them, that
    GitHub queued `QUEUED_MINUTES` ago or more and started nothing of: the latest run of each
    required check's workflow, where it has not started and lists no job that started, since its
    latest attempt began, or where the run lists the job of the check's own name queued, since
    that job was queued. The roll-up lists no check of a run with no jobs, so `queued` cannot see
    the first (#1695, 2026-11-11), and a run that ended can still list its `check` job queued
    (#1691). `jobs` is each run's jobs by its id: a run GitHub gave no jobs for is not judged."""
    found = []
    for name in required:
        mine = [one for one in runs if one.get("name") == name and one.get("id")]
        if not mine:
            continue
        last = max(mine, key=lambda one: int(one["id"]))
        listed = jobs.get(str(last["id"]))
        if listed is None:
            continue
        ended = last.get("status") == "completed"
        if not ended and str(last.get("status", "")).upper() in NOT_STARTED:
            began = any(one.get("status") in ("in_progress", "completed") for one in listed)
            since = None if began else _at(last.get("run_started_at") or last.get("created_at"))
        else:
            waits = [one for one in listed if one.get("name") == name]
            times = [_at(one.get("created_at")) for one in waits if one.get("status") == "queued"]
            since = max((at for at in times if at), default=None)
        if since and (now - since).total_seconds() >= QUEUED_MINUTES * 60:
            attempt = int(last.get("run_attempt") or 1)
            found.append(StuckRun(int(last["id"]), name, since, attempt, ended))
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
        queued=queued(listed.get("statusCheckRollup") or [], required),
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
            found = below.pull(line) if line.startswith("Branch:") else None
            if found and found.url == url:
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
    """One section as the round reads it. `reviewer` tells one reviewer from another: the
    seat (`findings.Section.seat`) where the roster is numbered, so one seat's sections written
    on two instances are one reviewer, and the whole `By:` text where it is not."""

    verdict: str = ""
    head: str = ""
    found: int = 0
    reviewer: str | int = ""
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
    owed: bool = False
    asked: str = ""
    asked_at: int = -1
    found: int = 0
    ended: int = 0
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
    numbered = isinstance(triage.roster, findings.Numbered)
    said.rounds = [
        Round(one.verdict, one.head, one.found, one.by if seat is None else seat, one.scoped)
        for one in triage.roster.counted(triage.sections)
        for seat in [one.seat if numbered else None]
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
        ran = checked.read(line)
        if ran:
            said.checked[ran.head] = ran.exit
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
    that round is owed."""
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
    """Whether the brief's mode needs no ruling from any review after the first: the day's
    warnings row (`cleanup`) gets one review, so it asks for no scoped review of the fix, no
    ruling on a decline or a drop, and no range-diff review after a rebase."""
    return said_of(text).mode == CLEANUP


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
        (findings.UNPROVEN, UNPROVEN),
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
    """The last head's verdict: the worst of its reviewers' last sections, a reviewer's scoped
    pass apart from its full review. A section that did not run counts for nothing beside one
    of the same reviewer's that ran at that head, so a scoped pass that found no room does not
    hide the review that ran, and a section that did not run never replaces the same pass's
    section that ran before it at that head; another reviewer's that did not run still holds
    the round."""
    if not said.rounds:
        return
    heads: dict[str, dict[tuple[str | int, bool], str]] = {}
    for number, one in enumerate(said.rounds):
        head = heads.setdefault(one.head or f"#{number}", {})
        if one.verdict in _RANKS or head.get((one.reviewer, one.scoped)) not in _RANKS:
            head[(one.reviewer, one.scoped)] = one.verdict
    last = heads[said.rounds[-1].head or f"#{len(said.rounds) - 1}"]
    ran = {who for (who, _), verdict in last.items() if verdict in _RANKS}
    said.verdict = _worst(
        [verdict for (who, _), verdict in last.items() if verdict in _RANKS or who not in ran]
    )
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


def short_of(
    text: str, head: str, heard: Collection[meets.Waiver] = (), proven: bool = False
) -> str:
    """What the pull request is short of at `head`, by its brief, or nothing. Every path that
    reads a review ends on the last round's judgement of the brief (`short_on_meets`), with the
    waivers whose words are in `heard`. `proven` says the Result's `Proved:` line holds at
    `head` (`proves`), which owes a fix no scoped review."""
    said = said_of(text)
    unrun = skills.missing(text)
    if unrun:
        return SKILLS_UNRUN.format(names=", ".join(unrun))
    if said.mode == NONE:
        return REVIEW_NONE
    short = _cleanup(said) if said.mode == CLEANUP else _review(said, head, proven)
    return short or short_on_meets(text, heard)


_JUDGED = re.compile(r"\bjudged:\s*(?P<why>[^;]+)", re.I)
_QUOTED = re.compile(r"`[^`]*`")
_THE_USER = re.compile(r"\bthe user\b|\buser's\b|\bthe (?:operator|owner)\b", re.I)


def _plain(text: str) -> str:
    return " ".join(text.split()).lower()


def user_judged(text: str, user: str = "") -> tuple[str, ...]:
    """Each `judged: <why>` clause of the brief's `Proves it:` line that names the user (`the
    user`, `the operator`, `the owner`, or `user`, the name jstack's config gives), as plain words:
    only the user can say it holds, so the pull request waits for their word at the merge
    (`short_on_judged`). A clause runs to the next `;`. A clause quoted in backticks is a mention,
    not a proof, and one that names a reviewer or a measure is no one's word but its own: neither
    is here. A `Done when` line is not read, since a brief about this rule quotes the clause in
    one, as user-judged-holds-merge's first line did."""
    proves = [
        _QUOTED.sub("", line.removeprefix("Proves it:"))
        for line in head_lines(text)
        if line.startswith("Proves it:")
    ]
    named = re.compile(rf"{_THE_USER.pattern}|\b{re.escape(user)}\b", re.I) if user else _THE_USER
    return tuple(
        _plain(clause["why"])
        for line in proves
        for clause in _JUDGED.finditer(line)
        if named.search(clause["why"])
    )


def judged_waivers(text: str, user: str = "") -> tuple[meets.Waiver, ...]:
    """The brief's `Waived: <words>, <thread>/<message>` lines that name a clause of
    `user_judged` by its words, whole or by a start of whole words, each as a `meets.Waiver` whose
    word jbus checks as it checks a waiver of a `Done when` line: the user's own, naming the slug,
    saying it waives and quoting the words."""
    clauses = user_judged(text, user)
    found = []
    for line in text.splitlines():
        if not line.startswith(meets.WAIVED):
            continue
        words, _, ref = line.removeprefix(meets.WAIVED).strip().rpartition(", ")
        said = _plain(words).removeprefix("judged:").strip()
        if said and "/" in ref and any(re.match(rf"{re.escape(said)}(?!\w)", c) for c in clauses):
            found.append(meets.Waiver(0, ref, said))
    return tuple(dict.fromkeys(found))


def short_on_judged(text: str, heard: Collection[meets.Waiver] = (), user: str = "") -> str:
    """`USER_JUDGED` where a clause of `user_judged` stands, or nothing: each is lifted by a
    `Waived:` line in `heard`, whose word jbus checked, that names it (`judged_waivers`). The
    user's own message lifts the hold too, through
    `jmerge --accept --message`, and a home's typed accept does not (`cli.Repo.accept`).
    rh-root-split-skill's brief said the user reviews the diff, and #1828 merged on its checks
    and review alone, 2026-11-12."""
    waived = {one.named for one in heard if one.number == 0}
    for clause in user_judged(text, user):
        if not any(clause.startswith(said) for said in waived):
            return USER_JUDGED
    return ""


_TEST = re.compile(r"(?:test_[^/]*|[^/]*_test)\.py|[^/]+\.(?:test|spec)\.[cm]?[jt]sx?")


def changed_tests(one: PullRequest) -> tuple[str, ...]:
    """The test files the pull request adds or changes: each `test_*.py` or `*_test.py`, and
    each `*.test.*` or `*.spec.*` of JavaScript or TypeScript (`.js`, `.ts`, `.jsx`, `.tsx`, and
    their `.mjs`, `.cjs`, `.mts` and `.cts` kin), it lists and does not delete. A Node repo's
    pull request is held to the same proof as a Python one's."""
    gone = set(one.removed)
    return tuple(
        path for path in one.files if path not in gone and _TEST.fullmatch(path.rsplit("/", 1)[-1])
    )


def changed_code(
    one: PullRequest,
    prose: Callable[[str], bool] = lambda path: False,
    fork_tests: Callable[[str], bool] = lambda path: False,
) -> str:
    """The first file whose change changes code, or nothing where none does: every file is a
    `proved.TEST_FILE`, of an `EXEMPT` kind, a `.py` file whose change `prose` says is to its
    docstrings and comments alone, or a fork file whose change `fork_tests` says is to the fork's
    tests alone (`forktests.fork_tests_alone`). A pull request that changes no code runs its tests
    over the same code at its base as at its head, so a base run that passes is no fault of
    theirs (`short_on_proved`)."""
    return next(
        (
            path
            for path in one.files
            if not proved.TEST_FILE.search(path)
            and not any(proved.of_kind(path, kind, prose) for kind in proved.EXEMPT)
            and not (proved.FORK_FILE.search(path) and fork_tests(path))
        ),
        "",
    )


def short_on_proved(
    text: str,
    one: PullRequest,
    carries: Callable[[str], bool] = lambda at: False,
    prose: Callable[[str], bool] = lambda path: False,
    fork_tests: Callable[[str], bool] = lambda path: False,
) -> str:
    """Why the brief's `Proved:` line does not prove the pull request, or nothing
    (`proved.proved`). A pull request that changes tests needs the line to name each of them,
    with their run over its merge-base's code ending 1, a failure, and at its head ending 0. A
    run that passes at the base, or ends on anything but a failure there (no test collected, a
    time limit), passes vacuously, unless the pull request changes no code (`changed_code`): its
    base then runs the head's own code, the base run has nothing to fail on, and the run at the
    head is the proof, as on a `tests only` line. A fork patch that adds a test of behaviour the
    fork already has is one (#1535, held 76 minutes on a base run that passed). One that changes
    no test needs no line, and where it says `none, <kind>` each file it changes is of a kind it
    names, a `.py` file whose change `prose` says is to its docstrings and comments alone being
    `docs` (`proved.prose_in`). One whose
    every file, a deleted one too, is a `proved.TEST_FILE` or of a `proved.EXEMPT` kind changes
    no code, so its tests pass at its base as well: its `tests only` line needs only the run at
    its head, ending 0, and the same line on a pull request that changes anything else proves
    nothing. A pull request that removes tests is one, with the edit to the doc that named them,
    which the docs lint makes it carry: a removal has no base run that fails. One that adds or
    changes a fork's patch (`proved.FORK_FILE`) needs a line as one that changes tests does,
    since its tests are inside the patch; one that only edits the `PKGBUILD` or deletes a patch
    has no fork test to run, and needs none. Where every file it changes is a fork file or of an
    `EXEMPT` kind, its `fork patches` line names the fork's test files, with the same base and
    head runs; the same line on a pull request that changes any other file, a test of this repo
    too, proves nothing (`proved.outside_fork`). A line of another head holds where the head
    carries that head's patch unchanged (`carries`, the range-diff `jmerge` reads after a rebase
    or a merge of the base): a push that changed the patch, a fix for a review's finding most of
    all, may have changed the tests too."""
    tests = changed_tests(one)
    said = proved.proved(text)
    if said is None:
        gone = set(one.removed)
        fork = [
            path
            for path in one.files
            if path not in gone and proved.FORK_FILE.search(path) and path.endswith(".patch")
        ]
        unproved = (*tests, *fork)
        return PROVED_MISSING.format(tests=", ".join(unproved)) if unproved else ""
    if said.fault:
        return PROVED_UNREAD.format(fault=said.fault)
    if said.kinds:
        if tests:
            return PROVED_NOT_EXEMPT.format(tests=", ".join(tests))
        other = next(
            (
                path
                for path in one.files
                if not any(proved.of_kind(path, kind, prose) for kind in said.kinds)
            ),
            "",
        )
        kinds = " and ".join(said.kinds)
        return PROVED_NOT_KIND.format(kinds=kinds, path=other) if other else ""
    if said.tests_only:
        code = first_code(one.files)
        if code:
            return PROVED_UNREAD.format(fault=_PROVED_CODE.format(path=code))
    if said.fork:
        code = proved.outside_fork(one.files)
        if code:
            return PROVED_UNREAD.format(fault=_PROVED_NOT_FORK.format(path=code))
    unnamed = [path for path in tests if path not in said.tests]
    if unnamed:
        return PROVED_UNNAMED.format(tests=", ".join(unnamed))
    if said.base_exit != 1 and not said.tests_only and changed_code(one, prose, fork_tests):
        return PROVED_BASE_PASSED.format(exit=said.base_exit, base=said.base[:12])
    if said.head_exit != 0:
        return PROVED_HEAD_FAILED.format(exit=said.head_exit, head=said.head[:12])
    if said.head != one.head and not carries(said.head):
        return PROVED_STALE.format(at=said.head[:12], head=one.head[:12])
    return ""


def proves(
    text: str,
    one: PullRequest,
    carries: Callable[[str], bool] = lambda at: False,
    prose: Callable[[str], bool] = lambda path: False,
    fork_tests: Callable[[str], bool] = lambda path: False,
) -> bool:
    """Whether the brief has a `Proved:` line and it holds at the pull request's head
    (`short_on_proved`): a fix whose line holds merges with no scoped review of it."""
    return proved.proved(text) is not None and not short_on_proved(
        text, one, carries, prose, fork_tests
    )


_DESK_CHECK = re.compile(
    r"make check-fast BASE=[0-9a-f]{40} PART=touched"
    r"|make check-fast BASE=[0-9a-f]{40}(?: PYTEST=:)? PART=guards|jgauge check"
)
"""The commands of a `Checked:` line that are a desk's whole check, as the crew's check block runs
them: the lint, the touched tests, the cross-cutting tests and the tests that read the change of
a repo whose check selects its tests (`PART=touched`, each step in the short lane and a step it
stops again in a full slot, so its 124 is no verdict), the guards the block ran before 2026-11-05
(`PYTEST=:` where the selection was none or all, lint only), and another repo's check command
(`jgauge check`). A line of the `PART=rest` alone is none of them; the two-step line reads as its
guards (`jbriefs.checked`)."""


def short_on_checked(
    text: str, head: str, carries: Callable[[str], bool] = lambda at: False
) -> str:
    """Why the brief's last `Checked:` line does not bind the pull request's `head`, or nothing.
    The line binds where it names a desk's whole check (`_DESK_CHECK`) that exited 0 at `head`,
    or at a head whose patch `head` carries unchanged (`carries`, as `short_on_proved` reads
    it). Every exit but 0 holds, a time limit's 124 too: a check cut short reached no verdict.
    A two-step line binds as its guards' step (`jbriefs.checked`): the rest's 124 in the short lane
    holds nothing, and the guards' own exit other than 0 holds as it would alone.
    The crew's push block asks this before the first push, with no head carried, and `jmerge`
    before a merge."""
    found = checked.last(text)
    if found is None:
        return CHECKED_MISSING.format(head=head[:12])
    command, ran, at = found.command, found.exit, found.head
    if at != head and not carries(at):
        return CHECKED_STALE.format(at=at[:12], head=head[:12])
    if ran == "124":
        return CHECKED_CUT.format(at=at[:12], head=head[:12])
    if ran != "0":
        return CHECKED_FAILED.format(exit=ran, at=at[:12], head=head[:12])
    if not _DESK_CHECK.fullmatch(command):
        return CHECKED_PART.format(command=command, head=head[:12])
    return ""


def _review(said: Said, head: str, proven: bool) -> str:
    """What the review of a `review` brief still lacks. One round: a `Scoped review: needed`
    line holds the pull request for a review of a later head only where no `Proved:` line holds
    at `head`, since a fix whose proof runs there merges on that run and its checks."""
    verdict, reviewed, fixed = said.verdict, said.reviewed, said.fixed
    if not said.written:
        return NO_REVIEW
    if verdict not in ("clean", "findings"):
        return NO_VERDICT
    if said.owes and not fixed:
        return NO_FIXED
    if said.owes and fixed == reviewed:
        return NOT_PUSHED
    owed = said.owed and not proven and not _scoped_since(said)
    if owed and (not reviewed or said.asked in ("", reviewed)):
        return FIX_UNREVIEWED
    if said.owes and _COMMIT.fullmatch(fixed) and head != fixed and head == reviewed:
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
    return " and ".join(
        _RULED.format(id=one.id, why=one.ruling.why) for one in named if one.ruling is not None
    )


def unruled(said: Said) -> str:
    """Why the declines keep the pull request waiting on its crew, or nothing: a decline that a
    scoped pass did not uphold and that is on none of `findings.RISKS`. The crew fixes such a
    finding, and where the crew keeps its decline, the home decides. A decline on a risk is
    the user's to decide (`declines`). One round asks no pass to rule on a decline: a scoped
    pass that runs for another reason, the re-judgement a `no` owes or a rebase's, still
    rules."""
    triage = said.triage
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
    if said.mode == CLEANUP:
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
    if said.mode == CLEANUP or fixed == reviewed or not _COMMIT.fullmatch(reviewed):
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
    if said.mode == CLEANUP:
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


def first_code(files: Collection[str]) -> str:
    """The first of `files` that is neither a `proved.TEST_FILE` nor of a `proved.EXEMPT` kind,
    or empty where every one is a test, docs or config and so changes no code. A `tests only`
    `Proved:` line and a push the review covers (`kept_note`) are judged by it alike."""
    return next(
        (
            path
            for path in files
            if not proved.TEST_FILE.search(path)
            and not any(proved.of_kind(path, kind) for kind in proved.EXEMPT)
        ),
        "",
    )


def kept_note(reviewed: str, head: str, verdict: Verdict) -> str:
    """Why the review of `reviewed` covers `head`, whose patch is not the reviewed one, or empty
    where it does not. A rebased head (`Verdict.rebased`) is covered whatever its patch differs
    in: the checks verify a rebase. A head pushed on the reviewed one, over a merge of main or
    not, is covered where its patch differs in tests, docs or config alone (`first_code`). Each
    waits only on its checks and its `Proved:`, `Checked:` and `Dropped on rebase` lines. A head
    whose patches git could not compare, or a push that changes code, gets its scoped review."""
    if verdict.differ is None:
        return ""
    if verdict.rebased:
        return _REBASE_KEPT.format(old=_short(verdict.old), new=_short(verdict.new))
    if first_code(verdict.differ):
        return ""
    return _PUSH_KEPT.format(old=reviewed[:12], new=head[:12])


def short_on_content(verdict: Verdict | None) -> str:
    if verdict is None or verdict.clean:
        return ""
    return CONTENT_CHANGED.format(command=verdict.command)


def short_on_github(one: PullRequest) -> str:
    """What GitHub holds against the pull request, or nothing. GitHub runs no check on a pull
    request that conflicts with its base, so a required check with no run at a conflicting head
    is said as the conflict that keeps it from running (`CONFLICTS`): #1694 and every other open
    statechart pull request read `check has no run` while each was CONFLICTING."""
    if one.waiting and one.waiting[0] in one.unrun:
        unrun = NO_RUN.format(check=one.waiting[0], head=one.head[:12])
        return CONFLICTS if one.mergeable == "CONFLICTING" else unrun
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


STILL_TO_PASS = (NO_RUN, LIVE_RUN, NOT_PASSED)
"""GitHub's waits on a required check that can still pass: no run at the head, a run not ended,
and one that has not passed and has not failed."""


def still_to_pass(one: PullRequest) -> str:
    """The wait `short_on_github` gives where all GitHub holds against the pull request is a
    required check that can still pass (`STILL_TO_PASS`), or nothing. A failed check or a conflict
    is no such wait: the crew's push for it brings a new head and a new range-diff. A rebase that
    changed the content is said beside this wait (`Repo.judged`), with it as the note, so the
    scoped review runs while the check does and not after it."""
    github = short_on_github(one)
    can_pass = {reason.code for reason in STILL_TO_PASS}
    if one.failed or one.mergeable == "CONFLICTING" or code_of(github) not in can_pass:
        return ""
    return github


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
    """The base's tip a pull request was judged over, and whether its files overlap what that
    base changed since its check started: such a one merges on the guards on its tree merged
    over `tip`, and goes through the line where they fail or were stopped (`cli.Repo.over_main`).
    `batch` marks a member of jmerge's batch, which merges once CI's check of the batch passed
    (`jmerge.batch`), and not on its own."""

    tip: str = ""
    overlaps: bool = False
    batch: bool = False


MERGING = Reason("check", "another run of jmerge is merging into its base")
IN_BATCH = Reason(
    "check", "it is in jmerge's batch over {base} at {tip}, whose check decides its merge"
)
"""The wait of a member of jmerge's batch whose check runs (`jmerge.batch`). CI's check of the
batch decides its merge, so it is on the step of a pull request that waits on its own check."""
BATCH_FIRST = Reason(
    "check",
    "jmerge's batch over {base} at {tip} is checked and merges first: a merge before it would "
    "undo that check",
)
"""The wait of a pull request that would merge while a batch is checked: a member that joined
after it was built, one the batch had no room for, and one that would merge alone."""
BATCH_STOPPED = Reason(
    "check",
    "jmerge's batch over {base} at {tip} stopped at #{number}, which did not merge: the next "
    "batch takes it",
)
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
