from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
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
    differ: tuple[str, ...] | None = None
    """The files in which the reviewed patch and the head's patch differ, line for line in
    order, context and all, of a verdict that is not clean: empty where only the commits
    differ, None where git could not compare the patches file by file."""
    rebased: bool = False
    """The head does not descend from the reviewed one, has as many commits of its own and
    changes each file the reviewed patch changes, so whatever it changed is a rebase's and no
    commit was pushed on it. A reviewed range that holds a stacked base's commits names files
    the head's patch does not, and so is never read as a rebase."""


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


_FLAGS = (
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--binary",
    "--no-renames",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)


def _path(header: str) -> str | None:
    """The file a `diff --git a/<path> b/<path>` line names, which `--no-renames` makes the same
    on both sides, or None where git quoted it."""
    both = header.removeprefix("diff --git ")
    path = both[2 : 2 + (len(both) - 5) // 2]
    return path if both == f"a/{path} b/{path}" else None


def _files(diff: str) -> dict[str, list[str]]:
    """Each file's lines of `diff`, its hunks' line numbers left out, by its header."""
    files: dict[str, list[str]] = {}
    lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            lines = files.setdefault(line, [])
        elif not line.startswith(("@@", "index ")):
            lines.append(line)
    return files


def _added_and_removed(lines: list[str]) -> Counter[str]:
    return Counter(line for line in lines if not line.startswith(" "))


@dataclass(frozen=True)
class _Patches:
    before: dict[str, list[str]]
    after: dict[str, list[str]]

    def differ(self, key: Callable[[list[str]], object] = list) -> list[str]:
        both = sorted({*self.before, *self.after})
        return [
            one for one in both if key(self.before.get(one, [])) != key(self.after.get(one, []))
        ]

    def files(self) -> tuple[str, ...] | None:
        """The files whose lines differ in order, context and all, so that a line moved within
        a file counts as a change, or None where git quoted one of their names."""
        paths = [_path(header) for header in self.differ()]
        return None if None in paths else tuple(path for path in paths if path is not None)


def _patches(repo: Path, old: tuple[str, str], new: tuple[str, str]) -> _Patches:
    before = _files(_git(repo, "-c", "core.quotePath=false", "diff", *_FLAGS, *old))
    after = _files(_git(repo, "-c", "core.quotePath=false", "diff", *_FLAGS, *new))
    return _Patches(before, after)


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
        patches = None
        if unpaired or not line:
            patches = _patches(repo, (base_old, reviewed), (base_new, head))
            first = next(iter(patches.differ(_added_and_removed)), "")
            how = "the commits do not pair up" if unpaired else "the range-diff shows no content"
            if not first and unpaired:
                why = f"{how}, and the two diffs add and remove the same lines"
                return Verdict(True, command, why, old, new)
            if not first:
                return Verdict(True, command, "the range-diff changes no content", old, new)
            why = f"{how}, and the two diffs differ in {_named(first)}"
        else:
            why = f"the range-diff changes content: {line.strip()}"
        patches = patches or _patches(repo, (base_old, reviewed), (base_new, head))
        differ = patches.files()
        rebased = (
            differ is not None
            and patches.before.keys() <= patches.after.keys()
            and _rebase(repo, (base_old, reviewed), (base_new, head))
        )
    except _Failed as error:
        return Verdict(False, command, str(error), old, new)
    return Verdict(False, command, why, old, new, differ, rebased)


def _named(header: str) -> str:
    return header.removeprefix("diff --git ")


def _rebase(repo: Path, old: tuple[str, str], new: tuple[str, str]) -> bool:
    """Whether the head is the reviewed commits written again: it does not descend from the
    reviewed head, and it has as many commits of its own, so that no commit was pushed on it."""
    if _git(repo, "merge-base", old[1], new[1]).strip() == old[1]:
        return False
    counts = {
        _git(repo, "rev-list", "--count", "--no-merges", f"{a}..{b}").strip() for a, b in (old, new)
    }
    return len(counts) == 1
