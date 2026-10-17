"""Which open pull requests are ready to merge: reviewed, fixed and green, with a check that
still covers today's default branch, which of those are still the user's to merge, and which
are merged only under the stricter gate of a guarded path.

This is the one copy of the rules. They are read from what GitHub lists for a pull request
and from the brief whose Result names it; nothing here runs a command.

Every reason `jmerge` writes after `wait:` or `hold:` from here is a named constant of this
module, formatted where it names a value, and a function returns one and never a string of
its own: the steps of the view are worked out from them (`jbus.merge.RULES`), and its tests
name each one. A constant whose name starts with `_` is a piece of a reason or a note of a
`ready` or `merged` line.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

from jbriefs import skills
from jmerge.rangediff import Verdict
from jsettings import Settings

_COMMIT = re.compile(r"[0-9a-f]{40}")
_ENDED = re.compile(r"Finding: (fixed, .|not fixed, .+, because .)")
_REBASE = re.compile(
    r"Rebase: patch (unchanged|changed in (.+)), before ([0-9a-f]{40}), head ([0-9a-f]{40})"
)
_ACK = re.compile(
    r"Dropped on rebase: (.+?), (\d+) of main's, (\d+) of its own, at ([0-9a-f]{12}): (.+)"
)
_UPHELD = "Drops: upheld "
_NOT_UPHELD = "Drops: not upheld "

_CI_FIX = re.compile(r"CI fix: ([0-9a-f]{40}), after the review of ([0-9a-f]{40})")
_HELD = re.compile(r"Rebase hold: at ([0-9a-f]{40}), |Rebase hold lifted: ")

OTHER_HOME = "another home's"
REQUIRED = "check"
MERGE_OFF = "auto-merge is off for this repo"
NO_BRIEF = "no brief has a Result that names it"
DRAFT = "draft"
RULES = "src/jmerge/"
GRAMMAR = "docs/jmerge.md#patterns"
RULES_CHANGED = "jmerge's rules changed in this run"
MAIN_MOVED = "main moved while it was judged"
KEPT = "every line kept"
PASSED = "passed"
FAILED = "failed"
TIMED_OUT = "timed out"
FRESH_QUEUED = "a fresh check is queued"
FRESH_CONFLICT = "it conflicts with today's main"
NO_HEAD = "its review names no head to compare its rebase with"

BASE = "its base is {base}, not {default}"
IN_STACK = "it is in the stack {stack}, which the user lands"
IN_UNNAMED_STACK = "it is in a stack its brief does not name, which the user lands"
REVIEW_NONE = "its brief says Review: none, so it needs the user's word"
NO_REVIEW = "it has no review yet"
SKILLS_UNRUN = "its Result has no artifact under Skills run: for {names}, which its brief names"
NO_VERDICT = "its review has no verdict"
NO_FIXED = "its findings are not handled: the Result has no Fixed line"
NOT_PUSHED = "its findings are not handled: nothing was pushed after them"
SECOND_UNWRITTEN = "its fix changed more than the findings named: the second pass is not written"
FIX_UNREVIEWED = "its fix is not reviewed: the scoped review of it is not written"
UNENDED = "its findings are not handled: {left} of {found} have no Finding line"
FIXED_NO_COMMIT = "its Fixed line names no commit"
REBASE_UNSAID = "its Rebase line does not say what the rebase did to the patch"
REBASE_UNTRUE = "its Rebase line says the patch is unchanged, and the rebase changed it"
CANNOT_CHECK = (
    "its Rebase line cannot be checked: "
    "the patch of {commit} cannot be worked out in the main checkout"
)
DROPPED = "the rebase dropped {lost} with no Dropped on rebase line at {head}"
NOT_UPHELD = "needs {user}, the review did not uphold the drop in {refused}"
UNRULED_DROPS = "needs {user}, the review of {head} did not rule on the drops in {files}"
SCOPED_UNRULED = "the scoped review has not ruled on the drops in {files}"
CONTENT_CHANGED = "the rebase changed the content after its review; scoped review of {command}"
NOT_PASSED = f"{REQUIRED} has not passed"
CONFLICTS = "it conflicts with its base"
UNDECIDED = "GitHub has not decided whether it merges"
TOUCHES = "needs {user}, touches {path}"
RENAMES_UNSAID = "needs {user}, GitHub did not say which paths its renames left"
UNLISTED = "needs {user}, GitHub listed {listed} of the {changed} files it changes"
NO_START = "its check has no start time"
GUARDED_UNENDED = "{left} of its {found} findings have no Finding line"
NOT_SEEN = "its head is not the one its review saw"
MAIN_CHANGED = "{default} changed {paths} after its check started at {since}; it needs {needs}"
FRESH_CHECK = "a fresh check"
FRESH_FAILS = "{command} fails on {head} over today's main {tip}{how}"
REBASE_HELD = "its crew held a third rebase after fixed and green, and its gate asks the user"
ROW_HELD = "its queue row is held: approve it again to let it merge"
MERGES_AFTER = "merges after {slug} ({open}), not merged yet"
QUEUE_UNREADABLE = "its queue cannot be read, so its holds and merge order are not known"

_MAINS_LOST = "{count} of main's lines in {file}"
_OWN_LOST = "{count} of its own in {file}"
_REFUSED = "{file}: {why}"
_MORE = " and {more} more"
_TIMED_OUT = ", timed out"
_CARRIED = "review carried over: range-diff {old} {new} clean"
_FRESH_NOTE = "fresh: {command} {passed} on {head} over {tip}"


@dataclass(frozen=True)
class PullRequest:
    """One open pull request, as `gh pr list --json` gives it."""

    number: int
    url: str
    title: str
    branch: str
    head: str
    base: str
    mergeable: str
    passed: bool
    files: tuple[str, ...]
    renamed: bool
    changed: int
    draft: bool = False
    started: datetime | None = None


def passed(rollup: list[dict]) -> bool:
    """Whether the check named `check` passed, whatever the other checks say.

    A status context has a `context` and a `state`; a check run has a `name`, a `status` and
    a `conclusion`. A check that is missing, skipped, neutral, pending or failed has not
    passed, and nothing stands in for it.
    """
    named = [one for one in rollup if REQUIRED in (one.get("name"), one.get("context"))]
    return bool(named) and all(
        one.get("state") == "SUCCESS"
        or (one.get("status") == "COMPLETED" and one.get("conclusion") == "SUCCESS")
        for one in named
    )


def started(rollup: list[dict]) -> datetime | None:
    """When the earliest run of the check named `check` started, or None where none says.

    A run that never started has the year 1 for its start, which is no time at all.
    """
    times = []
    for one in rollup:
        if REQUIRED not in (one.get("name"), one.get("context")):
            continue
        try:
            at = datetime.fromisoformat(one.get("startedAt") or "")
        except (TypeError, ValueError):
            continue
        if at.tzinfo is not None and at.year > 1:
            times.append(at)
    return min(times, default=None)


def pull_request(listed: dict) -> PullRequest:
    return PullRequest(
        number=listed["number"],
        url=listed["url"],
        title=listed.get("title") or "",
        branch=listed["headRefName"],
        head=listed["headRefOid"],
        base=listed.get("baseRefName") or "",
        mergeable=listed.get("mergeable") or "",
        passed=passed(listed.get("statusCheckRollup") or []),
        files=tuple(one["path"] for one in listed["files"]),
        renamed=any(one.get("changeType") == "RENAMED" for one in listed["files"]),
        changed=listed["changedFiles"],
        draft=bool(listed.get("isDraft")),
        started=started(listed.get("statusCheckRollup") or []),
    )


def _fields(line: str) -> list[str]:
    return line.split()


def _second(line: str) -> str:
    fields = _fields(line)
    return fields[1] if len(fields) > 1 else ""


def brief_of(url: str, tasks: Path) -> Path | None:
    """The first brief with a Result whose `Branch:` line ends on the pull request's url."""
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


