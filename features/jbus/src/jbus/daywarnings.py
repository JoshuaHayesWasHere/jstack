"""File the day's warnings row: one row a day per project, holding the warnings that the reviews
after the first found in pull requests that merged.

Josh's rule (2026-10-29): after the second review, fix errors in the pull request, file follow-ups
for medium and low, and ignore info, and a follow-up is small and reviewed only on its own work.
Josh, 2026-11-01, on how: "batch them into one follow-up row a day". So a later review's warning
holds no merge and goes to no crew: `jbriefs.findings` routes it `KEPT`, whatever its bucket or
tag, and this step keeps it once its pull request merged.

On each pass, `keep` reads the brief of each pull request that merged at or after `SINCE`, the
merge of #833 (636ac8b20), which dropped such a warning with no row: so the first row also holds
the warnings of every later review since then. A finding routed `KEPT` that the crew answered by
id anyway is not kept, and neither is one of a brief that says `Review: cleanup`, the day's row
itself, whose one review keeps nothing. `day-warnings.json` in the project's state keeps each
warning once, by its slug and id, with the local day this step first kept it.

Once a day has ended, `due` takes every kept warning of an earlier day that no row holds yet.
Where they are `BAR` or more, the step files them as one row, `warnings-<the latest of those
days>`, unapproved and as jbus's pass, and the next pass approves it by the follow-up rule
(`queue.filed`). Under `BAR`, it files nothing, and they carry to the next day's row: a thin day
neither launches a row nor loses a warning (the root home set the bar from the week audit's
replay, in which a bar of 3 launched 9 rows of 14). A day with no warning files nothing. Where the
queue refuses the row, its warnings stay kept for the next pass, and the refusal is a condition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jbriefs import findings
from jbriefs import home as homes
from jbus import Refused, mirror, queue, read_json, verbs, watch, write_json

if TYPE_CHECKING:
    from jbus.poll import Half

PREFIX = "warnings-"
BAR = 3
SINCE = datetime(2026, 11, 1, 2, 9, 9, tzinfo=UTC)
"""When #833 merged (636ac8b20), as GitHub gives its `mergedAt`."""
LEDGER = "day-warnings.json"


@dataclass(frozen=True)
class Kept:
    """One kept warning: the row whose pull request it was found in, its id there, its place,
    what it says, that pull request, and the day it was kept."""

    slug: str
    id: str
    place: str
    what: str
    pull: str
    day: str

    @property
    def key(self) -> str:
        return f"{self.slug}|{self.id}"

    @property
    def path(self) -> str:
        place = self.place.rpartition(":")[0] if ":" in self.place else self.place
        return place.strip("`")

    @property
    def line(self) -> str:
        """The warning's line of the row's `Done when:`. Its words are the reviewer's, so they are
        quoted: a quote is somebody's words, which `queue.asks` does not read as the brief's."""
        what = self.what.replace('"', "'")
        return f'- {self.slug} {self.id} warning {self.place}: "{what}" ({self.pull})'


def kept(slug: str, text: str, pull: str, day: str) -> list[Kept]:
    """Return the warnings of the brief `text` of `slug` that its day's row holds: each finding
    `findings.triage` routes `KEPT` that the crew did not answer by id, none of a `cleanup`
    brief."""
    said = findings.triage(text)
    if said.mode == findings.CLEANUP:
        return []
    return [
        Kept(slug, one.id, one.lead.place, one.lead.what, pull, day)
        for one in said.routed(findings.KEPT)
        if one.id not in said.answers
    ]


def due(ledger: dict[str, Any], today: str) -> tuple[str, list[Kept]] | None:
    """Return the day's row that is due, its day and its warnings: every kept warning of a day
    before `today` that no row holds, once they are `BAR` or more. None where none is due."""
    waiting = [
        Kept(**one)
        for key, one in sorted(ledger["kept"].items())
        if key not in ledger["filed"] and one["day"] < today
    ]
    if len(waiting) < BAR:
        return None
    return max(one.day for one in waiting), waiting


