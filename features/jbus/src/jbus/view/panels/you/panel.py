"""What waits on the user: the list the last pass left, with the gates as they are now, and every
gate of the home's `gates.md` that jbus does not hold as a question.

From that list the panel builds the page's two queues, as closed records (`_NEED`), in a person's
words and with no command line in them. `needs` is what only the user can move and nothing else
will: a gate that holds (`Holds:`) or has no default, an approval, a held merge, a row at a gate,
a leftover, a setup. `proceeds` is a gate whose default is already taken. It closes with that
default after 2 hours of silence (`questions.QUIET`), or, for a gate of a home's `gates.md`,
stands as it is. A link's conflict asks its home and not the user, so it is on neither queue.

A proposed work item is a need too, of the kind `ITEM`, which the user approves by its id on the
page (`_items`). Its `item` and the line it was last `seen` at go with it, as a steer names them,
and every other need has those two empty. A proposed item whose row waits for its approval is
left to that row, since a go by the item's id is no go of the row. But the user can approve a row
whose item was redirected only by the item's id (`jbus.steer.approvable`), so the item's need
then replaces the row's."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jbus import item, merge, mirror, questions, queue, waiting
from jbus.view.state import (
    _SLUG,
    WAITING_FILE,
    WORDS,
    Read,
    Source,
    _mtime,
    asker,
    iso,
    oldest,
    text,
    when,
)

FIRST = True
_WAITS = {
    key: None
    for key in (
        "kind",
        "key",
        "line",
        "since",
        "slug",
        "number",
        "question",
        "default",
        "home",
        "url",
    )
} | {
    "unblocks": [None],
    "answerable": None,
    "context": None,
    "built_on": None,
    "undo": None,
    "thread": None,
    "role": None,
    "options": [{"name": None, "follows": None, "default": None, "recommended": None}],
}
_GATE = {
    key: None for key in ("number", "question", "open", "status", "default", "built_on", "home")
}
_NEED = {
    key: None
    for key in (
        "project",
        "kind",
        "key",
        "what",
        "why",
        "since",
        "verb",
        "default",
        "risk",
        "open",
        "due",
        "item",
        "seen",
    )
} | {"answerable": None, "unblocks": [None]}
SHAPE = {"waiting": [_WAITS], "gates": [_GATE], "needs": [_NEED], "proceeds": [_NEED]}
ANSWER = "Answer"
REVERSIBLE, MERGES = "reversible", "merge to main"
NEEDS, PROCEEDS = "needs", "proceeds"
ITEM, APPROVE = "item", "Approve"
LINE = 200
WHY = 60
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")
SOURCES = (
    WAITING_FILE,
    Source("gates.md", "server", lambda read: {"at": _mtime(read.home / "gates.md")}, 140),
)


def _gates(state: Path, home: Path) -> list[dict[str, Any]]:
    """Every gate of the home's `gates.md` and of each scoped home's, open or not, except one
    that jbus holds as a question, which is on the waiting list while it is open. The panel also
    leaves out a gate whose slug was removed from the queue."""
    held = {one.key for one in questions.load(state)}
    gone = queue.removed_slugs(state)
    found = []
    for file, number, asked, body, key in mirror.home_gates(home):
        status = mirror.field(body, "Status")
        if key in held or mirror.asker(body) in gone:
            continue
        found.append(
            {
                "number": text(number, 20),
                "question": text(asked),
                "open": status.startswith("open"),
                "status": text(status),
                "default": text(mirror.field(body, "Default"), 600),
                "built_on": text(mirror.field(body, "Built on it")),
                "home": "" if file.parent == home else text(file.parent.name, 60),
            }
        )
    return found


def _question(one: questions.Question | None, home: Path, threads: Any) -> dict[str, Any]:
    """What an item of the list has of the question jbus holds for it: whether the user can
    answer it on the page, what the gate wrote, and who asked. An item that is not one of jbus's
    questions, such as a gate of a home's `gates.md`, has all three empty."""
    thread, role = asker(home, one.slug, threads) if one else ("", "")
    return {
        "answerable": one is not None,
        "context": text(one.context, WORDS) if one else "",
        "built_on": text(one.built_on, WORDS) if one else "",
        "undo": text(one.undo, WORDS) if one else "",
        "thread": text(thread, 80),
        "role": role,
        "options": [
            {
                "name": text(each.name),
                "follows": text(each.follows, WORDS),
                "default": each.default,
                "recommended": each.recommended,
            }
            for each in (one.options if one else ())
        ],
    }


