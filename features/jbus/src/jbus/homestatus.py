"""`jbus home status --home <directory>`: print where things stand for one home, at its start.

A home's start prints its part of what jbus and the home's files hold, each part under its own
heading and cut short (`status`). First come the files to read whole: the
home's note and the repo's context pack. A `standing.md` is not one: it holds no rule
(`jbus.rules`). Then `## waiting on you`, what waits on the user in
this project as `jbus needs` prints it, uncut, and a count for each other project that has
something waiting. Then `## plan`, the lines of `jbus plan`. Then `## queue`, the home's open
rows. Then `## questions`, the home's open questions. Then `## merged`, what `jmerge` merged
since the home's `merge-seen` mark. Last,
`## to read`, each brief's or request's last Result or Report heading that is not in the home's
`read-seen`. That last part is the one that writes: it marks read a heading whose brief is done,
with `Left: none`, and merged, and on the home's first start it marks every heading there is.

With `--gates` it prints instead what the blocks of the home skill's "Gates" read, one to a line
(`gates`): the repo's project in jbus's config, why no question could be read, and then the home's
open questions, one to a line, their fields joined by `SEP`.

`--home` is the home's directory: the repo's state directory for the root home, or a scope's
directory inside it. A row or a merge is the home's by the brief of its slug, by the rule of
`jbriefs.home`, and a question is the home's by its slug, by the one rule `jbus needs --home`
reads items by too (`jbus.needs.home_of`). `--no-jbus` says that jbus is not installed on the
machine, which the skill checks, since `uv run` puts this command on PATH whether it is or not.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import jbus
from jbriefs import home
from jbriefs import status as status_line
from jbriefs.status import Status
from jbus import needs, plan, questions, queue, verbs
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
    which is `mine` for the root home, and the repo's name. It reads the repo's scopes once, at
    the first brief it is asked of, and answers every brief of the pass from that read."""

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

    @cached_property
    def _home_of(self) -> Callable[[str], Path]:
        return home.reader(self.state)

    def keeps(self, kind: str, slug: str) -> bool:
        """Whether the brief (`tasks`) or the request (`scouts`) of `slug` is this home's."""
        brief = self.state / kind / f"{slug}.md"
        return self._home_of(_text(brief)) in self.works

    @cached_property
    def works(self) -> frozenset[Path]:
        """The homes whose rows this one works (`jbriefs.home.works`)."""
        return home.works(self.state, self.mine)


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
    mine = (
        one
        for one in kept
        if one.answer is None and needs.home_of(state, here.state, one.slug) in here.works
    )
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
        *atmost((clip(line) for line in ours), 10, more),
        *atmost((clip(line) for line in ending), 2, more),
    ]


def _needs(found: Bus) -> list[str]:
    """What waits on the user, as `jbus needs` prints it for this home's project, never cut, and
    one line for the other projects of the config that have something waiting."""
    if found.why or found.config is None or found.project is None:
        return [found.why]
    config, now = found.config, verbs.clock()
    said = needs.lines(config, [found.project], found.project.name, now)
    elsewhere = []
    for other in config.projects:
        try:
            count = len(needs.of(config, other, now)) if other != found.project else 0
        except needs.Unknown:
            count = 0
        if count:
            elsewhere.append(f"{other.name} {count}")
    if elsewhere:
        said.append(f"elsewhere: {', '.join(elsewhere)}: jbus needs")
    return said


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


def _read_to(lines: list[str], seen: str | None) -> int:
    """How many of merge.log's `lines` the home has read, by its `merge-seen` mark, as the home
    skill's merge step reads it: the last merged line it read, so the lines after it where a cut
    kept it, and none where the cut took it, since each line a cut keeps is newer. An empty mark
    is none read, and no mark the log's end. A number is a count the step wrote before it marked
    by a line."""
    if seen is None:
        return len(lines)
    if seen.isdigit():
        return int(seen)
    found = [n for n, line in enumerate(lines, 1) if line == seen]
    return found[-1] if found else 0


def _merges(here: Home) -> list[str]:
    log = here.state / "merge.log"
    lines = _lines(log)
    seen = here.mine / "merge-seen"
    mark = _read_to(lines, _text(seen).rstrip("\n") if seen.is_file() else None)
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
            done = status_line.read(" ".join(words[1:])) is Status.DONE
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
        "## waiting on you",
        *_needs(found),
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