def home_of(text: str) -> str:
    """The thread id on a brief's `Home:` line, or nothing for a brief with no such line."""
    for line in text.splitlines():
        if line.startswith("Home:"):
            return "".join(line.removeprefix("Home:").split()[:1])
    return ""


def stack_of(text: str) -> str | None:
    """The name on the `Stack:` line in the brief's head, or None for a brief with no such line.

    The head ends at the first Result: the same words in what a crewmate wrote do not count.
    """
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Stack:"):
            return "".join(line.removeprefix("Stack:").split()[:1])
    return None


def held(one: PullRequest, default: str, stack: str | None, land: str | None) -> str:
    """Why the pull request is not the command's to merge, whatever its review and checks say.

    A pull request based on another branch would be merged into that branch, and nothing of
    it would reach the default one. A stack is landed by the user: `land` is the stack they
    said to land, and it lifts the second wait only.
    """
    if one.base != default:
        return BASE.format(base=one.base, default=default)
    if stack is None or (stack and stack == land):
        return ""
    return IN_STACK.format(stack=stack) if stack else IN_UNNAMED_STACK


def rebase_held(text: str, head: str) -> str:
    """Why a pull request whose crew held a rebase waits, or nothing.

    Past its `Fixed:` line a crew rebases twice for the default branch, and in place of the
    third writes `Rebase hold: at <head>, ...` and parks a gate. The pull request waits at
    that head until a `Rebase hold lifted:` line comes after it; a later head is one the
    crew rebased after all.
    """
    last = ""
    for line in text.splitlines():
        found = _HELD.match(line)
        if found:
            last = found[1] or ""
    return REBASE_HELD if last and last == head else ""