def _waiting(
    state: Path, home: Path, left: list[Any] | None, words: dict[str, str], threads: Any = None
) -> list[dict[str, Any]]:
    """The list of what waits on the user, as the last pass left it, with the gates as they are
    now in jbus's questions and in `gates.md`. A gate keeps the `since` that the pass gave it, a
    new question has the time it was asked, and a new gate of a file has no time. A leftover of a
    task that ended has its task's words (`words`), not the pass's. A question that jbus holds
    has what the page needs to answer it (`_question`)."""
    kept = [one for one in left or [] if one["kind"] in waiting.kinds()]
    since = {one["key"]: one.get("since") for one in kept}
    asked = questions.load(state)
    held = {str(one.number): one for one in asked}
    try:
        live = waiting.gates(home, asked, queue.removed_slugs(state))
    except OSError:
        live = []
    listed = [one for one in kept if one["kind"] != "gate"] + [
        one | {"since": since.get(one["key"]) or one.get("since")} for one in live
    ]
    return [
        {
            "kind": one["kind"],
            "key": text(one.get("key"), 120),
            "line": words.get(text(one.get("slug"), 80), text(one.get("line")))
            if one["kind"] == "left"
            else text(one.get("line")),
            "since": when(one.get("since")),
            "slug": text(one.get("slug"), 80),
            "number": text(str(one.get("number") or ""), 20),
            "question": text(one.get("question")),
            "default": text(one.get("default"), 600),
            "home": text(one.get("home"), 60),
            "url": text(one.get("url")),
            "unblocks": [
                text(slug, 80) for slug in one.get("unblocks") or [] if isinstance(slug, str)
            ]
            if isinstance(one.get("unblocks"), list)
            else [],
        }
        | _question(
            held.get(str(one.get("number"))) if questions.listed(one) else None, home, threads
        )
        for one in sorted(listed, key=lambda one: waiting.kinds().index(one["kind"]))
    ]


def _cut(given: str, cap: int = LINE) -> str:
    """A line of words, cut between two of them where it is long."""
    given = " ".join(given.split())
    if len(given) <= cap:
        return given
    return given[:cap].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _brief(read: Read, slug: str) -> tuple[str, str]:
    """The title line of the brief that `slug` has in the project's `briefs/`, and the first
    sentence of its `Task:` line, both empty where there is no such brief."""
    try:
        brief = queue.brief(read.state, slug) if _SLUG.fullmatch(slug) else None
    except ValueError:
        brief = None
    title = task = ""
    for line in (brief or "").splitlines():
        if not title and line.startswith("# "):
            title = line[2:]
        elif not task and line.startswith("Task:"):
            task = _SENTENCE.split(line.removeprefix("Task:").strip(), maxsplit=1)[0]
    return _cut(title), _cut(task)


def _after(line: str, slug: str) -> str:
    """What a line says after the slug it names, as `left <slug>: why` says `why`."""
    mark = f"{slug}: "
    at = line.find(mark) if slug else -1
    return line[at + len(mark) :] if 0 <= at <= 12 else line


def _tier(waits: dict[str, Any], one: questions.Question | None) -> str | None:
    """Which queue an item is on: `needs`, `proceeds`, or None for one that asks the user
    nothing. Only a gate has a default to go ahead on. A question that jbus holds closes after
    silence unless it holds for the answer. A gate of a home's file has no timer, and goes ahead
    on its default where it has one."""
    if waits["kind"] != "gate":
        return NEEDS
    if one is None:
        return PROCEEDS if waits["default"].strip() else NEEDS
    if one.question.endswith(questions.LINK):
        return None
    return NEEDS if one.holds else PROCEEDS


def _route(project: str, waits: dict[str, Any], slug: str) -> str:
    """The hash route of the drawer that shows an item in full: the gate's own route for a
    question that jbus holds, and for any other item the list of its kind, opened at the item."""
    here = quote(project, safe="")
    if waits["answerable"]:
        return f"#/{here}/gate/{quote(waits['number'], safe='')}"
    named = waits["number"] if waits["kind"] in ("gate", "hold") else slug
    return f"#/{here}/you/{waits['kind']}" + (f"/{quote(named, safe='')}" if named else "")


