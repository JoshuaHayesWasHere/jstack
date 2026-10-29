from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from jsettings import proc

_COMMIT = re.compile(r"[0-9a-f]{40}")
_PAIR = re.compile(r" {0,3}(?:-|\d+): +\S+ ([=!<>]) +(?:-|\d+): +\S+( .*)?")
_PART = re.compile(r" ## (.+) ##")
_AUTHOR = "Author: "
INDENT = "    "
TIMEOUT = 60


@dataclass(frozen=True)
class Verdict:
    clean: bool
    command: str
    why: str
    old: str = ""
    new: str = ""


class _Failed(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    try:
        ran = proc.git(repo, *args, timeout=TIMEOUT)
    except UnicodeDecodeError as error:
        raise _Failed(f"git {args[0]} could not be run ({error})") from None
    if isinstance(ran, proc.TimedOut):
        raise _Failed(f"git {args[0]} took more than {TIMEOUT} seconds")
    if isinstance(ran, proc.Unrun):
        raise _Failed(f"git {args[0]} could not be run ({ran.stderr})")
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


def _past_held(repo: Path, base_old: str, reviewed: str, base_new: str) -> str:
    """Where the reviewed range starts once it leaves out the commits the new base holds: a
    commit of main's that sat in the old range, as a squash merge of the link under a stacked
    one does, is in neither patch and pairs with nothing. `base_old` where git cannot say."""
    try:
        forks = _git(repo, "merge-base", "--all", reviewed, base_new).split()
        if len(forks) != 1 or forks[0] == base_old:
            return base_old
        _git(repo, "merge-base", "--is-ancestor", base_old, forks[0])
    except _Failed:
        return base_old
    return forks[0]


def verdict(repo: Path, reviewed: str, head: str, default: str, since: str = "") -> Verdict:
    """Whether `head` carries `reviewed`'s patch. Each head's commits are counted from its fork
    from `default`, the reviewed one's from `since` where the caller knows better."""
    command = f"git range-diff --no-color origin/{default}..{reviewed} origin/{default}..{head}"
    if not (_COMMIT.fullmatch(reviewed) and _COMMIT.fullmatch(head)):
        return Verdict(False, command, "the reviewed head and the head are not both full commits")
    old = new = ""
    try:
        for commit in (reviewed, head):
            _have(repo, commit)
        base_old = since or _git(repo, "merge-base", reviewed, f"origin/{default}").strip()
        base_new = _git(repo, "merge-base", head, f"origin/{default}").strip()
        base_old = _past_held(repo, base_old, reviewed, base_new)
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
