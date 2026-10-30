"""Which home a brief or a scout's request belongs to, and which thread that home is now. This
module is the one copy of that rule.

A repo's state directory holds the root home's files, and a directory beside them for each
scoped home. A scope is such a directory whose `home-id` holds an id or whose `handoff.md` has a
`Was home:` line. A brief names its home on a `Home:` line in its head, before its first `## `
heading. A home writes the scope's name there. A brief written before homes wrote scope names
gives instead a thread id that is in a `home-id` or on a `Was home:` line. A brief with no such
line, or one that names `root`, the root's ids or no scope, belongs to the root (`home_of`).
A brief queued now must name its home as `root` or a scope's name (`fault`).

A home's thread is the first word of its `home-id`, read again on each call. A home that
handed off has no thread until the next home's start writes its own id there. An id equal
to the one on its handoff's `Was home:` line counts as none (`thread_of`). A `Was home:`
line with no id on it counts as no line.

`homes_dir`, from `jsettings.paths`, is where every repo's state is. `jbus home` asks this
module for the skills, `jbus.leftover` and `jbus.word` ask it for what jbus sends, and `jmerge`
asks it whose a pull request is. No other copy of the rule exists.
"""

from __future__ import annotations

import re
from pathlib import Path

from jbriefs import parse
from jsettings.brief import head
from jsettings.paths import homes_dir as homes_dir

WAS = re.compile(r"^Was home:[ \t]*(\S+)", re.M)
ROOT = "root"


def _read(file: Path) -> str:
    try:
        return file.read_text(errors="replace")
    except OSError:
        return ""


def ids(directory: Path) -> tuple[str, str]:
    """Two ids: the first word of the directory's `home-id`, and the id on the `Was home:` line
    of its `handoff.md`. Either is empty where there is none."""
    was = WAS.search(_read(directory / "handoff.md"))
    return (_read(directory / "home-id").split()[:1] or [""])[0], was[1] if was else ""


def named(brief: str) -> str:
    """The first word of the brief's first `Home:` line in its head, or an empty string when the
    head has no such line."""
    return "".join((head(brief, "Home:") or "").split()[:1])


def scopes(state: Path) -> list[tuple[Path, str, str]]:
    """Each scope of the state, by its name, with its `ids`."""
    found = []
    for one in sorted(path for path in state.glob("*") if path.is_dir()):
        now, was = ids(one)
        if now or was:
            found.append((one, now, was))
    return found


def home_of(state: Path, brief: str) -> Path:
    """The directory of the home that a brief belongs to. That is the scope that its `Home:`
    line names, by name or by either of its ids. Where two scopes match, it is the last one
    in name order. For any other brief it is `state`."""
    name = named(brief)
    if not name or name == ROOT or name in ids(state):
        return state
    for scope, now, was in reversed(scopes(state)):
        if name in (scope.name, now, was):
            return scope
    return state


def fault(state: Path, brief: str, project: str) -> str:
    """Why a brief may not be queued for its home, or an empty string. Its `Home:` line must
    name `root` or the name of a scope of `state` (`scopes`): a brief with no line once landed
    in the root without a word, and a thread id or a name that is no scope would too."""
    name = named(brief)
    names = ", ".join(scope.name for scope, _, _ in scopes(state))
    want = f"name {ROOT} or the row's scope" + (f" ({names})" if names else "")
    if not name:
        return f"no Home: line: {want}"
    if name != ROOT and name not in names.split(", "):
        return f"Home: line names {name}, which is no home of {project}: {want}"
    return ""


def thread_of(home: Path, slug: str = "") -> str:
    """The one lookup of whom jbus sends to: the thread an owner is now, read again on each call.
    A home's directory, the root's or a scope's, is its home's thread: an empty string when the
    directory has no `home-id`, or when the id there belongs to the home that handed off. A slug is
    the thread on the `Thread:` line of its brief under `tasks/`, or else of its request under
    `scouts/`. It is an empty string where there is none."""
    if not slug:
        now, was = ids(home)
        return "" if was == now else now
    for kind in ("tasks", "scouts"):
        try:
            text = (home / kind / f"{slug}.md").read_text(errors="replace")
        except OSError:
            text = ""
        if found := parse.thread_of(text):
            return found
    return ""
