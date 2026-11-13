"""`jbus needs`: print what waits on the user, for one project with `--project` or for all.

It is the one answer to "what needs me". It reads the list the last pass wrote
(`waiting-on-user.json`) and keeps only what the user has to decide, by the one rule that also
raises a decision and wakes a home with it (`blockers.deciding`): a gate whose `Holds:` line holds
it, a gate with no default or one that names a door, a go gate whose silence starts nothing, a row
whose brief has no go, a pull request `jmerge` holds for the user's word, a hold no crew
clears that the user's word lifts (`jbus.clock.held`), a setup only the user
can give, and an approved row that waits for room on a full /tmp after the pass removed what
finished crews left there (`room`): its row's `why` says so, `waiting: /tmp is full: its quota`,
from the first pass it waits. A hold of GitHub's budget at or under its floor is one item for
the whole project once it has lasted over ten minutes (`budgethold.needed`), since no row
launches until its reset. A failing state backup is one item of the machine's, on the infra project's
list and its root home's, until a snapshot succeeds (`jbus.snapshot.failing`). A row a home can clear by itself (a row at `gate`, a leftover its
home still has, a hold a thread works on) is not on it, and neither is a refused go: a refusal is
an act of the home's (`acts.jsonl`), most of them a sha that did not match, and the home tries
again by itself.

Each item is one line with what it holds, then a plain hint for the reply, the same `Reply:` a
decision carries (`blockers.reply`), and, for a gate that holds, the fail-safe to read first. A
project no pass has listed yet says so, since nothing is known of it. `jbus home status` opens with
the same lines for its own project (`jbus.homestatus`).

With no `--home` the list also has each ask a home of the project made of the user itself that
is still open in its `told` file (`asks`), the root's and each scope's, named with its home, so
the project-wide "nothing waits" means no home has an ask open either. A closed home's asks (a
scope whose plan is archived) stay on it and on the root home's list until cleared. `jbus home
status` counts them in its line of what waits in other projects.

`--home <directory>` keeps one home's items of its project: a scope's directory keeps that
scope's, and the root home's keeps its own and every scope's. Every home's list also has each item
about the whole project, no row and no home (`WIDE`, and a hold of GitHub's budget), and each ask
the home made of the user itself that is still open in its `told` file (`asks`), so a home's
"nothing waits" means none of these is open either. An item is a home's by the slug it
is about, by the one rule (`home_of`) that `jbus home status --home` reads questions by too: a
home's own slug (`home`, `home-<scope>`), else the home of the slug's brief or request
(`jbriefs.home.home_of`), in the home's files or as the queue stored it, else the catch-all's,
`uncategorized`; the root's own items, `home` and no slug, are the root's. A pull
request `jmerge` holds is about the row whose pull request it is.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jbus
from jbriefs import home as homes
from jbriefs import meets
from jbus import (
    blockers,
    budgethold,
    alert,
    cleanup,
    passes,
    questions,
    queue,
    snapshot,
    turnend,
    verbs,
    waiting,
    waive,
)
from jsettings.brief import head_lines

FREE = "nothing to reply: free room on it, and the next pass launches the row"
"""The hint a row that waits for /tmp ends in: no word of the user's frees it."""
WIDE = ("install", "config")
"""The kinds of item about the whole project, no row and no home: every home's list has them."""
HELD = "nothing to reply: the launches start again at the reset, and merges still go"
"""The hint a hold of GitHub's budget ends in: no word of the user's lifts it."""
UNIT = "jbus-snapshot.service"
MEND = (
    f"nothing to reply: fix what its last line names (journalctl --user -u {UNIT} has the rest), "
    "and the next snapshot that succeeds clears this"
)
"""The hint a failing backup ends in: the next run that succeeds ends it, and no word does."""


