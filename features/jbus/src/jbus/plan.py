"""`jbus plan`: read a home's plan, and join it with the queue at each read.

`plan.md` holds what the user decided: one section for each entry, `## <slug>: <one line>`,
with its "Done when" list and the user's words under `Decisions:`. It holds no status. An
entry is often several briefs, and each brief is a row of the queue that names its entry
(`queue.entry`). So `status` works out the progress of an entry's work from its rows at each
read, in the words of the row statuses. No model types the status, and nothing here writes
it down.

An entry with no row has only what the home wrote of it: its `Stage:` line, which says where
the planning is, a `Stage`: `proposed`, `planned`, `parked` or `scouting`, read from the line's
first word, and the rest of the line is a note. A first word outside the four is no stage:
`jbus plan` flags it, and the entry is never briefed (`buildable`). A plan from before has
`Status:` lines, which someone typed. jbus ignores such a line where the entry has rows,
and shows it as typed where the entry has none.

An entry whose rows are all over (`queue.over`) is finished, and `close` moves its section,
as it is, to `plan-done.md` beside the plan. That is the only write in this module, and it
changes no line of the section. `plan.md` keeps the open entries only, so a home's start
reads the lines `shown` returns and not the file.

The user gives an entry its go once, by `jbus plan go <entry> --message <thread>/<message>`: jbus
reads the message from T3 Code and refuses one that is not the user's own, as `queue approve
--message` does. The go is a `Go` in `goes.json` in the project's state directory, one for each
entry of each home's plan, and it is bound to the entry's head (`head`): its heading and its
`Done when:` lines. Under the setting `go = "entry"` jbus approves each row filed under the entry
(`queue add --entry`) by the go, basis `queue.ENTRY`, when it is queued and on each pass, an edit of
its brief included (`queue.entered`). The go holds while the entry is in the plan with the same
head and no `jbus plan stop <entry>` stopped it (`holding`). When it no longer holds, each row of
the entry that has not launched waits for the user's go again, and a launched one goes on.

A go that holds over an entry whose rows are all over is owed (`owed`): the user said go and
nothing is queued, so its home is woken to queue the next row or close the entry.

An entry that waits on other work says so on its `Builds on:` line, as a brief does
(`jbriefs.chains.builds_on`), and never in its `Decisions:` prose. Once every row or entry the
line names has merged and the entry has no row of its own, it is ready to brief (`buildable`):
its home is woken to brief it and queue its first row.
"""

from __future__ import annotations

import argparse
import enum
import hashlib
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbriefs import home as homes
from jbriefs.chains import builds_on
from jbus import Config, Refused, locked, queue, read_json, t3, verbs, work, write_json

LINE, STATUS = 56, 60
_ENTRY = re.compile(r"## (?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*): (?P<line>.+)")
_SCOPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_WORD = re.compile(r"[^\s,;:(]*")


class Stage(enum.Enum):
    """Where the planning of an entry with no row is. `buildable` says whether the entry is
    briefed once its `Builds on:` has merged: a parked entry waits for the user, and a scouting
    one for its scout."""

    PROPOSED = "proposed"
    PLANNED = "planned"
    PARKED = "parked"
    SCOUTING = "scouting"

    @property
    def buildable(self) -> bool:
        return self in (Stage.PROPOSED, Stage.PLANNED)


@dataclass(frozen=True)
class Entry:
    """An `Entry` is one `## <slug>: <one line>` section of a plan. `said` is what its
    `Stage:` line says, `stage` is the `Stage` its first word names, and `unknown` is that word
    where it names none. An entry with no `Stage:` line has neither. `typed` is the whole
    `Status:` line of a plan from before. `said` and `typed` may be empty. `builds_on` is each
    row or entry its `Builds on:` line names."""

    slug: str
    line: str
    said: str = ""
    typed: str = ""
    builds_on: frozenset[str] = frozenset()
    stage: Stage | None = None
    unknown: str = ""

    @property
    def buildable(self) -> bool:
        """Whether the entry's stage lets it be briefed. An entry with no `Stage:` line is, as
        a plan from before has none, and one whose stage is unknown is not."""
        return self.stage.buildable if self.stage else not self.unknown


