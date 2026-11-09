"""Which home a brief or a scout's request belongs to, and which thread that home is now. This
module is the one copy of that rule.

A repo's state directory holds the root home's files, and a directory beside them for each
scoped home. A scope is such a directory with a `plan.md`, the file a home writes when it makes
one, but for the directories every home of the repo shares (`SHARED`): the home skill's
scoped-homes.md reads its scopes by the same rule (`scopes`). A scope is one from the moment it
is made, before its thread starts and writes its `home-id`: jbus queues its rows at once and
tells it of them once that id is there (`thread_of`). `/handoff` keeps the plan of a scope it
closes as `plan-archived.md`, so that scope is no scope, whatever ids it kept.

The root home owns no row. `uncategorized` (`UNCATEGORIZED`) is the scope reserved as the
catch-all: it owns every brief no other scope claims (`catchall`). A brief names its home on a
`Home:` line in its head, before its first `## ` heading. A home writes the scope's name there.
A brief written before homes wrote scope names gives instead a thread id that is in a `home-id`
or on a `Was home:` line. A brief with no such line, or one that names `root`, the root's ids, a
name that is no scope, or a scope that is archived, belongs to the catch-all (`home_of`), whether
or not its directory is made yet. A brief queued now must name its home as `uncategorized` or a
scope's name (`fault`): a brief queued with `Home: root` would show under the root, which T3 Code's
sidebar groups by the line as written.

A home's thread is the first word of its `home-id`, read again on each call. A home that
handed off has no thread until the next home's start writes its own id there. An id equal
to the one on its handoff's `Was home:` line counts as none (`thread_of`). A `Was home:`
line with no id on it counts as no line. Until the catch-all's home runs, what is sent to it
reaches the root's thread, so that no row goes untold before `/home uncategorized` has started.

`homes_dir`, from `jsettings.paths`, is where every repo's state is. `jbus home` asks this
module for the skills, `jbus.leftover` and `jbus.word` ask it for what jbus sends, and `jmerge`
asks it whose a pull request is. No other copy of the rule exists.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from jbriefs import parse
from jsettings.brief import head
from jsettings.paths import homes_dir as homes_dir

WAS = re.compile(r"^Was home:[ \t]*(\S+)", re.M)
ROOT = "root"
UNCATEGORIZED = "uncategorized"
SHARED = frozenset({"tasks", "scouts", "reports", "log"})


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
    """Each scope of the state, by its name, with its `ids`, either of which is empty where there
    is none."""
    found = (plan.parent for plan in sorted(state.glob("*/plan.md")))
    return [(one, *ids(one)) for one in found if one.name not in SHARED]


def catchall(state: Path) -> Path:
    """The directory of the catch-all home, `uncategorized`, made or not."""
    return state / UNCATEGORIZED


def home_of(state: Path, brief: str) -> Path:
    """The directory of the home that a brief belongs to. That is the scope that its `Home:`
    line names, by name or by either of its ids. Where two scopes match, it is the last one
    in name order. For any other brief it is the catch-all's (`catchall`), never `state`. A
    caller that asks of many briefs takes `reader`, which reads the scopes once."""
    return reader(state)(brief)


def reader(state: Path) -> Callable[[str], Path]:
    """`home_of` for many briefs: the root's ids and the scopes of `state` are read once, at the
    first brief whose `Home:` line names something other than `root`, so a home that changes
    after that is not seen by the function this returns. A brief with no `Home:` line, or one
    that names `root`, reads neither: it is the catch-all's."""
    other = catchall(state)
    known: tuple[tuple[str, str], dict[str, Path]] | None = None

    def home(brief: str) -> Path:
        nonlocal known
        name = named(brief)
        if not name or name == ROOT:
            return other
        if known is None:
            homes: dict[str, Path] = {}
            for scope, now, was in scopes(state):
                homes |= {key: scope for key in (scope.name, now, was) if key}
            known = ids(state), homes
        root, homes = known
        return other if name in root else homes.get(name, other)

    return home


def fault(state: Path, brief: str, project: str) -> str:
    """Why a brief may not be queued for its home, or an empty string. Its `Home:` line must
    name `uncategorized` or the name of a scope of `state` (`scopes`): a brief with no line once
    landed in a home without a word, and a thread id or a name that is no scope would too. The
    root owns no row, so a line that names `root` is refused too, though `home_of` reads one
    written before as the catch-all's."""
    name = named(brief)
    known = [scope.name for scope, _, _ in scopes(state) if scope.name != UNCATEGORIZED]
    want = f"name {UNCATEGORIZED} or the row's scope" + (f" ({', '.join(known)})" if known else "")
    if not name:
        return f"no Home: line: {want}"
    if name == ROOT:
        return f"Home: line names {ROOT}, which owns no row: {want}"
    if name not in (UNCATEGORIZED, *known):
        return f"Home: line names {name}, which is no home of {project}: {want}"
    return ""


def stands_in(state: Path) -> bool:
    """Whether the root home stands in for the catch-all (`catchall`): until `/home
    uncategorized` starts it, the catch-all has no thread of its own, and the root's thread hears
    and works its rows."""
    now, was = ids(catchall(state))
    return was == now


def worked_by(state: Path, directory: Path) -> Path:
    """The directory of the home whose thread works the rows of the home `directory`: its own,
    and the root's for the catch-all while the root stands in for it (`stands_in`)."""
    if directory == catchall(state) and stands_in(state):
        return state
    return directory


def works(state: Path, directory: Path) -> frozenset[Path]:
    """The homes whose rows the home of `directory` works: its own, and for the root the
    catch-all's too while it stands in for it (`stands_in`)."""
    if directory == state and stands_in(state):
        return frozenset((state, catchall(state)))
    return frozenset((directory,))


def thread_of(home: Path, slug: str = "") -> str:
    """The one lookup of whom jbus sends to: the thread an owner is now, read again on each call.
    A home's directory, the root's or a scope's, is its home's thread: an empty string when the
    directory has no `home-id`, or when the id there belongs to the home that handed off. A slug is
    the thread on the `Thread:` line of its brief under `tasks/`, or else of its request under
    `scouts/`. It is an empty string where there is none. The catch-all's directory with no
    thread of its own is the root's thread, until its home starts."""
    if not slug:
        if home.name == UNCATEGORIZED and stands_in(home.parent):
            return thread_of(home.parent)
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