@dataclass(frozen=True)
class Need:
    """`Need` is one thing only the user can do: the project it is in, what it is and what it
    holds (`said`), the plain hint for the reply (`blockers.reply`), and the fail-safe of a gate
    that holds."""

    project: str
    said: str
    reply: str
    fail_safe: str = ""

    def lines(self) -> list[str]:
        safe = [f"  fail-safe: {self.fail_safe}"] if self.fail_safe else []
        answer = f"  answer: {self.reply}"
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
    if one["kind"] == "held" and not one.get("slug"):
        return str(next(iter(one.get("rows", [])), ""))
    return str(one.get("slug") or "")


def home_of(state: Path, root: Path, slug: str) -> Path:
    """The directory of the home a slug is, of the project whose jbus state is `state` and whose
    root home is `root`: a scope's for `home-<scope>`, else the home of its brief or request, in
    the home's files or as the queue stored it. The root's own items, `home` and no slug, are the
    root's, and any other slug of no brief is the catch-all's (`jbriefs.home.catchall`). It is
    the one rule, which `jbus home status --home` reads questions by too."""
    if slug.startswith("home-") and (root / slug[5:]).is_dir():
        return root / slug[5:]
    for kind in ("tasks", "scouts"):
        file = root / kind / f"{slug}.md"
        if file.is_file():
            return homes.home_of(root, file.read_text(errors="replace"))
    if slug in ("", "home"):
        return root
    stored = queue.brief(state, slug)
    return homes.home_of(root, stored) if stored else homes.catchall(root)


def of(
    config: jbus.Config, project: jbus.Project, now: datetime, home: Path | None = None
) -> list[Need]:
    """Return what waits on the user in one project at `now`, in the list's order, then the asks
    still open in its homes' `told` files (`asks`): with `home`, only that home's, and a root
    home's scopes' with the root's, and with none, every home's. Raise `Unknown` where nothing is
    known."""
    run = passes.Pass(config, project, now)
    listed = waiting.read(run.state)
    if listed is None or run.first:
        raise Unknown(f"{project.name}: no pass has listed what waits there yet")
    try:
        found = blockers.deciding(run, listed)
    except questions.Unparsable:
        raise Unknown(f"{project.name}: {questions.path(run.state)} does not parse") from None
    needs: list[tuple[str | None, Need]] = [
        (
            None if one["kind"] in WIDE else _slug(run, one),
            Need(project.name, said, blockers.reply(one), str(one.get("fail_safe") or "")),
        )
        for one, said in found
    ]
    needs += [(slug, Need(project.name, f"row {slug}: {why}", FREE)) for slug, why in room(run)]
    if held := budgethold.needed(run):
        needs.append((None, Need(project.name, held, HELD)))
    if config.owner(alert.MACHINE) == project and (backup := snapshot.failing(config)):
        since, line = backup
        said = f"{UNIT}, the state backup, has failed since {config.user.stamp(since)}"
        needs.append(("", Need(project.name, f"{said}; its last line: {line}", MEND)))
    root = config.home(project)
    if home is None:
        return [need for _, need in needs] + asks(project, root, root)
    kept = [
        need
        for slug, need in needs
        if slug is None
        or (at := home_of(run.state, root, slug)) == home
        or home == root == at.parent
    ]
    return kept + asks(project, root, home)


def asks(project: jbus.Project, root: Path, home: Path) -> list[Need]:
    """Return each ask a home made of the user itself that is still open: a `decision local` or
    `stop local` line of its `told` file, which `jbus told` keeps until a `cleared local` line ends
    it (`jbus.turnend`). With the root home, its scopes' too, and none where the root home has no
    directory yet. A closed scope, whose plan is archived (`plan-archived.md`, no `plan.md`), has
    no thread to ask, but its open asks still wait on the user: the root home's list keeps them,
    named with the closed home, until a `cleared local` line in its `told` ends them."""
    if not root.is_dir():
        return []
    scopes = sorted(one for one in root.iterdir() if (one / "plan.md").is_file() or closed(one))
    found = []
    for at in [root, *scopes] if home == root else [home]:
        name = "root" if at == root else at.name
        for line in turnend.open_asks(at):
            if closed(at):
                reply = f"reply to the root home in your own words: the {name} home is closed"
                found.append(Need(project.name, f"{name} home (closed) {line}", reply))
            else:
                reply = f"reply to the {name} home in your own words"
                found.append(Need(project.name, f"{name} home {line}", reply))
    return found


