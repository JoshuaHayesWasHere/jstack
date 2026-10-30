"""`jbus home status --home <directory>`: print where things stand for one home, at its start.

A home's start prints its part of what jbus and the home's files hold, each part under its own
heading and cut short (`status`). First come the files to read whole: the user's standing rules,
the home's note, and the repo's context pack. Then `## plan`, the lines of `jbus plan`. Then
`## queue`, what waits on the user and the home's open rows. Then `## questions`, the home's open
questions. Then `## merged`, what `jmerge` merged since the home's `merge-seen` mark. Last,
`## to read`, each brief's or request's last Result or Report heading that is not in the home's
`read-seen`. That last part is the one that writes: it marks read a heading whose brief is done,
with `Left: none`, and merged, and on the home's first start it marks every heading there is.

With `--gates` it prints instead what the blocks of the home skill's "Gates" read, one to a line
(`gates`): the repo's project in jbus's config, why no question could be read, and then the home's
open questions, one to a line, their fields joined by `SEP`.

`--home` is the home's directory: the repo's state directory for the root home, or a scope's
directory inside it. A question, a row or a merge is the home's by the brief or the request of its
slug, by the one rule of `jbriefs.home`. `--no-jbus` says that jbus is not installed on the
machine, which the skill checks, since `uv run` puts this command on PATH whether it is or not.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import jbus
from jbriefs import home
from jbus import plan, questions, queue, waiting
from jsettings import paths

SEP = "\037"
WIDTH = 110
"""Characters a line is cut at, but a line of the plan, at `PLAN_WIDTH`, and one to read."""
PLAN_WIDTH = 150
NO_JBUS = "no jbus: jbus is not installed here, so it holds no question"
SHOW_THE_OPEN_ONES = 'the block of "Show the open ones"'


@dataclass(frozen=True)
class Home:
    """`Home` is one home of a repo: its directory (`mine`), the repo's state directory (`state`),
    which is `mine` for the root home, and the repo's name."""

    mine: Path
    state: Path
    repo: str

    @classmethod
    def of(cls, directory: str) -> Home:
        mine, repo = Path(directory), paths.repo_name()
        return cls(mine, mine if mine.name == repo else mine.parent, repo)

    @property
    def scope(self) -> str:
        return "" if self.mine == self.state else self.mine.name

    @property
    def own(self) -> str:
        """The slug the home asks its own questions under."""
        return f"home-{self.scope}" if self.scope else "home"

    def keeps(self, kind: str, slug: str) -> bool:
        """Whether the brief (`tasks`) or the request (`scouts`) of `slug` is this home's."""
        brief = self.state / kind / f"{slug}.md"
        return home.home_of(self.state, _text(brief)) == self.mine

    def asked(self, slug: str) -> bool:
        """Whether a question asked under `slug` is this home's: one under its own slug, or one
        whose brief or request is its. A question no brief, no request and no home asked is the
        root home's."""
        if slug == self.own:
            return True
        if slug == "home" or (
            slug.startswith("home-") and (self.state / slug[5:] / "plan.md").is_file()
        ):
            return False
        for kind in ("tasks", "scouts"):
            if (self.state / kind / f"{slug}.md").is_file():
                return self.keeps(kind, slug)
        return self.mine == self.state


def _text(file: Path) -> str:
    try:
        return file.read_text(errors="replace")
    except OSError:
        return ""


def _lines(file: Path) -> list[str]:
    text = _text(file)
    return text.splitlines() if text else []


def clip(line: str, width: int = WIDTH) -> str:
    return line[: width - 3] + "..." if len(line) > width else line


def atmost(lines: Iterable[str], count: int, more: str) -> list[str]:
    lines = list(lines)
    if len(lines) <= count:
        return lines
    return [*lines[:count], f"... and {len(lines) - count} more: {more}"]


@dataclass(frozen=True)
class Bus:
    """What jbus holds for a home: the repo's project, why nothing could be read, and the home's
    open questions."""

    project: jbus.Project | None
    config: jbus.Config | None
    why: str
    open: tuple[questions.Question, ...]


def bus(here: Home, installed: bool) -> Bus:
    if not installed:
        return Bus(None, None, NO_JBUS, ())
    try:
        config = jbus.load()
    except jbus.Refused:
        config = None
    project = (
        next((one for one in config.projects if one.state == here.repo), None) if config else None
    )
    if config is None or project is None:
        why = (
            f"no project: jbus's config names no project for {here.repo}, "
            "so it holds no question of this repo"
        )
        return Bus(None, config, why, ())
    state = config.state(project)
    try:
        kept = questions.read(state)
    except questions.Unparsable:
        why = f"jbus could not be read: {questions.path(state)} is not the record jbus writes"
        return Bus(project, config, why, ())
    mine = (one for one in kept if one.answer is None and here.asked(one.slug))
    return Bus(project, config, "", tuple(mine))


def gates(here: Home, found: Bus) -> list[str]:
    fields = (
        (
            one.number,
            one.slug,
            one.question,
            one.default,
            one.built_on,
            one.undo,
            one.holds,
            one.fail_safe,
        )
        for one in found.open
    )
    asked = [SEP.join(map(str, each)) for each in fields]
    return [found.project.name if found.project else "", found.why, *asked]


def _plan(here: Home, found: Bus) -> list[str]:
    more = f"jbus plan --scope {here.scope}" if here.scope else "jbus plan"
    try:
        if found.config is None or found.project is None:
            raise jbus.Refused("no jbus")
        said = plan.listing(found.config, found.project, here.scope or None)
    except (jbus.Refused, OSError):
        return [f"no jbus plan: read {here.mine}/plan.md whole"]
    return atmost((clip(line, PLAN_WIDTH) for line in said.rstrip("\n").split("\n")), 12, more)


