"""Which home of a project each task, thread and need belongs to, and the project's homes in
the order the page groups them.

A home is the one `jbriefs.home_of` gives a brief or a scout's request: the scope that its
`Home:` line names, or the root. The view asks jbriefs and keeps no rule of its own. A home is
written as its scope's name, and the root as an empty string, as a gate of the root's
`gates.md` has it. A brief whose `Home:` line names something that is no scope now, such as a
scope that has retired, belongs to the root, and `retired` keeps the name the line gives, so
that its row can say so. A brief that names one of the root's own ids is the root's and names
no retired scope.

A slug's brief is its file in the home's `tasks/`, then the one jbus keeps in the state
directory's `briefs/`, the order `state._whole` reads them in. A scout's is its request in the
home's `scouts/`. A home's own thread is the home whose `home-id`, or whose handoff's
`Was home:` line, has its id. A thread that is none of these has no home.

`group` gives the project's homes: the root first, then each scope in name order, each with
the open tasks and the needs that are its own, its health and the day its scope was made.

A home's health is the `health` of its own thread, the home thread the last pass listed for
it (`state._home_work`), and of the one that is out where it listed two, as a handoff leaves
them. Where the health is `quiet` or `hung`, `since` is the time that thread last wrote. A home
no listed thread is has `none`, since a repo may run with no home, and where the pass left no
list of threads every home has `unknown`.

A scope is made by the root home's block, which writes its `plan.md` with a first line and
then `Goal (<day>, ...)`. That day is `started`. The root, a plan with no such line before its
first entry, and a scope with no plan have none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from jbriefs import home as jbriefs

ROOT = ""
GROUP = {
    "name": None,
    "open": None,
    "waits": None,
    "health": None,
    "since": None,
    "started": None,
}
SINCE = ("quiet", "hung")
_GOAL = re.compile(r"^Goal \((\d{4}-\d\d-\d\d)\b", re.M)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


@dataclass(frozen=True)
class Owner:
    """The home a brief belongs to, `name`, and the name its `Home:` line gives where that
    names no scope now, `retired`."""

    name: str = ROOT
    retired: str = ""

    def said(self) -> dict[str, str]:
        """The two keys a task or a thread has of its home."""
        return {"home": self.name, "retired": self.retired}


@dataclass(frozen=True)
class Homes:
    """The homes of one project: `home` is its home directory, the root's, and `state` its
    state directory."""

    home: Path
    state: Path

    @cached_property
    def scopes(self) -> list[tuple[Path, str, str]]:
        return jbriefs.scopes(self.home)

    def owner(self, brief: str) -> Owner:
        """The home of a brief or a request, by its text."""
        found = jbriefs.home_of(self.home, brief)
        if found != self.home:
            return Owner(found.name)
        named = jbriefs.named(brief)
        return Owner(ROOT, "" if named in jbriefs.ids(self.home) else named)

    def of_slug(self, slug: str, kind: str = "tasks") -> Owner | None:
        """The home of the slug's brief, or of its request for `scouts`, or None where it has
        no such file."""
        if not slug or "/" in slug:
            return None
        places = [self.home / kind / f"{slug}.md"]
        if kind == "tasks":
            places.append(self.state / "briefs" / f"{slug}.md")
        for place in places:
            text = _read(place)
            if text is not None:
                return self.owner(text)
        return None

    def of_task(self, slug: str) -> Owner:
        """The home of a task: its brief's, or the root where it has no brief."""
        return self.of_slug(slug) or Owner()

    def of_thread(self, thread: dict[str, Any], given: str) -> Owner | None:
        """The home of a thread the last pass listed, with `given` its id: a home's own, the
        one of the task of a crew's or a reviewer's slug, or the one of a scout's request.
        None for any other thread."""
        role, slug = thread["role"], thread["slug"]
        if role == "home":
            if given and given in jbriefs.ids(self.home):
                return Owner()
            for scope, now, was in self.scopes:
                if given and given in (now, was):
                    return Owner(scope.name)
            return None
        if role in ("crew", "reviewer") and slug:
            return self.of_task(slug)
        return self.of_slug(slug, "scouts") if role == "scout" else None

    def of_gate(self, scope: str) -> str:
        """The home of a gate of a `gates.md`, by the name of the directory it is in: that
        scope while it is one, else the root."""
        return scope if scope in {one.name for one, _, _ in self.scopes} else ROOT

    def started(self, scope: Path) -> str | None:
        """The day the scope was made: the `Goal (<day>` line of its plan, before the plan's
        first entry."""
        plan = _read(scope / "plan.md")
        found = _GOAL.search(plan.split("\n## ", 1)[0]) if plan else None
        return found[1] if found else None

    def group(
        self,
        tasks: list[dict[str, Any]],
        needs: list[dict[str, Any]],
        threads: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        """The project's homes, the root first and then each scope by name, each with how many
        open tasks and needs are its own, its health from `threads`, the threads the last pass
        listed with each one's home, and the day its scope was made."""
        own = [one for one in threads or [] if one["role"] == "home"]
        found = []
        for name, scope in ((ROOT, None), *((one.name, one) for one, _, _ in self.scopes)):
            mine = sorted(
                (one for one in own if one["home"] == name),
                key=lambda one: (one["out"], one["updated"] or ""),
            )
            thread = mine[-1] if mine else None
            health = "unknown" if threads is None else thread["health"] if thread else "none"
            found.append(
                {
                    "name": name,
                    "open": sum(1 for task in tasks if task["home"] == name),
                    "waits": sum(1 for need in needs if need["home"] == name),
                    "health": health,
                    "since": thread["updated"] if thread and health in SINCE else None,
                    "started": self.started(scope) if scope else None,
                }
            )
        return found
