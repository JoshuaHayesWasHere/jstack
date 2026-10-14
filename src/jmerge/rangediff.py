"""Whether a rebase changed the content of a reviewed patch, as `git range-diff` shows it.

A review is of a head. A rebase gives the branch another head, and the review still covers
it when the commits say the same thing over another base: the lines they add and remove are
the ones the review saw, and only the context around them or the place of a hunk moved. A
line that is added or removed on one side alone is content no review saw.

`verdict` is the one answer. It fails closed: a commit that is not here, a git that fails
or takes too long, or an output that cannot be read is a content change.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_COMMIT = re.compile(r"[0-9a-f]{40}")
_PAIR = re.compile(r" {0,3}(?:-|\d+): +\S+ ([=!<>]) +(?:-|\d+): +\S+( .*)?")
_PART = re.compile(r" ## (.+) ##")
_AUTHOR = "Author: "
INDENT = "    "
TIMEOUT = 60


@dataclass(frozen=True)
class Verdict:
    """What a rebase did to the content of a reviewed patch."""

    clean: bool
    command: str
    why: str
    old: str = ""
    new: str = ""


class _Failed(Exception):
    """Git could not say. Its text is the reason."""


def _git(repo: Path, *args: str) -> str:
    try:
        ran = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise _Failed(f"git {args[0]} took more than {TIMEOUT} seconds") from None
    except (OSError, UnicodeDecodeError) as error:
        raise _Failed(f"git {args[0]} could not be run ({error})") from None
    if ran.returncode:
        lines = (ran.stderr or ran.stdout).strip().splitlines()
        fatal = [line for line in lines if line.startswith(("fatal: ", "error: "))]
        said = (fatal or lines or [f"exit {ran.returncode}"])[0 if fatal else -1].strip()
        raise _Failed(f"git {args[0]} failed ({said})")
    return ran.stdout


def _have(repo: Path, commit: str) -> None:
    try:
        _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
        return
    except _Failed:
        pass
    try:
        _git(repo, "fetch", "-q", "origin", commit)
        _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    except _Failed as error:
        raise _Failed(
            f"the commit {commit} is not here and could not be fetched: {error}"
        ) from None


def content_change(said: str) -> tuple[str, bool]:
    """The first line of a range-diff that changes the content of the patch, or nothing,
    and whether a commit stands on one side alone (`<` or `>`): squashed, split, added or
    dropped, which a pair by pair reading cannot judge.

    Under a pair marked `!` each line is the diff of two diffs: after the indent, one sign
    for the side that has the line, then the line of that side's diff. A line both sides
    have is no change. Of the others, four kinds are where the patch sits or who wrote it,
    not what it says, and each is known by how it starts: a context line or a line of the
    commit message (a space), a hunk header, an empty line, and the author. Every other
    line is content. No part of a commit is passed over by its name: a file may be called
    what git calls the metadata.
    """
    first = ""
    unpaired = False
    for line in said.splitlines():
        if not line.startswith(INDENT):
            pair = _PAIR.fullmatch(line)
            unpaired = unpaired or bool(pair and pair[1] in "<>")
            if not pair:
                first = first or line
            continue
        outer, inner = line[4:5], line[5:]
        if outer in " @":
            continue
        moved = inner[:1] in ("", " ") or inner.startswith(("@@", _AUTHOR))
        if outer not in "+-" or not moved or _PART.fullmatch(inner):
            first = first or line
    return first, unpaired


def _changes(diff: str) -> dict[str, Counter[str]]:
    """What a diff adds and removes, by file: every line of a file's part but its context,
    its hunk headers and its `index` line, each with how often it is there."""
    files: dict[str, Counter[str]] = {}
    lines: Counter[str] = Counter()
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            lines = files.setdefault(line, Counter())
        elif not line.startswith((" ", "@@", "index ")):
            lines[line] += 1
    return files


def _same_changes(repo: Path, old: tuple[str, str], new: tuple[str, str]) -> str:
    flags = ("--no-color", "--no-ext-diff", "--no-textconv", "--binary", "--no-renames")
    before = _changes(_git(repo, "diff", *flags, *old))
    after = _changes(_git(repo, "diff", *flags, *new))
    for file in sorted({*before, *after}):
        if before.get(file) != after.get(file):
            return file.removeprefix("diff --git ")
    return ""


def verdict(repo: Path, reviewed: str, head: str, default: str) -> Verdict:
    """Whether the review of `reviewed` carries over to `head`, a rebase of it.

    Each side is the commits from where it left the origin's default branch, so the origin
    is as fresh as the caller fetched it.
    """
    command = f"git range-diff --no-color origin/{default}..{reviewed} origin/{default}..{head}"
    if not (_COMMIT.fullmatch(reviewed) and _COMMIT.fullmatch(head)):
        return Verdict(False, command, "the reviewed head and the head are not both full commits")
    old = new = ""
    try:
        for commit in (reviewed, head):
            _have(repo, commit)
        base_old = _git(repo, "merge-base", reviewed, f"origin/{default}").strip()
        base_new = _git(repo, "merge-base", head, f"origin/{default}").strip()
        old, new = f"{base_old}..{reviewed}", f"{base_new}..{head}"
        command = f"git range-diff --no-color {old} {new}"
        line, unpaired = content_change(_git(repo, "range-diff", "--no-color", old, new))
        if unpaired or not line:
            file = _same_changes(repo, (base_old, reviewed), (base_new, head))
            how = "the commits do not pair up" if unpaired else "the range-diff shows no content"
            if file:
                why = f"{how}, and the two diffs differ in {file}"
                return Verdict(False, command, why, old, new)
            if unpaired:
                why = f"{how}, and the two diffs add and remove the same lines"
                return Verdict(True, command, why, old, new)
    except _Failed as error:
        return Verdict(False, command, str(error), old, new)
    if line:
        return Verdict(False, command, f"the range-diff changes content: {line.strip()}", old, new)
    return Verdict(True, command, "the range-diff changes no content", old, new)
