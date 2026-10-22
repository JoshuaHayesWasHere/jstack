"""`jbus plan`: read a home's plan, and join it with the queue at each read.

`plan.md` holds what the user decided: one section for each entry, `## <slug>: <one line>`,
with its "Done when" list and the user's words under `Decisions:`. It holds no status. An
entry is often several briefs, and each brief is a row of the queue that names its entry
(`queue.entry`). So `status` works out the progress of an entry's work from its rows at each
read, in the words of the row statuses. No model types the status, and nothing here writes
it down.

An entry with no row has only what the home wrote of it: its `Stage:` line, which says where
the planning is (`proposed`, `planned`, `parked` or `scouting`). A plan from before has
`Status:` lines, which someone typed. jbus ignores such a line where the entry has rows,
and shows it as typed where the entry has none.

An entry whose rows are all over (`queue.over`) is finished, and `close` moves its section,
as it is, to `plan-done.md` beside the plan. That is the only write in this module, and it
changes no line of the section. `plan.md` keeps the open entries only, so a home's start
reads the lines `shown` returns and not the file.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from jbus import Config, Refused, queue, verbs

LINE, STATUS = 56, 60
_ENTRY = re.compile(r"## (?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*): (?P<line>.+)")
_SCOPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class Entry:
    """An `Entry` is one `## <slug>: <one line>` section of a plan. `stage` is what its
    `Stage:` line says, and `typed` is the whole `Status:` line of a plan from before. Either
    may be empty."""

    slug: str
    line: str
    stage: str
    typed: str


def entries(text: str) -> list[Entry]:
    """Return the entries of a plan, in its order. A `## ` heading that is not
    `<slug>: <one line>` starts no entry, and ends the one above it."""
    found: list[Entry] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            heading = _ENTRY.fullmatch(line.rstrip())
            inside = heading is not None
            if heading:
                found.append(Entry(heading["slug"], heading["line"].strip(), "", ""))
        elif inside and line.startswith("Stage:") and not found[-1].stage:
            one = found[-1]
            found[-1] = Entry(one.slug, one.line, line.removeprefix("Stage:").strip(), one.typed)
        elif inside and line.startswith("Status:") and not found[-1].typed:
            one = found[-1]
            found[-1] = Entry(one.slug, one.line, one.stage, line.strip())
    return found


def rows_of(slug: str, rows: list[queue.Row]) -> list[queue.Row]:
    return [row for row in rows if queue.entry(row) == slug]


def status(entry: Entry, rows: list[queue.Row]) -> str:
    """Return the progress of the entry's work. `rows` are the rows of the entry.

    With rows, it counts them: the finished ones first, `4 of 7 merged`, then each open row
    that has a pull request, by its number, `#383 at pr`, then the rest by status,
    `1 queued not approved`. With every row over, it says to close the entry. With no rows, it
    returns the entry's stage, or its typed line, or `no stage`.
    """
    if not rows:
        if entry.stage:
            return entry.stage
        return f"(typed) {entry.typed}" if entry.typed else "no stage"
    done = [row for row in rows if queue.over(row)]
    if len(done) == len(rows):
        counted = "its row" if len(rows) == 1 else f"all {len(rows)} rows"
        return f"{counted} finished: close it"
    finished = Counter(row["status"] for row in done)
    parts = [f"{finished[name]} {name}" for name in queue.FINAL if finished[name]] or ["0 merged"]
    count, _, name = parts[0].partition(" ")
    parts[0] = f"{count} of {len(rows)} {name}"
    still = [row for row in rows if not queue.over(row)]
    pulls = sorted(
        (row for row in still if row.get("pr")), key=lambda row: (len(row["pr"]), row["pr"])
    )
    parts += [f"{row['pr']} at {row.get('status', 'queued')}" for row in pulls]
    rest: Counter[str] = Counter()
    for row in still:
        if row.get("pr"):
            continue
        word = row.get("status", "queued")
        if word == "queued" and not row.get("approved"):
            word = "queued not approved"
        elif word in queue.FINAL:
            word = f"{word} and waiting"
        rest[word] += 1
    for name in queue.STATUSES:
        for word in (name, f"{name} not approved", f"{name} and waiting"):
            if rest[word]:
                parts.append(f"{rest[word]} {word}")
    return ", ".join(parts)


def _cut(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: cap - 3].rstrip() + "..."


def shown(text: str, rows: list[queue.Row]) -> str:
    """Return one line for each entry of the plan: its slug, its one line and its status. It
    cuts each part short so that a plan of seventeen entries fits on one screen."""
    said = []
    for one in entries(text):
        counted = status(one, rows_of(one.slug, rows))
        said.append(f"{one.slug} | {_cut(one.line, LINE)} | {_cut(counted, STATUS)}\n")
    return "".join(said)


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
    where = path(config.home(project), args.scope)
    try:
        rows = queue.load(config.state(project))
    except queue.Unparsable as error:
        raise Refused(f"refused: {error}") from error
    if args.verb == "close":
        if not args.entry:
            raise Refused("refused: close needs an entry: jbus plan close <entry>")
        print(close(where, args.entry, rows))
        return 0
    print(shown(where.read_text(), rows) or f"no entry in {where}\n", end="")
    return 0


def _planned(planned: argparse.ArgumentParser) -> None:
    planned.add_argument("verb", nargs="?", choices=["close"], help="move a finished entry out")
    planned.add_argument("entry", nargs="?", help="the entry to close, by its slug")
    planned.add_argument("--scope", help="a scoped home's plan, in place of the root home's")


VERBS = (
    verbs.Verb(
        "plan",
        "each entry of the home's plan.md, its status counted from its queue rows",
        _planned,
        _plan,
    ),
)