@dataclass
class Round:
    """One `## Review` section of a brief: its verdict, its head and its count of findings."""

    verdict: str = ""
    head: str = ""
    found: int = 0


@dataclass
class Said:
    """What a brief says of its pull request's review, read line by line. `rounds` is each
    `## Review` section in order. `second` and `scoped` say whether any `Second pass:` or
    `Scoped review:` line said one is needed, guarded or not, whatever a later line says."""

    none: bool = False
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
    found: int = 0
    ended: int = 0
    second: bool = False
    scoped: bool = False
    rounds: list[Round] = field(default_factory=list)


def said_of(text: str) -> Said:
    """What the brief says of its review, read line by line: the one reader, which the merge
    goes by and the view shows."""
    said = Said()
    seen = review = listed = False
    for line in text.splitlines():
        if line.startswith("Review:") and not seen:
            seen = True
            said.none = _second(line) == "none"
        if line.startswith("## "):
            review = line == "## Review"
            said.written = said.written or review
            listed = False
            if review:
                said.rounds.append(Round())
        elif review and line.startswith("Findings:"):
            listed = True
        elif line.startswith("Dropped:"):
            listed = False
        elif listed and line.startswith("- ") and line != "- none":
            said.found += 1
            said.rounds[-1].found += 1
        if _ENDED.match(line):
            said.ended += 1
        if review and line.startswith("Verdict:"):
            said.verdict = said.rounds[-1].verdict = _second(line)
            said.ran += said.verdict in ("clean", "findings")
        if review and line.startswith("Head:"):
            said.reviewed = said.rounds[-1].head = _second(line)
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
        if line.startswith("Rebase:"):
            said.rebased = _fields(line)[-1]
        if line.startswith("CI fix:"):
            named = _CI_FIX.fullmatch(line.strip())
            said.pushed, said.saw = (named[1], named[2]) if named else ("", "")
    return said


def _ci_fix(said: Said) -> tuple[str, str]:
    """The head the last `CI fix:` line names and the head its review saw, or nothing twice.

    The line counts only of the review the brief has, and not after a fix: the `Fixed:`
    line names the head then, as before. This is the one reading of it.
    """
    if said.pushed and said.saw == said.reviewed and not _COMMIT.fullmatch(said.fixed):
        return said.pushed, said.saw
    return "", ""


