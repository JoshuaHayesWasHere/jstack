"""This module restates a row's line of `work.json` as each writer of that row's inputs writes, so
the view shows a change within milliseconds and not at the next pass (`jbus.work`).

A write of the queue restates the `Row` facet of each row it reaches (`queued`, from
`queue._changing`), and a run of `jmerge`, the tick's or the pass's, restates the `Pull` facet
and the `why` of each pull request it judged (`pulled`, from `merge._sent`), each judged again
from the facts the last pass kept (`work.restate`). The pass still judges every row: it keeps a
`Pull` facet that a later run of `jmerge` restated (`kept`), and logs each line it corrects as
drift (`drift`, from `states.keep_work`). Every writer holds `work.LOCK`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jbus import locked, write_json
from jbus.work import (
    APPROVED,
    LOCK,
    Answered,
    Facts,
    Launch,
    Pull,
    Question,
    Row,
    Thread,
    Written,
    entry,
    holder,
    judge,
    path,
    read,
    restate,
    scouting,
    stored,
)

SEEN = ("thread", "pr")
"""The columns of a row of the queue that a new row's line carries as they are (`fresh`)."""
PULLED = "pulled"
"""The field of a line that says when a run of `jmerge` last restated its `Pull` facet."""


def _rewrite(state_dir: Path, change: Callable[[list[Any]], list[Any]]) -> None:
    """Rewrite the lines of `work.json` with what `change` makes of them, under `LOCK`, and
    write nothing where nothing changed. A file that no pass wrote yet is left as it is."""
    with locked(state_dir, LOCK):
        kept = read(state_dir)
        if kept is None:
            return
        work = change(kept["work"])
        if work != kept["work"]:
            write_json(path(state_dir), {**kept, "work": work})


def _is_row(one: Any) -> bool:
    return isinstance(one, dict) and one.get("kind") == "row" and isinstance(one.get("key"), str)


def queued(
    state_dir: Path,
    rows: list[dict[str, Any]],
    facet: Callable[[dict[str, Any]], Row],
    scout: Callable[[dict[str, Any]], bool],
    moved: set[str],
) -> None:
    """Restate the line of `work.json` of each row of `moved` from the queue as it is now: the
    `Row` facet that `facet` gives the row. A row the queue no longer has loses its line, and a
    row with no line yet gets one judged with nothing launched, written or open (`fresh`), which
    the next pass judges in full. Each write of the queue calls this under the queue's lock once
    it wrote (`queue._changing`), so the view shows a change of the queue at once."""
    by_slug = {row["slug"]: row for row in rows}

    def change(lines: list[Any]) -> list[Any]:
        work, had = [], set()
        for one in lines:
            if _is_row(one):
                row = by_slug.get(one["key"])
                if row is None:
                    continue
                had.add(one["key"])
                if one["key"] not in moved:
                    work.append(one)
                    continue
                one = restate(one, row=facet(row))
            work.append(one)
        at = max((n for n, one in enumerate(work) if _is_row(one)), default=-1) + 1
        work[at:at] = [fresh(row, facet(row), scout(row)) for row in rows if row["slug"] not in had]
        return work

    _rewrite(state_dir, change)


def fresh(row: dict[str, Any], facet: Row, scout: bool) -> dict[str, Any]:
    """Return the line of a row that no pass judged yet: nothing launched, written or open."""
    facts = Facts(
        facet, Thread.NONE, Launch.NONE, Written.NONE, Pull.NONE, Question.NONE, Answered.BOTH
    )
    state = judge(facts)
    slug = row["slug"]
    about = {"key": slug, "kind": "row", "slug": slug, **{name: row.get(name, "") for name in SEEN}}
    said = {"scout": str(scouting(state))} if scout else {}
    return entry(state, holder(state, role="scout" if scout else ""), **about, **said)


def pulled(state_dir: Path, said: dict[int, tuple[Pull, str]], at: str) -> None:
    """Restate the `Pull` facet of the line of each pull request that a run of `jmerge` judged,
    by its number, as `jmerge` judged it, with its reason as the line's `why`, and mark the line
    `PULLED` at `at`, when the run ended (`Said.at`). The pass and the merge tick both call this
    as their run of `jmerge` ends (`merge._sent`), so a verdict reaches the view at once. The
    pass keeps a facet that a run after its own restated (`kept`)."""
    if not said:
        return

    def change(lines: list[Any]) -> list[Any]:
        work = []
        for one in lines:
            number = str(one.get("pr", "")).removeprefix("#") if _is_row(one) else ""
            if number.isdigit() and int(number) in said:
                pull, why = said[int(number)]
                made = restate(one, pull=pull, why=why)
                if made is not one:
                    one = {**made, PULLED: at}
            work.append(one)
        return work

    _rewrite(state_dir, change)


def kept(one: dict[str, Any], was: dict[str, Any] | None, ran: str) -> dict[str, Any]:
    """Return the pass's line `one`, with the `Pull` facet of the file's line `was` where a run of
    `jmerge` that ended after `ran`, when the pass's own run ended, restated it: a merge tick's
    run judged later than the pass's own run, whose verdict the pass's line holds."""
    facts = stored(was) if was is not None and str(was.get(PULLED, "")) > ran else None
    if facts is None or was is None:
        return one
    return {**restate(one, pull=facts.pull), PULLED: was[PULLED]}


def drift(before: list[Any], after: list[Any]) -> list[tuple[str, str]]:
    """Return each row's line that the pass corrects and that a writer should have kept right, by
    key, with what was wrong in it: a line for a row the queue no longer has, no line for a row it
    has, a `Row` facet the queue gave otherwise (a move between `APPROVED` facets is the pass's to
    judge, as `restate` says), a `Pull` facet that a run of `jmerge` restated (`PULLED`) and that
    the pass, with GitHub's answer, judges otherwise for the same pull request, or a value that does
    not follow from the line's own facts, which no writer restates since its facts are right.

    The facets the pass alone sees, a thread's and what was written, and a pull request no run of
    `jmerge` restated on the line yet, are no drift. The writers run in the pass too, before it
    writes, so a facet broken in the file is most often put right by one of them first, and the
    pass then finds nothing of it to correct."""
    was = {one["key"]: one for one in before if _is_row(one)}
    now = {one["key"]: one for one in after if _is_row(one)}
    found = []
    for key in sorted(was.keys() | now.keys()):
        old, new = was.get(key), now.get(key)
        if old is None:
            found.append((key, "no line"))
        elif new is None:
            found.append((key, "a line for a row the queue does not have"))
        elif off := _off(old, new):
            found.append((key, ", ".join(off)))
    return found


def _off(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    facts = (old.get("facts") or {}, new.get("facts") or {})
    rows = (facts[0].get("row"), facts[1].get("row"))
    pulls = (facts[0].get("pull"), facts[1].get("pull"))
    off = []
    if rows[0] != rows[1] and not set(rows) <= set(APPROVED):
        off.append(f"row {rows[0]!r} for {rows[1]!r}")
    heard = facts[1].get("answered") in (Answered.BOTH, Answered.GITHUB)
    if pulls[0] != pulls[1] and PULLED in old and old.get("pr") == new.get("pr") and heard:
        off.append(f"pull {pulls[0]!r} for {pulls[1]!r}")
    if facts[0] == facts[1] and old.get("value") != new.get("value"):
        off.append(f"value {old.get('value')!r} for {new.get('value')!r}")
    return off


def moment(at: datetime) -> str:
    """Return `at` as `PULLED` keeps it: in UTC to the microsecond, so stamps compare as text."""
    return at.astimezone(UTC).isoformat(timespec="microseconds")
