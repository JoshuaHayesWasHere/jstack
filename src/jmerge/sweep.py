"""What a finished thread left that may be removed: its worktree, its branches, the gate's ref.
And what a fresh check that passed left: the marker of its tree, on the origin.

This is the one copy of the rules. They are read from a brief or a scout's request, and from
what the command found out from git and GitHub; nothing here runs a command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jbus import mirror
from jmerge import green

WORKTREE = "the worktree"
LOCAL = "the local branch"
REMOTE = "the remote branch"
GATE = "the gate's ref"

PAUSED = "paused"

MARKERS = green.REF
MARKER_DAYS = 7


@dataclass(frozen=True)
class Record:
    """What a brief or a scout's request says of the branch it names."""

    source: str
    branch: str
    thread: str
    short: str
    paused: bool
    pull: str


@dataclass(frozen=True)
class Found:
    """What git and GitHub say of a record's branch."""

    default: str
    pull: Literal["MERGED", "OPEN", "CLOSED", ""] = ""
    silent: str = ""
    merged: bool = False
    tree: str = ""
    trees: str = ""
    dirty: bool = False
    stray: tuple[str, ...] = ()
    pid: int = 0
    based: str = ""


def _thread(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Thread:"):
            return "".join(line.split()[1:2])
    return ""


def _last(text: str, heading: str) -> list[str] | None:
    """The lines from the last heading that starts so, as the skills' own blocks read them."""
    lines = text.splitlines()
    starts = [at for at, line in enumerate(lines) if line.startswith(heading)]
    return lines[starts[-1] + 1 :] if starts else None


def _said(lines: list[str], label: str) -> list[str] | None:
    found = [line.split()[1:] for line in lines if line.split()[:1] == [label]]
    return found[-1] if found else None


def _status(lines: list[str], of: str, only: bool) -> str:
    """What a Status line is short of. `only` is a Result's rule, as the crew skill reads it:
    the line is `Status: done` and nothing more. A Report may say more after the word."""
    status = _said(lines, "Status:")
    if status is None:
        return f"not done, its {of} has no Status line"
    if status == ["done"] or (status[:1] == ["done"] and not only):
        return ""
    if status[:1] == ["done"]:
        return f"its {of} says more than Status: done"
    word = "blocked" if status[:1] == ["blocked"] else "not done"
    if status and status[0].rstrip(",.:;") == PAUSED:
        word = PAUSED
    return f"{word}, its {of} says Status: {' '.join(status)}"


def of_brief(slug: str, text: str) -> Record:
    """A crewmate is finished when its last Result says `Status: done` and `Left: none`."""
    source = f"tasks/{slug}.md"
    result = _last(text, "## Result")
    pull = ""
    paused = False
    if result is None:
        short = f"not done, {source} has no Result"
    else:
        branch = _said(result, "Branch:")
        short = _status(result, "Result", only=True)
        paused = short.startswith(f"{PAUSED}, ")
        if not short and _said(result, "Left:") != ["none"]:
            short = "Left, its Result does not say Left: none"
        if not short and branch is None:
            short = "its Result has no Branch line"
        if branch and branch[-1].startswith("http"):
            pull = branch[-1]
    return Record(source, slug, _thread(text), short, paused, pull)


def of_request(slug: str, text: str) -> Record:
    """A scout is finished when its last Report says `Status: done` and names no page.

    `Page: none` names none, and neither does `Page: none, <why>`, which a scout writes when it
    could build none: `jbus.mirror.page` reads it, as the scout skill's own block does.
    A page may still wait on the user, and the scout goes on in its worktree when they answer.
    Whether its session has ended cannot be told from here, so a Report with a page is kept.
    """
    source = f"scouts/{slug}.md"
    report = _last(text, "## Report")
    if report is None:
        short = f"not done, {source} has no Report"
    else:
        short = _status(report, "Report", only=False)
        if not short and mirror.page("\n".join(report)):
            short = "its Report has a page, which may wait on the user"
    return Record(source, f"scout-{slug}", _thread(text), short, False, "")


def kept(record: Record, found: Found) -> str:
    """The first reason what the record's thread left is kept, or nothing: it may be removed."""
    if record.short:
        return record.short
    if found.pull == "OPEN":
        return "its pull request is open"
    if found.pull == "CLOSED":
        return "its pull request closed unmerged"
    if record.pull and found.pull != "MERGED":
        return f"could not ask GitHub about its pull request{found.silent}"
    if found.trees:
        return f"its worktree {found.tree} is not under {found.trees}"
    if found.dirty:
        return f"dirty, {found.tree} has uncommitted work"
    if found.stray:
        ref = found.stray[0]
        where = f"origin's {found.default}"
        if found.merged:
            where += " or in its merged pull request"
        return f"{'unpushed, ' if ref == LOCAL else ''}{ref} has a commit that is not in {where}"
    if found.pid:
        return f"a process is running in {found.tree} (pid {found.pid})"
    return found.based


def marker(tree: str) -> str:
    """The ref that says this tree passed the repo's check: at the commit that passed, pushed
    by `jmerge` after its fresh check, and read by the check workflow, which then skips the
    suite on that tree."""
    return f"{MARKERS}{tree}"


def past(committed: int, now: float) -> int:
    """The whole days since a marker's commit was made, where it is older than a marker is
    kept, and otherwise 0. They are the days a run's own marker, its artifact, is kept:
    main is long past a tree of that age."""
    age = now - committed
    return int(age // 86400) if age > MARKER_DAYS * 86400 else 0