def short_of(text: str, head: str) -> str:
    """The first thing the brief says its pull request is short of, or nothing.

    A skill or principle the brief's `Skills:` line names comes first: its Results owe it an
    artifact under `Skills run:`, and one that is missing, empty or a placeholder is the
    crew's to write before anything else is judged (`jbriefs.skills.missing`).

    A head that moved after the review or the `Fixed:` line is short of nothing here: the
    range-diff says whether the review covers it (`to_range_diff`). Findings a `Fixed:`
    line was written before are still not handled, and with the head off that line they
    show two ways: the head is the one they were written on, or one has no `Finding:` line.

    A fix whose review is owed, the last `Scoped review: needed since <head>` line, is short
    of it until a review of another head is written, and then of a `Finding:` line for each
    finding. A `Second pass: needed since <head>` line, which a brief from before that rule
    has, is read the same way. A line that ends `guarded` is not read here: what holds that
    fix is the proof a guarded path is merged on (`short_of_guarded` and the proof's head).
    """
    said = said_of(text)
    verdict, reviewed, fixed = said.verdict, said.reviewed, said.fixed
    found, ended = said.found, said.ended
    unrun = skills.missing(text)
    if unrun:
        return SKILLS_UNRUN.format(names=", ".join(unrun))
    if said.none:
        return REVIEW_NONE
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
    if said.owed and (not reviewed or said.asked in ("", reviewed)):
        return FIX_UNREVIEWED
    if (said.wider or said.owed) and ended < found:
        return UNENDED.format(left=found - ended, found=found)
    if fixed not in ("", "none") and not _COMMIT.fullmatch(fixed):
        return FIXED_NO_COMMIT
    if verdict == "findings" and _COMMIT.fullmatch(fixed) and head != fixed:
        if head == reviewed:
            return NOT_PUSHED
        if ended < found:
            return UNENDED.format(left=found - ended, found=found)
    return ""


def _named(said: Said, head: str) -> bool:
    """Whether a line of the brief names `head`: the `Fixed:` line where it names a commit,
    else the last review's `Head:`, the last `CI fix:` line or the last `Rebase:` line.

    A head no line names is not refused: it is compared with the commit the review covers
    (`to_range_diff`).
    """
    if _COMMIT.fullmatch(said.fixed):
        return head == said.fixed
    return head in (said.reviewed, _ci_fix(said)[0], said.rebased)


def _covered(said: Said) -> str:
    """The commit the review covers: the `Fixed:` commit, else the head the last review saw.

    A clean review that is not the first was written after the fix, of the fix or of a
    later head, so its head is the one covered and the `Fixed:` line is older than it.
    A `Fixed:` line moved after such a review, for a failed check, is taken for older too:
    a later rebase is then compared from that review's head, and the push no review saw
    waits for a scoped review.
    """
    if _COMMIT.fullmatch(said.fixed) and not (said.verdict == "clean" and said.ran > 1):
        return said.fixed
    return said.reviewed


def under_fix(rebase: Rebase | None, text: str, head: str) -> str:
    """The head the last review saw, where `head` is the `Fixed:` commit and no `Rebase:`
    line tells of it, or nothing. A fix is a push on top of what was reviewed, so the two
    left the default branch at one commit. Where they did not, a rebase came between them,
    and the `Fixed:` line alone does not say a review saw what it did: the two are compared.
    """
    said = said_of(text)
    reviewed = said.reviewed
    if rebase is None and said.fixed == head != reviewed and _COMMIT.fullmatch(reviewed):
        return reviewed if _COMMIT.fullmatch(head) else ""
    return ""


def _seen(text: str) -> set[str]:
    """The head each `## Review` section names."""
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
    """What a Result's `Rebase:` line says a rebase did to the patch, the base-to-head diff."""

    did: str
    files: tuple[str, ...]
    before: str
    head: str


def _told(text: str) -> Rebase | None:
    """The last `Rebase:` line, or None for a brief with none or with one in the older shape.

    With no such line, a `CI fix:` line is read as one: a push for a failed check moved the
    head from the one the review saw, changed the patch, and has no file of a rebase to
    count lines in. Only a line `_ci_fix` reads, so that `to_range_diff` gives no commit
    to compare where this gives no rebase.
    """
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
    """What the brief's `Rebase:` line says of the rebase that ended on `head`, or None.

    A crewmate writes no such line since the review follows the patch, so this reads a
    brief from before. Its line says nothing of a head the brief does not name (`_named`):
    a later rebase wrote none, and that head is compared with the commit the review covers.
    """
    return _told(text) if _named(said_of(text), head) else None


def to_compare(rebase: Rebase | None) -> tuple[str, ...]:
    """The commits whose patch-ids the command works out: those of a claim it can check.

    A line that says the patch changed claims nothing a patch-id checks: what it changed is
    read from the range-diff (`to_range_diff`).
    """
    if rebase is None or rebase.did != "unchanged":
        return ()
    return (rebase.before, rebase.head)


