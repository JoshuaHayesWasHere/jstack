"""Whose a brief or a scout's request is, and which thread its home is now. This module is the
one rule.

A repo's state directory holds the root home's files, and a directory beside them for each
scoped home. A scope is such a directory whose `home-id` holds an id or whose `handoff.md`
has a `Was home:` line. A brief names its home on a `Home:` line in its head, before its
first `## ` heading. A home writes the scope's name there. A brief from before homes wrote
scope names gives a thread id that is in a `home-id` or on a `Was home:` line. A brief with
no such line, or one that names the root's ids or no scope, belongs to the root
(`home_of`).

A home's thread is the first word of its `home-id`, read again on each call. A home that
handed off has no thread until the next home's start writes its own id there. An id equal
to the one on its handoff's `Was home:` line counts as none (`thread_of`). A `Was home:`
line with no id on it counts as no line.

`jbus home` asks this module for the skills, `jbus.leftover` and `jbus.word` ask it for
what jbus sends, and `jmerge` asks it whose a pull request is. No other copy of the rule
exists.
"""

from __future__ import annotations

import re
from pathlib import Path

WAS = re.compile(r"^Was home:[ \t]*(\S+)", re.M)


def _read(file: Path) -> str:
    try:
        return file.read_text(errors="replace")
    except OSError:
        return ""


def ids(directory: Path) -> tuple[str, str]:
    """The id in the directory's `home-id`, its first word, and the id on the `Was home:` line
    of its `handoff.md`. Either is empty where there is none."""
    was = WAS.search(_read(directory / "handoff.md"))
    return (_read(directory / "home-id").split()[:1] or [""])[0], was[1] if was else ""


def named(brief: str) -> str:
    """The first word of the brief's first `Home:` line in its head, or nothing."""
    for line in brief.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Home:"):
            return "".join(line.removeprefix("Home:").split()[:1])
    return ""


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
    if not name or name in ids(state):
        return state
    for scope, now, was in reversed(scopes(state)):
        if name in (scope.name, now, was):
            return scope
    return state


def thread_of(directory: Path) -> str:
    """The thread of the home whose directory this is now, or nothing when the directory has no
    `home-id` or the id there belongs to the home that handed off."""
    now, was = ids(directory)
    return "" if was == now else now