def brief(day: str, warnings: list[Kept]) -> str:
    """Return the day's warnings row's brief, in the shape of
    `features/jbriefs/templates/brief.md`, which `queue.add` takes whatever the warnings name.
    A warning on a shared doc, such as the README, makes the row a docs sweep, whose title names
    docs, since only a docs sweep may claim one (`queue.conduct`). A warning that names no file
    is of its pull request as a whole, so where no warning names a file `Where:` is the repo."""
    pulls = list(dict.fromkeys(one.pull for one in warnings))
    where = [path for path in dict.fromkeys(one.path for one in warnings) if path not in ("", "-")]
    days = sorted({one.day for one in warnings})
    span = days[0] if len(days) == 1 else f"{days[0]} to {days[-1]}"
    lines = [one.line for one in warnings]
    docs = any(queue.shared_doc(text) for text in [*lines, *(f"`{path}`" for path in where)])
    return "\n".join(
        [
            f"# {PREFIX}{day}: fix the warnings that later reviews found, kept {span}"
            + (", and the docs they name" if docs else ""),
            "Task: each warning below is a finding of a review after the first, of a pull request "
            "that has merged: it held no merge and went to no crew, and this row fixes it, as the "
            "one follow-up row of the day.",
            "Done when:",
            *lines,
            "- Each warning above is fixed, or the Result says why it stands, citing a path:line.",
            "- The check command (`$H/fresh-check`) passes.",
            "Proves it: CI's `check` job on the pull request, and a test for each warning fixed "
            "where one can be written.",
            "Size: S",
            f"Where: {', '.join(f'`{path}`' for path in where) or '`.`'}",
            f"Decisions: {findings.CLEANUP_DECIDED}kept {span}, in {len(pulls)} pull requests, "
            'and the user has not seen it (Josh, 2026-11-01: "batch them into one follow-up row '
            'a day")',
            "Design: none, each warning names its own fix",
            "Pull request: open one when done",
            f"Review: {findings.CLEANUP}",
            "Playbook: bug-fix",
            f"Home: {homes.ROOT}",
            "",
        ]
    )


def keep(half: Half) -> None:
    """Keep the warnings of each merged pull request, then file the day's row where one is due."""
    run, world = half.run, half.seen.world
    if world is None:
        return
    ledger: dict[str, Any] = read_json(run.state / LEDGER, {"kept": {}, "filed": {}})
    today = run.user.day(run.now)
    for slug, pull in sorted(world.merged.items()):
        if not pull.get("mergedAt") or watch.when(pull["mergedAt"]) < SINCE:
            continue
        path = run.home / "tasks" / f"{slug}.md"
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        url = pull.get("url") or watch.named(mirror.last_result(text) or "")[0]
        for one in kept(slug, text, url, today):
            ledger["kept"].setdefault(one.key, asdict(one))
    write_json(run.state / LEDGER, ledger)
    owed = due(ledger, today)
    if owed is None:
        return
    day, warnings = owed
    name = f"{PREFIX}{day}"
    if queue.fresh(run.state, name) is None:
        text = brief(day, warnings)
        (run.home / "tasks").mkdir(parents=True, exist_ok=True)
        (run.home / "tasks" / f"{name}.md").write_text(text)
        try:
            queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)
        except Refused as refused:
            run.condition(name, f"its brief was not queued: {refused}")
            return
    for one in warnings:
        ledger["filed"][one.key] = name
    write_json(run.state / LEDGER, ledger)
    line = f"retro {name}: filed {len(warnings)} warnings of later reviews, kept to {day}"
    run.find(name, "retro", line, key=f"warnings {name}", past=True)


STEPS = (verbs.Step("close", 55, "daywarnings.keep", keep, ("sight", "world")),)
