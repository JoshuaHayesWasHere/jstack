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

`--home <directory>` keeps one home's items of its project: a scope's directory keeps that
scope's, and the root home's keeps its own and every scope's. An item is a home's by the slug it
is about, by the rule `jbus home status --home` reads questions by: a home's own slug (`home`,
`home-<scope>`), else the home of the slug's brief or request (`jbriefs.home.home_of`), else the
root's. A pull request `jmerge` holds is about the row whose pull request it is.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jbus
from jbriefs import home as homes
from jbus import blockers, passes, questions, queue, verbs, waiting


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


def _slug(run: passes.Pass, one: waiting.Item) -> str:
    """The slug an item is about: a scope's own for a gate of that scope's `gates.md` that its
    home asked as `home`, else its own, or for a pull request `jmerge` holds, its row's."""
    if one["kind"] == "gate" and one.get("home") and one.get("slug") in ("", "home"):
        return f"home-{one['home']}"
    if one["kind"] == "hold" and not one.get("slug"):
        try:
            rows = queue.load(run.state)
        except queue.Unparsable:
            return ""
        pr = f"#{one.get('number')}"
        return next((row["slug"] for row in rows if row.get("pr") == pr), "")
    return str(one.get("slug") or "")


def home_of(run: passes.Pass, root: Path, slug: str) -> Path:
    """The directory of the home a slug is: a scope's for `home-<scope>`, else the home of its
    brief or request, in the home's files or as the queue stored it, else the root's, which
    `home` and a slug of no brief are."""
    if slug.startswith("home-") and (root / slug[5:]).is_dir():
        return root / slug[5:]
    for kind in ("tasks", "scouts"):
        file = root / kind / f"{slug}.md"
        if file.is_file():
            return homes.home_of(root, file.read_text(errors="replace"))
    stored = queue.brief(run.state, slug) if slug else None
    return homes.home_of(root, stored) if stored else root


def of(
    config: jbus.Config, project: jbus.Project, now: datetime, home: Path | None = None
) -> list[Need]:
    """Return what waits on the user in one project at `now`, in the list's order: with `home`,
    only that home's, and a root home's scopes' with the root's. Raise `Unknown` where nothing
    is known."""
    run = passes.Pass(config, project, now)
    listed = waiting.read(run.state)
    if listed is None or run.first:
        raise Unknown(f"{project.name}: no pass has listed what waits there yet")
    try:
        found = blockers.deciding(run, listed)
    except questions.Unparsable:
        raise Unknown(f"{project.name}: {questions.path(run.state)} does not parse") from None
    if home is not None:
        root = config.home(project)
        found = [
            (one, said)
            for one, said in found
            if (at := home_of(run, root, _slug(run, one))) == home or home == root == at.parent
        ]
    return [
        Need(project.name, said, blockers.reply(project, one), str(one.get("fail_safe") or ""))
        for one, said in found
    ]


def lines(
    config: jbus.Config,
    projects: list[jbus.Project],
    scope: str,
    now: datetime,
    home: Path | None = None,
) -> list[str]:
    """Return the lines `jbus needs` prints for the projects: a head that counts the items, the
    items, and a line for each project nothing is known of. `scope` names the projects in the
    line that says nothing waits, and `home` keeps one home's items (`of`)."""
    user, found, unknown = config.user.user, [], []
    for project in projects:
        try:
            found += of(config, project, now, home)
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
    """`jbus --project <name> needs` is one project, and `--home` one home of it."""
    parser.add_argument(
        "--home",
        help="a home's directory: only that home's items, and a root home's scopes' with its own",
    )


def _home(config: jbus.Config, project: jbus.Project, directory: str) -> Path:
    """The home `--home` names: the project's root home or one of its scopes. Refuse any other
    directory."""
    root, path = config.home(project).resolve(), Path(directory).expanduser().resolve()
    if path == root or (path.parent == root and (path / "plan.md").is_file()):
        return config.home(project) / path.relative_to(root)
    raise jbus.Refused(f"refused: {directory} is no home of {project.name}")


def _needs(args: argparse.Namespace, config: jbus.Config) -> int:
    if args.home:
        project = verbs.here(config, args.project)
        home = _home(config, project, args.home)
        where = "root home and its scopes" if home == config.home(project) else f"{home.name} home"
        said = lines(config, [project], f"{project.name}'s {where}", verbs.clock(), home)
        print("\n".join(said))
        return 0
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