def closed(scope: Path) -> bool:
    """Whether a scope's directory is a closed home: its plan archived, with no plan open."""
    return (scope / "plan-archived.md").is_file() and not (scope / "plan.md").is_file()


def room(run: passes.Pass) -> list[tuple[str, str]]:
    """Return each approved row the last pass held back for a full /tmp, with its `why`
    (`cleanup.WAITING`)."""
    try:
        rows = queue.load(run.state)
    except queue.Unparsable:
        return []
    return [
        (row["slug"], str(row["why"]))
        for row in sorted(rows, key=queue.order)
        if row.get("status") in queue.UNLAUNCHED
        and cleanup.WAITING.match(str(row.get("why") or ""))
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
    stands = [line for project in projects for line in standing(config, project, home)]
    stands += [line for project in projects for line in waived(config, project, now, home)]
    for project in projects:
        try:
            found += of(config, project, now, home)
        except Unknown as why:
            unknown.append(f"not known: {why}")
    if not found and unknown:
        return [*unknown, f"nothing else known waits on {user} in {scope}", *stands]
    if not found:
        return [f"nothing waits on {user} in {scope}", *stands]
    names = sorted({one.project for one in found}, key=[p.name for p in projects].index)
    head = f"waiting on {user}: {len(found)}, in {', '.join(names)}"
    return [head, *(line for one in found for line in one.lines()), *unknown, *stands]


def standing(config: jbus.Config, project: jbus.Project, home: Path | None = None) -> list[str]:
    """Return a line for each home of the project that holds a standing word for follow-ups
    (`jbus.standing`), naming the word and the user's words: with `home`, only that home's, and
    a root home's scopes' with the root's. What it approves waits on nobody, so the user sees
    here what is approved in their name."""
    root = config.home(project)
    lines = []
    for scope, (word, said) in sorted(queue.standing_words(config.state(project)).items()):
        if home is not None and home not in (root, root / scope):
            continue
        name = scope or "root"
        lines.append(
            f"{project.name} {name} home standing word {word} for follow-ups that open no door: "
            f'"{said.words}"'
        )
    return lines


def waived(
    config: jbus.Config, project: jbus.Project, now: datetime, home: Path | None = None
) -> list[str]:
    """Return a line for each waiver the root home made on its own judgment in the day before
    `now` (`jbus.waive`), naming the row, each line, the reason and the undo: with `home`, only
    the rows of that home, and a root home's scopes' with the root's. It waits on nobody, so the
    user reads here, with nothing to answer, what the root waived in their name."""
    state, root = config.state(project), config.home(project)
    lines = []
    for act in waive.recent(state, now):
        slug, said = act["action"]["subject"], act["evidence"]
        at = home_of(state, root, slug)
        if home is not None and home != at and not home == root == at.parent:
            continue
        brief = root / "tasks" / f"{slug}.md"
        items = meets.done_when(head_lines(brief.read_text())) if brief.is_file() else []
        named = ", ".join(
            f'line {one} "{items[int(one) - 1]}"' if int(one) <= len(items) else f"line {one}"
            for one in act["action"]["pre"].split()
        )
        lines.append(
            f"{project.name} root waived {slug}: {named}, because {said['words']}; "
            f"undo: {said.get('undo', '')}; nothing to answer"
        )
    return lines


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
        "what waits on the user, with what each holds and a plain hint for the reply",
        _arguments,
        _needs,
    ),
)
