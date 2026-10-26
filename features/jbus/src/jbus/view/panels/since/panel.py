"""What happened since the user last looked: the line at the top of `#/` that says, say, "3
merged, 1 newly stuck, 1 default taken".

The server does not know when the user looked, and is never told. It gives `/stack.json` a list
of what happened over the last `KEEP`, each with its kind, its subject, its project, when and
the drawer that has it, oldest first. The page keeps one number of its own, the last time the
user had it in view, and counts each entry after that time. That number is the only thing it
keeps, in the browser's own storage, and it holds no content.

The kinds are `merged`, a row that moved to merged (as the panel `merged` reads it, over
`KEEP` and not only today); `stuck`, a stall or an idle crew that stands now, from the
project's list of what is wrong (`state.wrongs`), since its first stall after the row last
moved (`_began`); and `default`, a question
that jbus closed with its default, since nobody answered it in 2 hours. A stuck row that moved
again is no longer stuck, so it is not on the list: the line says what stands, not what was."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import quote

from jbus import questions
from jbus.view.state import (
    EVENTS_FILE,
    MERGE_LOG,
    MOVES_FILE,
    QUEUE_FILE,
    STALLED,
    Read,
    iso,
    kept,
    text,
    when,
    wrongs,
)

FIRST = False
KEEP = timedelta(days=7)
"""How far back the list goes. A visit longer ago than that counts from `from`."""
EVENT = {key: None for key in ("kind", "subj", "project", "at", "open")}
SHAPE = {"since": {"from": None, "events": [EVENT]}}
STUCK = ("stall", "idle")
"""The kinds of `state.wrongs` that are a row that does not move: the map flags the same two."""


def _asked(read: Read) -> list[questions.Question] | None:
    try:
        return questions.read(read.state) if read.name else None
    except questions.Unparsable:
        return None


SOURCES = (
    QUEUE_FILE,
    MOVES_FILE,
    EVENTS_FILE,
    MERGE_LOG,
    kept(questions.NAME, lambda read: read.once(_asked), 80),
)


def _open(read: Read, route: str) -> str:
    return f"#/{quote(read.name, safe='')}/{route}"


def _event(read: Read, kind: str, subj: str, at: str, route: str) -> dict[str, Any]:
    return {"kind": kind, "subj": subj, "project": read.name, "at": at, "open": _open(read, route)}


def _merged(read: Read, start: str) -> list[dict[str, Any]]:
    """Each row that merged at `start` or after: a move to merged in the queue, or a row that
    `merge.log` records as merged while the queue says another state."""
    found: dict[str, str] = {}
    for move in read.moves or []:
        slug, at = text(move.get("slug"), 80), when(move.get("at"))
        if move.get("to") == "merged" and at and at >= start:
            found[slug] = max(found.get(slug, ""), at)
    for one in read.ended:
        at = one["since"] if one["state"]["kind"] == "merged" else None
        if at and at >= start and one["slug"] not in found:
            found[one["slug"]] = at
    return [_event(read, "merged", slug, at, "merged") for slug, at in found.items()]


def _began(read: Read) -> dict[str, str]:
    """When each row's stuck run began: the first stall jbus logged of it since the row last
    moved. jbus logs a stall again while it stands, and the list of what is wrong keeps the last
    one, which would make a row that has been stuck for an hour look newly stuck."""
    moved: dict[str, str] = {}
    for move in read.moves or []:
        slug, at = text(move.get("slug"), 80), when(move.get("at"))
        if at:
            moved[slug] = max(moved.get(slug, ""), at)
    began: dict[str, str] = {}
    for one in read.events:
        slug = one["slug"]
        if one["kind"] == STALLED and one["at"] > moved.get(slug, "") and slug not in began:
            began[slug] = one["at"]
    return began


def _stuck(read: Read) -> list[dict[str, Any]]:
    began = _began(read)
    return [
        {"kind": "stuck", "subj": one["subj"], "project": read.name}
        | {"at": min(one["since"], began.get(one["subj"], one["since"]))}
        | {"open": one["where"][0]["open"]}
        for one in read.once(wrongs)
        if one["kind"] in STUCK and one["since"]
    ]


def _defaults(read: Read, start: str) -> list[dict[str, Any]]:
    found = []
    for one in read.once(_asked) or []:
        said = one.answer
        at = when(said.at) if said and said.closed_by == questions.SILENCE else None
        if at and at >= start:
            subj = text(one.slug, 80) or f"question {one.number}"
            found.append(_event(read, "default", subj, at, "words"))
    return found


def happened(read: Read) -> list[dict[str, Any]]:
    """What happened in the project over the last `KEEP`, of each kind."""
    start = iso(read.now - KEEP)
    return _merged(read, start) + _stuck(read) + _defaults(read, start)


def _since(base: Read, events: list[dict[str, Any]]) -> dict[str, Any]:
    order = sorted(events, key=lambda one: (one["at"], one["project"], one["kind"], one["subj"]))
    return {"since": {"from": iso(base.now - KEEP), "events": order}}


def stack(base: Read, reads: list[Read], answer: dict[str, Any]) -> dict[str, Any]:
    return _since(base, [one for read in reads for one in happened(read)])


def build(read: Read) -> dict[str, Any]:
    return _since(read, happened(read))