def _queue(here: Home, found: Bus) -> list[str]:
    if found.why or found.config is None or found.project is None:
        return [found.why]
    more = f"jbus --project {found.project.name} queue show"
    state = found.config.state(found.project)
    try:
        rows = queue.load(state)
        said = queue.noted(state, rows)
    except queue.Unparsable as error:
        return [clip(f"refused: {error}")]
    user = found.config.user.user
    listed = [one["line"] for one in waiting.read(state) or []]
    still = sorted((row for row in rows if not queue.over(row)), key=queue.order)
    ours = (
        f"{row['slug']} | {row.get('status', '')} | {row.get('pr', '')} | {row.get('why', '')}"
        for row in still
        if here.keeps("tasks", row["slug"])
    )
    left = len(rows) - len(still)
    if left:
        counted = "1 finished row" if left == 1 else f"{left} finished rows"
        said = f"{counted} not shown: jbus queue show --all\n{said}"
    ending = [line for line in said.splitlines() if line.strip()]
    return [
        *([f"waiting on {user}:"] if listed else []),
        *atmost((clip(line) for line in listed), 3, more),
        *atmost((clip(line) for line in ours), 10, more),
        *atmost((clip(line) for line in ending), 2, more),
    ]


def _questions(here: Home, found: Bus) -> list[str]:
    said = []
    if (here.mine / "gates.md").exists():
        said.append(
            'a gates file: run the block of "Move the ones a file still has" ("Gates"), '
            "then this block again"
        )
    if found.why:
        return [*said, found.why]
    if not found.open:
        return [*said, "none is open"]
    asked = (
        clip(f"question {one.number}, from {one.slug}: {one.question} (default: {one.default})")
        for one in found.open
    )
    return [*said, *atmost(asked, 5, SHOW_THE_OPEN_ONES)]


def _merged(lines: list[str]) -> list[tuple[str, str]]:
    """Each line of `merge.log` that logs a merge, with the slug it merged."""
    found = []
    for line in lines:
        words = line[17:].split()
        if line[17:].startswith("merged ") and len(words) > 2:
            found.append((words[2], line))
    return found


def _merges(here: Home) -> list[str]:
    log = here.state / "merge.log"
    lines = _lines(log)
    seen = _text(here.mine / "merge-seen").rstrip("\n")
    mark = int(seen) if seen.isdigit() else len(lines)
    if mark > len(lines):
        mark = 0
    new = (clip(line) for slug, line in _merged(lines[mark:]) if here.keeps("tasks", slug))
    return atmost(new, 5, str(log))


def _heading(brief: Path) -> str:
    found = [line for line in _lines(brief) if line.startswith(("## Result", "## Report"))]
    return found[-1] if found else ""


def _finished(brief: Path) -> bool:
    """Whether the brief's last Result says `Status: done` and `Left: none`."""
    done = left = result = False
    for line in _lines(brief):
        if line.startswith("## "):
            result = False
        if line.startswith("## Result"):
            done = left = False
            result = True
        words = line.split()
        if result and words[:1] == ["Status:"]:
            done = words == ["Status:", "done"]
        if result and words[:1] == ["Left:"]:
            left = words == ["Left:", "none"]
    return done and left


def _to_read(here: Home) -> list[str]:
    seen = here.mine / "read-seen"
    marked = set(_lines(seen))
    unread = []
    for kind in ("tasks", "scouts"):
        for brief in sorted(one for one in (here.state / kind).glob("*.md") if one.is_file()):
            said = f"{kind}/{brief.name}: {_heading(brief)}"
            if _heading(brief) and said not in marked and here.keeps(kind, brief.stem):
                unread.append(said)
    if not seen.exists():
        seen.write_text("".join(f"{said}\n" for said in unread))
        return [
            f"no mark yet: {len(unread)} headings of this home's are marked read in {seen}, "
            "and none is shown"
        ]
    merged = {f"tasks/{slug}.md" for slug, _ in _merged(_lines(here.state / "merge.log"))}
    shown, finished = [], []
    for said in unread:
        brief = said.partition(": ## ")[0]
        if brief in merged and _finished(here.state / brief):
            finished.append(said)
        else:
            shown.append(said)
    if finished:
        with seen.open("a") as kept:
            kept.writelines(f"{said}\n" for said in finished)
    said = atmost(shown, 8, "mark these read, then run this block again")
    if finished:
        said.append(
            f"marked read and not shown: {len(finished)} finished headings, "
            "each done with Left: none and merged"
        )
    return said


def _whole(here: Home) -> list[str]:
    said = [
        f"read whole: {file}"
        for file in (
            here.state / "standing.md",
            here.mine / "handoff.md",
            here.mine / "handoff.next.md",
        )
        if file.is_file()
    ]
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    index = Path(top.stdout.strip()) / "docs" / "context" / "INDEX.md"
    if top.returncode == 0 and index.is_file():
        said.append(f"read whole: {index}")
    return said


def status(here: Home, found: Bus) -> list[str]:
    return [
        *_whole(here),
        "## plan",
        *_plan(here, found),
        "## queue",
        *_queue(here, found),
        "## questions",
        *_questions(here, found),
        "## merged",
        *_merges(here),
        "## to read",
        *_to_read(here),
    ]


def run(directory: str, installed: bool, only_gates: bool) -> list[str]:
    here = Home.of(directory)
    found = bus(here, installed)
    return gates(here, found) if only_gates else status(here, found)
