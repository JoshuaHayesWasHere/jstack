"""`jbus needs`: print what waits on the user, for one project with `--project` or for all.

It is the one answer to "what needs me". It reads the list the last pass wrote
(`waiting-on-user.json`) and keeps only what the user has to decide, by the one rule that also
raises a decision and wakes a home with it (`blockers.deciding`): a gate whose `Holds:` line holds
it, a gate with no default or one that names a door, a go gate whose silence starts nothing, a row
whose brief has no go, a pull request `jmerge` holds for the user's word, and a setup only the user
can give. A row a home can clear by itself (a row at `gate`, a leftover its home still has, a hold
a thread works on) is not on it, and neither is a refused go: a refusal is an act of the home's
(`acts.jsonl`), most of them a sha that did not match, and the home tries again by itself.

Each item is one line with what it holds, then the reply that answers it, the same `Reply:` a
decision carries (`blockers.reply`), and, for a gate that holds, the fail-safe to read first. A
project no pass has listed yet says so, since nothing is known of it. `jbus home status` opens with
the same lines for its own project (`jbus.homestatus`).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime

import jbus
from jbus import blockers, passes, questions, verbs, waiting


@dataclass(frozen=True)
class Need:
    """`Need` is one thing only the user can do: the project it is in, what it is and what it
    holds (`said`), the reply that answers it, and the fail-safe of a gate that holds."""

    project: str
    said: str
    reply: str
    fail_safe: str = ""

    def lines(self) -> list[str]:
        safe = [f"  fail-safe: {self.fail_safe}"] if self.fail_safe else []
        answer = f'  answer: say "{self.reply}", or say what to do instead'
        return [f"{self.project} {self.said}", *safe, answer]


class Unknown(Exception):
    """The project's list cannot be read: no pass has written one, or its questions do not
    parse."""


def of(config: jbus.Config, project: jbus.Project, now: datetime) -> list[Need]:
    """Return what waits on the user in one project at `now`, in the list's order. Raise
    `Unknown` where nothing is known."""
    run = passes.Pass(config, project, now)
    listed = waiting.read(run.state)
    if listed is None or run.first:
        raise Unknown(f"{project.name}: no pass has listed what waits there yet")
    try:
        found = blockers.deciding(run, listed)
    except questions.Unparsable:
        raise Unknown(f"{project.name}: {questions.path(run.state)} does not parse") from None
    return [
        Need(project.name, said, blockers.reply(project, one), str(one.get("fail_safe") or ""))
        for one, said in found
    ]


def lines(
    config: jbus.Config, projects: list[jbus.Project], scope: str, now: datetime
) -> list[str]:
    """Return the lines `jbus needs` prints for the projects: a head that counts the items, the
    items, and a line for each project nothing is known of. `scope` names the projects in the
    line that says nothing waits."""
    user, found, unknown = config.user.user, [], []
    for project in projects:
        try:
            found += of(config, project, now)
        except Unknown as why:
            unknown.append(f"not known: {why}")
    if not found and unknown:
        return [*unknown, f"nothing else known waits on {user} in {scope}"]
    if not found:
        return [f"nothing waits on {user} in {scope}"]
    names = sorted({one.project for one in found}, key=[p.name for p in projects].index)
    head = f"waiting on {user}: {len(found)}, in {', '.join(names)}"
    return [head, *(line for one in found for line in one.lines()), *unknown]


def _arguments(parser: argparse.ArgumentParser) -> None:
    """`jbus needs` takes no argument of its own: `jbus --project <name> needs` is one project."""


def _needs(args: argparse.Namespace, config: jbus.Config) -> int:
    if args.project:
        projects = [config.project(args.project)]
        scope = args.project
    else:
        projects = list(config.projects)
        scope = "any project"
    print("\n".join(lines(config, projects, scope, verbs.clock())))
    return 0


VERBS = (
    verbs.Verb(
        "needs",
        "what waits on the user, with what each holds and the reply that answers it",
        _arguments,
        _needs,
    ),
)
