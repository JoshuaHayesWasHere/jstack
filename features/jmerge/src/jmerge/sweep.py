from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jbriefs import below, parse
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
    source: str
    branch: str
    thread: str
    short: str
    paused: bool
    pull: str


@dataclass(frozen=True)
class Found:
    default: str
    pull: Literal["MERGED", "OPEN", "CLOSED", ""] = ""
    silent: str = ""
    merged: bool = False
    tree: str = ""
    trees: str = ""
    dirty: bool = False
    stray: tuple[str, ...] = ()
    pid: int | None = 0
    based: str = ""


def _said(lines: list[str], label: str) -> list[str] | None:
    found = [line.split()[1:] for line in lines if line.split()[:1] == [label]]
    return found[-1] if found else None


def _status(lines: list[str], of: str, only: bool) -> str:
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
    source = f"tasks/{slug}.md"
    result = below.last(text, "## Result")
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
    return Record(source, slug, parse.thread_of(text), short, paused, pull)


def of_request(slug: str, text: str) -> Record:
    source = f"scouts/{slug}.md"
    report = below.last(text, "## Report")
    if report is None:
        short = f"not done, {source} has no Report"
    else:
        short = _status(report, "Report", only=False)
        if not short and mirror.page("\n".join(report)):
            short = "its Report has a page, which may wait on the user"
    return Record(source, f"scout-{slug}", parse.thread_of(text), short, False, "")


def kept(record: Record, found: Found) -> str:
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
    if found.pid is None:
        return f"no process list could be read to tell whether a process is running in {found.tree}"
    if found.pid:
        return f"a process is running in {found.tree} (pid {found.pid})"
    return found.based


def past(committed: int, now: float) -> int:
    age = now - committed
    return int(age // 86400) if age > MARKER_DAYS * 86400 else 0