def short_on_rebase(rebase: Rebase | None, patches: list[str | None]) -> str:
    """What the `Rebase:` line leaves the pull request short of, or nothing.

    `patches` are the patch-ids of the commits `to_compare` gave, in that order, each None
    where it could not be worked out.
    """
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
    """The reason a `Rebase:` line that names a commit the main checkout does not have waits."""
    return CANNOT_CHECK.format(commit=commit)


def _changed(diff: str) -> tuple[Counter[str], Counter[str]]:
    """The lines a diff of one file adds and the lines it removes, each with how often.

    A line is its text with the whitespace at its end stripped, and a blank one is no line.
    """
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
    """How many lines a rebase dropped from one file: of the default branch's, and of the
    pull request's own.

    `main` is the diff of the file between where the branch left the default branch before
    the rebase and where it leaves it now, `own` the pull request's diff of it before the
    rebase, and `head` the file as the rebased head has it. A line one side added is still
    there, unless the other side's diff removes that same line: a deletion that was meant.
    Lines are counted, so one that is there once does not stand for two.
    """
    theirs, gone_on_main = _changed(main)
    ours, gone_here = _changed(own)
    there = Counter(line.rstrip() for line in head.splitlines() if line.strip())
    return (theirs - gone_here - there).total(), (ours - gone_on_main - there).total()


@dataclass(frozen=True)
class Drop:
    """One file a rebase took lines out of: how many of the default branch's, and how many
    of the pull request's own."""

    file: str
    mains: int
    own: int


def _lost(lost: tuple[Drop, ...]) -> str:
    """Each file that lost a line and whose it was, as the crew skill's block counts them."""
    mains = [_MAINS_LOST.format(count=one.mains, file=one.file) for one in lost if one.mains]
    own = [_OWN_LOST.format(count=one.own, file=one.file) for one in lost if one.own]
    return " and ".join([*mains, *own])


def acks(text: str, head: str) -> dict[str, tuple[int, int, str]]:
    """The brief's `Dropped on rebase: <file>, <n> of main's, <m> of its own, at <head12>:
    <why>` lines for this head: file -> (n, m, why). A line at another head says nothing
    of this one, and the last line for a file is the one that counts."""
    found = {}
    for line in text.splitlines():
        said = _ACK.fullmatch(line.strip())
        if said and said[4] == head[:12]:
            found[said[1]] = (int(said[2]), int(said[3]), said[5])
    return found


def answered(text: str, head: str) -> tuple[Drop, ...]:
    """The drops the crew answered for at this head, as its `Dropped on rebase:` lines count
    them. They stand for the count once a review saw the head and no `Rebase:` line is
    there to count from: what that review ruled on them still holds."""
    return tuple(Drop(file, said[0], said[1]) for file, said in acks(text, head).items())


def _rulings(text: str, head: str) -> tuple[set[str], dict[str, str]] | None:
    """What the reviews that cover `head` say of the drops: the files upheld, and the
    files not upheld with why. None where no review covers the head.

    A review covers the head when its `Head:` line names it, or names the head the last
    rebase ended on: what `to_range_diff` takes for a review that saw the rebased patch.
    Every such review counts, and a later one that rules on a file again has the last
    word on it: one that says nothing of the drops, a second pass, takes no ruling away.
    """
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
    """Files the review that covers `head` lists on its `Drops: upheld <file>, <file>` line."""
    ruled = _rulings(text, head)
    return ruled[0] if ruled else set()


def unexplained(lost: tuple[Drop, ...], text: str, head: str) -> tuple[Drop, ...]:
    """The drops its crew has not answered for at this head: a file with no `Dropped on
    rebase:` line there, or with one whose counts are not the ones counted."""
    said = acks(text, head)
    return tuple(one for one in lost if said.get(one.file, ())[:2] != (one.mains, one.own))