def staged(said: str) -> tuple[Stage | None, str]:
    """Read a `Stage:` line's text: the `Stage` its first word names, or None and that word,
    or the whole text where it starts with no word."""
    word = _WORD.match(said)
    first = word[0] if word else ""
    known = next((one for one in Stage if one.value == first), None)
    return known, "" if known else first or said


def entries(text: str) -> list[Entry]:
    """Return the entries of a plan, in its order. A `## ` heading that is not
    `<slug>: <one line>` starts no entry, and ends the one above it. The `Builds on:` line is
    read over the entry's whole section, as a brief's is, so an item wrapped onto the next line
    counts."""
    found: list[Entry] = []
    bodies: list[list[str]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            heading = _ENTRY.fullmatch(line.rstrip())
            inside = heading is not None
            if heading:
                found.append(Entry(heading["slug"], heading["line"].strip()))
                bodies.append([])
        elif inside:
            bodies[-1].append(line)
            if line.startswith("Stage:") and not found[-1].said:
                said = line.removeprefix("Stage:").strip()
                stage, unknown = staged(said)
                found[-1] = replace(found[-1], said=said, stage=stage, unknown=unknown)
            elif line.startswith("Status:") and not found[-1].typed:
                found[-1] = replace(found[-1], typed=line.strip())
    return [
        replace(one, builds_on=builds_on("\n".join(body)))
        for one, body in zip(found, bodies, strict=True)
    ]


def rows_of(slug: str, rows: list[queue.Row]) -> list[queue.Row]:
    return [row for row in rows if queue.entry(row) == slug]


@dataclass(frozen=True)
class Progress:
    """The count of some rows, in the parts `status` says. `finished` is each final status with
    its count of the rows that are over, in the order of `work.FINAL`. `pulls` is each open row
    that has a pull request, as its number and its status, by number. `rest` is each other open
    row's word with its count, in the order of `queue.STATUSES`. Each row is in one part."""

    total: int
    finished: tuple[tuple[str, int], ...]
    pulls: tuple[tuple[str, str], ...]
    rest: tuple[tuple[str, int], ...]

    @property
    def over(self) -> int:
        return sum(count for _, count in self.finished)


def progress(rows: list[queue.Row]) -> Progress:
    """Count the rows: the finished ones by status, each open row with a pull request, and the
    rest by status, where a queued row with no approval is `queued not approved` and a final
    row that is not over is `<status> and waiting`."""
    finished = Counter(row["status"] for row in rows if queue.over(row))
    still = [row for row in rows if not queue.over(row)]
    pulls = sorted(
        (row for row in still if row.get("pr")), key=lambda row: (len(row["pr"]), row["pr"])
    )
    rest: Counter[str] = Counter()
    for row in still:
        if row.get("pr"):
            continue
        word = row.get("status", "queued")
        if word == "queued" and not row.get("approved"):
            word = "queued not approved"
        elif word in work.FINAL:
            word = f"{word} and waiting"
        rest[word] += 1
    return Progress(
        len(rows),
        tuple((name, finished[name]) for name in work.FINAL if finished[name]),
        tuple((row["pr"], row.get("status", "queued")) for row in pulls),
        tuple(
            (word, rest[word])
            for name in queue.STATUSES
            for word in (name, f"{name} not approved", f"{name} and waiting")
            if rest[word]
        ),
    )


def status(entry: Entry, rows: list[queue.Row]) -> str:
    """Return the progress of the entry's work. `rows` are the rows of the entry.

    With rows, the function says their `progress`: the finished ones first, `4 of 7 merged`,
    then each open row that has a pull request, by its number, `#383 at pr`, then the rest by
    status, `1 queued not approved`. With every row over, it says to close the entry. With no
    rows, it returns the entry's stage, or its typed line, or `no stage`.
    """
    if not rows:
        if entry.said:
            return entry.said
        return f"(typed) {entry.typed}" if entry.typed else "no stage"
    counted = progress(rows)
    if counted.over == counted.total:
        every = "its row" if counted.total == 1 else f"all {counted.total} rows"
        return f"{every} finished: close it"
    parts = [f"{count} {name}" for name, count in counted.finished] or ["0 merged"]
    count, _, name = parts[0].partition(" ")
    parts[0] = f"{count} of {counted.total} {name}"
    parts += [f"{pr} at {word}" for pr, word in counted.pulls]
    parts += [f"{count} {word}" for word, count in counted.rest]
    return ", ".join(parts)


GOES = "goes.json"
LOCK = "goes.lock"


@dataclass(frozen=True)
class Go:
    """`Go` is the user's go for one plan entry. `scope` is the scoped home whose plan holds the
    entry, or empty for the root home. `head` is the entry's head's sha (`head`) when the user
    gave it. `ref` is the user's message, `<thread id>/<message id>`, with its words, its time and
    its thread's title as `t3.heard` read them. `ran_by` and `ran_at` are who ran `plan go` and
    when. `stopped` is when and by whom `plan stop` stopped it, or empty."""

    entry: str
    scope: str
    head: str
    ref: str
    words: str
    said_at: str
    said_in: str
    ran_by: dict[str, str]
    ran_at: str
    stopped: str = ""

    def said(self) -> queue.Said:
        return queue.Said(self.words, self.said_at, self.said_in, True, self.ref)


def head(text: str, slug: str) -> str:
    """Return the sha256 of the entry's head: its `## <slug>: ` line and its `Done when:` lines,
    the label's and each item's under it. Return nothing for a plan with no such entry."""
    lines = text.splitlines()
    start = next((at for at, line in enumerate(lines) if line.startswith(f"## {slug}: ")), None)
    if start is None:
        return ""
    kept, inside = [lines[start].rstrip()], False
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("Done when:"):
            inside = True
        elif inside and not line.startswith(("- ", " ", "\t")):
            inside = False
        if inside:
            kept.append(line.rstrip())
    return hashlib.sha256("\n".join(kept).encode()).hexdigest()


def goes(state: Path) -> list[Go]:
    """Return every go kept, stopped or not. A record this module did not write is left out."""
    found = []
    for one in read_json(state / GOES, []) or []:
        try:
            found.append(Go(**one))
        except TypeError:
            continue
    return found


def _kept(state: Path, made: Go) -> None:
    """Keep `made` in place of the go its entry had, under the lock that each change of the
    file holds, so two homes that change it at once both keep theirs."""
    with locked(state, LOCK):
        others = [one for one in goes(state) if (one.scope, one.entry) != (made.scope, made.entry)]
        write_json(state / GOES, [asdict(one) for one in [*others, made]])


def _scope(home: Path, directory: Path) -> str:
    return "" if directory == home else directory.name


def why_not(made: Go, text: str | None) -> str:
    """Return why the go no longer holds for the plan `text`, or nothing while it holds."""
    if made.stopped:
        return f"stopped {made.stopped}"
    if text is None or not head(text, made.entry):
        return "the entry is not in the plan: it closed"
    if head(text, made.entry) != made.head:
        return "the entry's heading or Done when lines changed"
    return ""


def holding(state: Path, home: Path, brief: str, entry: str) -> queue.Said | None:
    """Return the user's go for the plan entry `entry` of the home the brief belongs to
    (`jbriefs.home.home_of`), where it holds, or None. A brief of the catch-all's
    (`uncategorized`) takes the go of an entry of its own plan, else of the root's: the root
    plans and briefs, and the catch-all owns the row from the queue on."""
    directory = homes.home_of(home, brief)
    places = [directory, *([home] if directory == homes.catchall(home) else [])]
    found = (
        (made, place)
        for place in places
        for made in goes(state)
        if (made.scope, made.entry) == (_scope(home, place), entry)
    )
    made, directory = next(found, (None, directory))
    if made is None:
        return None
    try:
        text: str | None = (directory / "plan.md").read_text()
    except OSError:
        text = None
    return None if why_not(made, text) else made.said()


def filed_under(home: Path, state: Path, slug: str, text: str, entry: str) -> None:
    """Refuse a row a home adds (`queue add --from`) outside an open entry of its plan, so that
    each row the home files is approved by its entry's go (`holding`), asked of the user once for
    the entry and never for the row. The row is filed under `entry`, or under its own slug where
    `entry` is empty, as `queue.given_entry` reads it. The plan is the one of the home the brief
    belongs to, and for the catch-all's the root's too, the plans `holding` reads.

    A row already in the queue, a follow-up (a brief with a `Follows:` line, approved on its
    parent's go), and a brief whose home has no plan pass: a repo `jbus plan` does not answer for
    has none. A row jbus filed never comes here, since its filer calls `queue.add` itself."""
    if queue.named_parent(slug, text) or queue.fresh(state, slug) is not None:
        return
    directory = homes.home_of(home, text)
    places = [directory, *([home] if directory == homes.catchall(home) else [])]
    plans = [place for place in places if (place / "plan.md").is_file()]
    if not plans:
        return
    found = [one.slug for place in plans for one in entries((place / "plan.md").read_text())]
    if (entry or slug) in found:
        return
    whose = " or ".join("root" if place == home else place.name for place in plans)
    listed = ", ".join(dict.fromkeys(found)) or "none"
    if entry:
        raise Refused(
            f"refused: --entry {entry} names no entry of the {whose} home's plan, whose open "
            f"entries are: {listed}, and nothing is queued"
        )
    raise Refused(
        f"refused: {slug} is filed under no entry of the {whose} home's plan: add it with "
        f"--entry <entry> of an open entry ({listed}), or write its entry first, one heading and "
        "its Done when: list, and ask the user for the entry's go once, recorded with jbus plan "
        "go <entry> --message <thread>/<message>, and nothing is queued"
    )


def entry_go(state: Path, home: Path) -> queue.EntryGo:
    return lambda brief, entry: holding(state, home, brief, entry)


def _gone(made: Go | None, text: str) -> str:
    if made is None:
        return ""
    why = why_not(made, text)
    if not why:
        return f"go {made.said_at}"
    return f"go {why}" if made.stopped else f"go void: {why}"


def _cut(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: cap - 3].rstrip() + "..."


def shown(text: str, rows: list[queue.Row], given: list[Go] | None = None) -> str:
    """Return a line for each entry whose stage is unknown, first, so the home's start, which
    cuts the listing at 12 lines, never cuts one. Then one line for each entry of the plan: its
    slug, its one line and its status, and the entry's go where `given` has one. It cuts each part
    short so that a plan of seventeen entries fits on one screen."""
    said, flags = [], []
    kept = {one.entry: one for one in given or []}
    for one in entries(text):
        counted = status(one, rows_of(one.slug, rows))
        go = _gone(kept.get(one.slug), text)
        go = f" | {go}" if go else ""
        said.append(f"{one.slug} | {_cut(one.line, LINE)} | {_cut(counted, STATUS)}{go}\n")
        if one.unknown:
            flags.append(
                f"{one.slug}: Stage {one.unknown} is no stage "
                f"({', '.join(stage.value for stage in Stage)}), so it is never briefed\n"
            )
    return "".join(flags + said)


def path(home: Path, scope: str | None) -> Path:
    """Return the plan of the root home, or of the scoped home `scope`. Refuse a plan that
    is not there."""
    if scope is not None and not _SCOPE.fullmatch(scope):
        raise Refused(f"refused: {scope} is not a scope")
    plan = (home / scope if scope else home) / "plan.md"
    if not plan.is_file():
        raise Refused(f"refused: no plan at {plan}")
    return plan


def close(plan: Path, slug: str, rows: list[queue.Row]) -> str:
    """Move the entry's section, as it is, from the plan to `plan-done.md` beside it.

    The section is the heading and every line up to the next `## ` heading. `close` refuses
    while a row of the entry is not over. It appends the section to `plan-done.md` before it
    rewrites the plan, so a move that stops between the two leaves the section in both files
    and loses no line.
    """
    lines = plan.read_text().splitlines(keepends=True)
    start = next((at for at, line in enumerate(lines) if line.startswith(f"## {slug}: ")), None)
    if start is None:
        raise Refused(f"refused: {plan} has no entry {slug}")
    still = [row for row in rows_of(slug, rows) if not queue.over(row)]
    if still:
        named = ", ".join(f"{row['slug']} ({row.get('status', 'queued')})" for row in still)
        raise Refused(f"refused: {slug} has rows that are not over: {named}")
    end = next((at for at in range(start + 1, len(lines)) if lines[at].startswith("## ")), None)
    section = "".join(lines[start:end])
    done = plan.with_name("plan-done.md")
    was = done.read_text() if done.is_file() else ""
    gap = "" if not was or was.endswith("\n\n") else "\n" if was.endswith("\n") else "\n\n"
    with open(done, "a") as kept:
        kept.write(gap + section)
    new = plan.with_name(f"{plan.name}.new")
    new.write_text("".join(lines[:start] + (lines[end:] if end is not None else [])))
    os.replace(new, plan)
    return f"closed {slug}: its section is in {done}"


def _plan(args: argparse.Namespace, config: Config) -> int:
    """`jbus plan`: show each entry of a home's plan with its status, counted from the queue
    now. `jbus plan close <entry>` moves a finished entry's section to `plan-done.md`.

    Every repo has the home skill, so with no `--project` the verb reads the plan of the repo
    it runs in, and refuses a repo the config does not name."""
    project = verbs.here(config, args.project)
    if not args.verb:
        print(listing(config, project, args.scope), end="")
        return 0
    where = path(config.home(project), args.scope)
    rows = _rows(config, project)
    home, state = config.home(project), config.state(project)
    scope = _scope(home, where.parent)
    if not args.entry:
        raise Refused(f"refused: {args.verb} needs an entry: jbus plan {args.verb} <entry>")
    if args.verb == "close":
        print(close(where, args.entry, rows))
        return 0
    if args.verb == "go":
        print("\n".join(go(config, state, home, where, args.entry, args.message, rows)))
        return 0
    if args.verb == "stop":
        print("\n".join(stop(config.user, state, home, scope, args.entry)))
    return 0


def _rows(config: Config, project: jbus.Project) -> list[queue.Row]:
    try:
        return queue.load(config.state(project))
    except queue.Unparsable as error:
        raise Refused(f"refused: {error}") from error


def listing(config: Config, project: jbus.Project, scope: str | None) -> str:
    """Return what `jbus plan` prints: a line for each entry of the plan of the root home, or of
    the scoped home `scope`, with its status. A home's start prints the same (`jbus.homestatus`)."""
    where = path(config.home(project), scope)
    home, state = config.home(project), config.state(project)
    mine = [one for one in goes(state) if one.scope == _scope(home, where.parent)]
    return shown(where.read_text(), _rows(config, project), mine) or f"no entry in {where}\n"


def go(
    config: Config,
    state: Path,
    home: Path,
    where: Path,
    entry: str,
    message: str,
    rows: list[queue.Row],
) -> list[str]:
    """Keep the user's message as the go of the entry, bound to its head now, and approve the
    rows of the entry that wait for a go. Refuse an entry the plan does not have, an entry with
    no queue row in any status, so no go is kept with nothing queued under it, and a message
    that is not the user's own (`t3.heard`)."""
    if not message:
        raise Refused("refused: go needs the user's word: --message <thread id>/<message id>")
    bound = head(where.read_text(), entry)
    if not bound:
        raise Refused(f"refused: {where} has no entry {entry}")
    if not rows_of(entry, rows):
        raise Refused(
            f"refused: {entry} has no queue row: queue its first row, a scout's if it needs "
            "design (--depends for what it waits on), then give the go"
        )
    heard = t3.heard(config, message)
    made = Go(
        entry,
        _scope(home, where.parent),
        bound,
        heard.ref,
        heard.words,
        heard.said_at,
        heard.said_in,
        queue.runner(),
        config.user.stamp(queue.clock()),
    )
    _kept(state, made)
    said = queue.Approval(
        queue.ENTRY, entry, heard.words, heard.said_at, heard.said_in, True, {}, ""
    )
    line = said.line().partition(";")[0]
    return [f"went {entry}: {line}", *queue.entered(state, config.user, entry_go(state, home))]


def stop(user: jsettings.Settings, state: Path, home: Path, scope: str, entry: str) -> list[str]:
    """Stop the go of the entry, and take back the go of each row of it that has not launched."""
    made = next((one for one in goes(state) if (one.scope, one.entry) == (scope, entry)), None)
    if made is None:
        raise Refused(f"refused: {entry} has no go to stop")
    by = queue.who(queue.runner())
    _kept(state, replace(made, stopped=f"{user.stamp(queue.clock())} by {by}"))
    return [f"stopped {entry}'s go", *queue.entered(state, user, entry_go(state, home))]


def _entered(half: Any) -> None:
    """Keep the entry rule on the table as a step of the pass, before any launch. A project
    where no entry was ever given a go has nothing to keep."""
    run = half.run
    if not (run.state / GOES).exists():
        return
    try:
        for line in queue.entered(run.state, run.user, entry_go(run.state, run.home)):
            run.say(f"queue {run.project.name}: {line}")
    except Refused:
        return


def owed(state: Path, home: Path, rows: list[queue.Row]) -> list[Go]:
    """Return each go that holds whose entry has rows and none live: its last row ended (a scout
    reported, a row merged) and nothing is queued for what is left. Each is an item of the one
    list that wakes the entry's home (`jbus.wakes`), and a thing its home has out
    (`jbus.children.out`). It leaves both on the entry's next row, or on `plan close`."""
    found = []
    for made in goes(state):
        try:
            text: str | None = (home / made.scope / "plan.md").read_text()
        except OSError:
            text = None
        mine = rows_of(made.entry, rows)
        if not why_not(made, text) and mine and all(queue.over(row) for row in mine):
            found.append(made)
    return found


def owed_key(made: Go) -> str:
    """The key of an owed entry on the one list: `owed <scope>/<entry>`, or `owed <entry>` for an
    entry of the root home's plan."""
    return _key("owed", made.scope, made.entry)


def _key(word: str, scope: str, entry: str) -> str:
    return f"{word} {scope}/{entry}" if scope else f"{word} {entry}"


@dataclass(frozen=True)
class Buildable:
    """An entry of the plan of `scope` (empty for the root home's) that is ready to brief: the
    rows or entries its `Builds on:` line names, `merged`, have all merged, and it has no row."""

    scope: str
    entry: str
    merged: tuple[str, ...]

    def key(self) -> str:
        """Its key on the one list: `brief <scope>/<entry>`, or `brief <entry>` for the root's."""
        return _key("brief", self.scope, self.entry)


def merged(slug: str, rows: list[queue.Row]) -> bool:
    """Return whether the row `slug` merged, or, where no row has that slug, whether the entry
    `slug` has rows, every one of them final and one merged."""
    named = [row for row in rows if row["slug"] == slug]
    if named:
        return named[0].get("status") == "merged"
    mine = [row.get("status") for row in rows_of(slug, rows)]
    return bool(mine) and all(word in work.FINAL for word in mine) and "merged" in mine


def buildable(home: Path, rows: list[queue.Row]) -> list[Buildable]:
    """Return each entry of the root home's plan and of each scope's that is ready to brief: it
    has a `Builds on:` line whose rows or entries have all merged, no row of its own (a scout's
    included), and a stage that is `buildable`: not parked, scouting (a scout is out for it) or
    unknown. Each is an item of the one list that wakes the entry's home (`jbus.wakes`), and it
    leaves the list on the entry's first row."""
    found = []
    for directory in [home, *(scope for scope, _, _ in homes.scopes(home))]:
        try:
            text = (directory / "plan.md").read_text()
        except OSError:
            continue
        for one in entries(text):
            if (
                one.builds_on
                and one.buildable
                and not rows_of(one.slug, rows)
                and all(merged(other, rows) for other in one.builds_on)
            ):
                scope = _scope(home, directory)
                found.append(Buildable(scope, one.slug, tuple(sorted(one.builds_on))))
    return found


STEPS = (verbs.Step("before-watch", 9, "plan.entered", _entered),)


def _planned(planned: argparse.ArgumentParser) -> None:
    planned.add_argument(
        "verb",
        nargs="?",
        choices=["close", "go", "stop"],
        help="close: move a finished entry out; go: keep the user's go for an entry, and every "
        "row filed under it is approved by it; stop: stop that go",
    )
    planned.add_argument("entry", nargs="?", help="the entry, by its slug")
    planned.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="with go: the user's own message in T3 Code that gives the entry its go"
        "; THREAD/last is the user's newest message there",
    )
    planned.add_argument("--scope", help="a scoped home's plan, in place of the root home's")


VERBS = (
    verbs.Verb(
        "plan",
        "each entry of the home's plan.md, its status counted from its queue rows",
        _planned,
        _plan,
    ),
)