def _need(
    read: Read,
    waits: dict[str, Any],
    one: questions.Question | None,
    slugs: dict[str, str],
    tier: str,
) -> dict[str, Any]:
    """One item as the page draws it: what it is and why in words, the one verb that moves
    it, what it risks, what it unblocks and where it opens."""
    kind, slug = waits["kind"], waits["slug"]
    if kind == "hold":
        slug = slugs.get(waits["number"], "")
    elif kind in ("approve", "row", "left"):
        slug = slug or waits["key"].rpartition(":")[2]
    title, task = _brief(read, slug)
    line = _after(waits["line"], waits["slug"])
    default = waits["default"]
    if kind == "gate":
        what, why = waits["question"], _cut(waits["context"])
    elif kind == "approve":
        what, why = title or slug, task
    elif kind == "hold":
        said = merge.parse(waits["line"])
        number = f"#{waits['number']}"
        what = f"Pull request {number}" + (f": {title}" if title else "")
        why = _cut(said.reason if said and said.reason else "waits for your word")
        default = ""
    else:
        what = title or (slug if kind == "left" else "") or line
        why = line if what != line else ""
    accepts = bool(waits["answerable"] and one is not None and not one.holds)
    depends = [
        task["slug"]
        for task in read.tasks
        if slug and any(each["slug"] == slug for each in task["depends"])
    ]
    due = None
    if one is not None and tier == PROCEEDS:
        due = iso(datetime.fromisoformat(one.asked_at) + questions.QUIET)
    return {
        "project": read.name,
        "kind": kind,
        "key": waits["key"],
        "what": _cut(what, 100),
        "why": _cut(why, WHY),
        "since": waits["since"],
        "verb": ANSWER if kind == "gate" and not accepts else waiting.verb(kind),
        "answerable": waits["answerable"],
        "default": _cut(default, 600),
        "risk": MERGES if kind == "hold" else (one.holds if one and one.holds else REVERSIBLE),
        "unblocks": list(dict.fromkeys([*waits["unblocks"], *depends])),
        "open": _route(read.name, waits, slug),
        "due": due,
        "item": "",
        "seen": "",
    }


def _approves(waits: dict[str, Any]) -> str:
    """The slug of the row that a need of the kind `approve` asks a go for, or nothing for any
    other need."""
    return (waits["slug"] or waits["key"].rpartition(":")[2]) if waits["kind"] == "approve" else ""


def _items(read: Read, found: dict[str, item.Item], rows: set[str]) -> list[dict[str, Any]]:
    """A need for each proposed item that only its id can approve: one whose row does not wait
    for a go, such as one with no row, and one that was redirected."""
    lines = item.read(read.state)
    made = []
    for one in found.values():
        if one.state is not item.State.PROPOSED or (one.slug in rows and not one.redirect):
            continue
        first = next(line for line in lines if line.get("item") == one.id)
        review = item.judged(read.state, one).risk is item.Risk.REVIEW
        redirected = f", redirected at {one.redirect}" if one.redirect else ""
        made.append(
            {
                "project": read.name,
                "kind": ITEM,
                "key": f"{ITEM}:{one.id}",
                "what": _cut(text(one.title) or one.slug or one.id, 100),
                "why": _cut(f"{one.id}, proposed in {one.source}{redirected}", WHY),
                "since": when(first.get("at")),
                "verb": APPROVE,
                "answerable": False,
                "default": "",
                "risk": str(item.Risk.REVIEW) if review else REVERSIBLE,
                "unblocks": [],
                "open": f"#/{quote(read.name, safe='')}/{ITEM}/{quote(one.id, safe='')}",
                "due": None,
                "item": one.id,
                "seen": one.last_event,
            }
        )
    return made


def _needs(read: Read, waits: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
    """The two queues of the page: what only the user can move, oldest first, and the gates
    that go ahead on their default, soonest first."""
    asked = {str(one.number): one for one in questions.load(read.state)}
    slugs = {task["pr"].removeprefix("#"): task["slug"] for task in read.tasks if task["pr"]}
    queues: dict[str, list[dict[str, Any]]] = {NEEDS: [], PROCEEDS: []}
    found = item.items(read.state)
    redirected = {one.slug for one in found.values() if one.slug and one.redirect}
    for one in waits:
        if _approves(one) in redirected:
            continue
        held = asked.get(one["number"]) if one["answerable"] else None
        tier = _tier(one, held)
        if tier:
            queues[tier].append(_need(read, one, held, slugs, tier))
    rows = {_approves(one) for one in waits} - {""}
    needs = oldest([*queues[NEEDS], *_items(read, found, rows)])
    return needs, sorted(queues[PROCEEDS], key=lambda one: one["due"] or "~")


def build(read: Read) -> dict[str, Any]:
    if not read.name:
        return {"waiting": [], "gates": [], "needs": [], "proceeds": []}
    words = {
        one["slug"]: one["state"]["say"]
        for one in read.tasks
        if one["state"]["kind"] in ("leftover", "closed")
    }
    waits = _waiting(read.state, read.home, read.left, words, read.mine.get("threads"))
    needs, proceeds = _needs(read, waits)
    return {
        "waiting": waits,
        "gates": _gates(read.state, read.home),
        "needs": needs,
        "proceeds": proceeds,
    }