def drops(lost: tuple[Drop, ...], text: str, head: str, *, user: Settings) -> tuple[str, str]:
    """`wait` or `hold` with why a rebase that dropped lines keeps the pull request from a
    merge, or nothing twice: nothing was lost, or the crew explained each drop at this
    head and a review that covers the head upheld each one.

    A drop with no explanation waits on the crew, and one explained waits on the scoped
    review. A drop the review ruled against is the user's. So is one a review of this head
    said nothing of: a head has its one review, so no ruling is coming.
    """
    lost = tuple(one for one in lost if one.mains or one.own)
    silent = unexplained(lost, text, head)
    if silent:
        return "wait", DROPPED.format(lost=_lost(silent), head=head[:12])
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
    """The commit a review covers, to compare with a head that is not it, or None where
    there is nothing to compare. `rebase` is `rebase_of`'s.

    It is `_covered`'s, the `Fixed:` commit or the head the last review saw, whenever no
    line of the brief names `head` and the last review did not see it: a rebase, or a push
    no review saw. A clean range-diff carries the review over, and one that is not asks for one
    scoped review. It is no commit where the review names none. The crew writes no line
    for it and moves no `Fixed:` line. Where a brief from before has a `Rebase:` line that
    moved the `Fixed:` line to the head of a rebase no review saw, it is the commit before
    that rebase: the last one a review covers.

    After a push for a failed check it is the head the last review saw, where the last
    `CI fix:` line names `head` and that review. After a fix the `Fixed:` line stands for
    the push.

    The rest is how such a `Rebase:` line that names the head is read, as it was then.
    None when a review saw the rebased patch: one written of the head the
    rebase ended on, or of the head the pull request is at. Otherwise it is the head the
    last review saw, whatever the `Rebase:` line says the rebase did: the line is of the
    last rebase alone, and one before it may have changed what the patch says. It is no
    commit where the review names none. After a fix it is the commit before the rebase,
    for a line that says the patch changed: the `Fixed:` line named it then, and the
    rebase moved that line to the new head. A fix pushed after the rebase stands on one
    side alone, and the pull request waits for a scoped review of both.
    """
    said = said_of(text)
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
    """What a `ready` or `merged` line says of a rebase that changed the patch and left its
    content as the review saw it, or nothing."""
    if verdict is None or not verdict.clean:
        return ""
    return _CARRIED.format(old=_short(verdict.old), new=_short(verdict.new))


def short_on_content(verdict: Verdict | None) -> str:
    """What a rebase that changed the content of the patch leaves the pull request short
    of, or nothing: one review of what the range-diff shows, which jbus asks its crew for."""
    if verdict is None or verdict.clean:
        return ""
    return CONTENT_CHANGED.format(command=verdict.command)


def short_on_github(one: PullRequest) -> str:
    """What GitHub says the pull request is short of, or nothing."""
    if not one.passed:
        return NOT_PASSED
    if one.mergeable == "MERGEABLE":
        return ""
    if one.mergeable == "CONFLICTING":
        return CONFLICTS
    return UNDECIDED


def patterns_of(text: str) -> tuple[str, ...]:
    """The patterns of a file of paths (protected, guarded, CI): one per line, `#` for a comment.

    A pattern that cannot be read as the rules of `_protects` read one is refused, with a
    ValueError that names it and `GRAMMAR`: one that is taken and protects nothing is no
    guardrail.
    """
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
    """Whether a pattern protects a path. Each part between two `/` is matched by itself,
    so a `*` never crosses one.

    A pattern that ends in `/` is a directory, and covers everything under it. With a `/`
    before that, or at its start, it is a path from the root of the repo; a bare name is a
    directory at any depth. A pattern that does not end in `/` is a file: a bare name at any
    depth, and with a `/` in it the whole path from the root.
    """
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
    """Why the pull request is the user's to merge and never the command's, or nothing.

    It changes a protected path, or GitHub did not say every path it changes: a path that
    was not listed cannot be said to be unprotected. A rename is a change to both its paths,
    and GitHub lists it under the new one alone: `left` are the paths its renames left, or
    None where they could not be asked for.
    """
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
    """A pull request that met every gate, as it was judged."""

    path: str = ""
    tip: str = ""
    rules: bool = False
    fresh: str = ""


def guarded_path(one: PullRequest, patterns: tuple[str, ...], left: tuple[str, ...] = ()) -> str:
    """The first guarded path the pull request changes, or nothing. A rename changes the
    path it left too."""
    for path in (*one.files, *left):
        if any(_protects(pattern, path) for pattern in patterns):
            return path
    return ""


def changes_the_rules(one: PullRequest, left: tuple[str, ...] = ()) -> bool:
    return bool(guarded_path(one, (RULES,), left))


def short_of_guarded(one: PullRequest, text: str, rebase: Rebase | None, carried: str) -> str:
    """What a pull request that is ready is still short of when it changes a guarded path.

    Its check has a start time, which is what main is compared against. Its review is
    finished: every finding it lists has its `Finding:` line, with or without a second pass.
    And the head is one the review covers: the head it saw, the `Fixed:` commit, the head
    of a rebase the command found to leave the patch as it was, or one the review carried
    over to. `carried` is `rebase_note`'s: a rebase that left the content as it was.
    """
    if one.started is None:
        return NO_START
    said = said_of(text)
    if said.verdict == "findings" and said.ended < said.found:
        return GUARDED_UNENDED.format(left=said.found - said.ended, found=said.found)
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
    """The paths the default branch changed that make a pull request's check stale.

    `main_paths` are the paths the default branch changed since the check started, the
    paths its renames left included. One is stale when the pull request changes it too
    (`pr_files`, and `renamed_from`, the paths its own renames left), or when it matches a
    pattern of `ci_paths`: the check then ran against another CI. A default branch that
    moved only on other paths leaves the check standing.
    """
    ours = {*pr_files, *renamed_from}
    stale = (
        path
        for path in main_paths
        if path in ours or any(_protects(pattern, path) for pattern in ci_paths)
    )
    return tuple(dict.fromkeys(stale))


def modules(path: str) -> tuple[str, ...]:
    """The names a Python file may be imported by: its dotted path and each tail of it, as
    any directory may be an import root (`src/`, or a test directory pytest puts on the
    path, where `tests/test_a.py` imports `test_b`). A package is its `__init__.py`.
    Nothing for any other file. A tail that is also a library's name counts too: it fails
    toward a fresh check."""
    if not path.endswith(".py"):
        return ()
    parts = path[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return ()
    return tuple(".".join(parts[start:]) for start in range(len(parts)))


def imports(path: str, text: str) -> set[str]:
    """Every module a Python file's imports load: each dotted prefix of `import a.b`, and
    for `from a import b` both `a` and `a.b`, a relative one read from the file's own
    package, by its full dotted path alone: a tail of it would make `from .models import x`
    in one directory a caller of `models.py` in every other. Nothing for a file that is not
    Python or does not parse."""
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
    """Whether a file calls on another: imports it, Python's way, or names its path, with
    a `/` in it (a bare root name such as `Makefile` is a word as often as a reference). A
    `conftest.py` is used by every Python file under its directory, as pytest loads it."""
    if other.endswith("conftest.py") and path.endswith(".py"):
        if path.startswith(other[: -len("conftest.py")]):
            return True
    if "/" in other and other in text:
        return True
    return bool(imports(path, text) & set(modules(other)))


def callers_and_dependencies(ours: dict[str, str], theirs: dict[str, str]) -> tuple[str, ...]:
    """The paths of `theirs` that are a caller of the pull request's files or something they
    depend on. `ours` is each file the pull request changes with its text at the head, and
    `theirs` each other one the default branch changed with its text at its tip, empty where
    it is gone. A file of `theirs` counts when it uses one of `ours`, or one of `ours` uses
    it (`uses`). A check that ran before such a change ran the patch against code it no
    longer meets, so it is stale as a file of its own would make it."""
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
    """The reason a pull request with stale paths waits, or nothing where it has none.
    `needs` is what lifts it: a fresh check, or for a guarded path a rebase alone."""
    if not stale:
        return ""
    more = _MORE.format(more=len(stale) - 5) if len(stale) > 5 else ""
    paths = " ".join(stale[:5]) + more
    return MAIN_CHANGED.format(default=default, paths=paths, since=user.clock(since), needs=needs)


def fresh_note(command: str, head: str, tip: str) -> str:
    """What a `ready` or `merged` line says of a local check that stood in for a stale one."""
    return _FRESH_NOTE.format(command=command, passed=PASSED, head=head[:12], tip=tip[:12])


def short_on_fresh(result: str, command: str, head: str, tip: str) -> str:
    """The reason a pull request whose local check did not pass waits, or nothing. jbus
    reads the head from it, and tells the crewmate to rebase."""
    if result == PASSED:
        return ""
    how = _TIMED_OUT if result == TIMED_OUT else ""
    return FRESH_FAILS.format(command=command, head=head[:12], tip=tip[:12], how=how)
