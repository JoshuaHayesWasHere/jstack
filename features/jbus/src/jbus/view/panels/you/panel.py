"""What waits on the user: the list the last pass left, with the gates as they are now, and every
gate of the home's `gates.md` that jbus does not hold as a question.

The panel builds the page's two queues, as closed records (`_NEED`), in a person's words and with
no command line in them. `needs` is what only the user can move and nothing else will. Of work,
that is every line of `work.json` whose holder is the user, a row's or a thread's, with what
holds it and since when it is in that state: a row at a gate, one to approve, a held merge, a
leftover, a closed pull request, a hung turn, a thread that waits on a request, and a thread
that is gone. The pass judged each line once (`jbus.work`), so the list of what waits on the
user is no second source for work: an item of it that names a row (`ROWS`) is no need by
itself, and only lends its route and what it unblocks to the row's need. Of that list, `needs`
has the rest: a gate that holds (`Holds:`) or has no default, and a setup. `proceeds` is a gate
whose default is already taken. It closes with that default after 2 hours of silence
(`questions.QUIET`). A gate of a home's `gates.md` instead stands as it is. A link's conflict
is a question for its home, not for the user, so it is on neither queue.

A proposed work item is a need too, of the kind `ITEM`, which the user approves by its id on the
page (`_items`). The need carries the two things a steer names: its `item`, and the line it was
last `seen` at. Every other need has those two empty. Each need names the task it is about, its
`slug`, or none, so the page draws that task once. Where a proposed item's row waits for its
approval, the panel leaves the item to that row. A go by the item's id is no go of the row. But
for a row whose item was redirected, the item's id is the only thing that approves it
(`jbus.steer.approvable`). So the item's need then takes the row's place."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jbus import item, mirror, questions, queue, waiting
from jbus.view.state import (
    _SLUG,
    LOST,
    SAYS,
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
        "slug",
    )
} | {"answerable": None, "unblocks": [None]}
SHAPE = {"waiting": [_WAITS], "gates": [_GATE], "needs": [_NEED], "proceeds": [_NEED]}
ANSWER = "Answer"
REVERSIBLE, MERGES = "reversible", "merge to main"
NEEDS, PROCEEDS = "needs", "proceeds"
ITEM, APPROVE = "item", "Approve"
LINE = 200
WHY = 60
USER = "user"
KIND_OF = {
    "asking": "row",
    "unapproved": "approve",
    "hold": "hold",
    "leftover": "left",
    "closed": "left",
}
"""The kind of the list of what waits on the user that names a row in each value of `work.json`.
A need of such a row has its kind's verb. A value with no kind, such as `hung`, is its own kind,
and its need opens the task."""
ROWS = frozenset(KIND_OF.values())
LOOK = "Look at it"
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


def _title(read: Read, slug: str) -> str:
    """The title line of the brief that `slug` has in the project's `briefs/`, empty where
    there is no such brief."""
    try:
        brief = queue.brief(read.state, slug) if _SLUG.fullmatch(slug) else None
    except ValueError:
        brief = None
    titled = (line[2:] for line in (brief or "").splitlines() if line.startswith("# "))
    return _cut(next(titled, ""))


def _after(line: str, slug: str) -> str:
    """What a line says after the slug it names, as `left <slug>: why` says `why`."""
    mark = f"{slug}: "
    at = line.find(mark) if slug else -1
    return line[at + len(mark) :] if 0 <= at <= 12 else line


def _tier(waits: dict[str, Any], one: questions.Question | None) -> str | None:
    """Which queue an item is on: `needs`, `proceeds`, or None for one that asks the user
    nothing. Only a gate has a default to go ahead on. A question that jbus holds closes when the
    user stays silent, unless its gate has a `Holds:` line. A gate of a home's file has no timer,
    and goes ahead on its default where it has one."""
    if waits["kind"] != "gate":
        return NEEDS
    if one is None:
        return PROCEEDS if waits["default"].strip() else NEEDS
    if one.question.endswith(questions.LINK):
        return None
    return NEEDS if one.holds else PROCEEDS


def _route(project: str, waits: dict[str, Any], slug: str) -> str:
    """The hash route of the drawer that shows an item in full. For a question that jbus holds,
    it is the gate's own route. For any other item, it is the list of the item's kind, opened at
    the item."""
    here = quote(project, safe="")
    if waits["answerable"]:
        return f"#/{here}/gate/{quote(waits['number'], safe='')}"
    named = waits["number"] if waits["kind"] in ("gate", "hold") else slug
    return f"#/{here}/you/{waits['kind']}" + (f"/{quote(named, safe='')}" if named else "")


def _need(
    read: Read, waits: dict[str, Any], one: questions.Question | None, tier: str
) -> dict[str, Any]:
    """One item of the list that names no row, as the page draws it: what it is and why in
    words, the one verb that moves it, what it risks, what it unblocks and where it opens."""
    kind, slug = waits["kind"], waits["slug"]
    line = _after(waits["line"], slug)
    if kind == "gate":
        what, why = waits["question"], _cut(waits["context"])
    else:
        what, why = line, ""
    accepts = bool(waits["answerable"] and one is not None and not one.holds)
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
        "default": _cut(waits["default"], 600),
        "risk": one.holds if one and one.holds else REVERSIBLE,
        "unblocks": waits["unblocks"],
        "open": _route(read.name, waits, slug),
        "due": due,
        "item": "",
        "seen": "",
        "slug": slug,
    }


def _approves(need: dict[str, Any]) -> str:
    """For a need of the kind `approve`, the slug of a row: the need asks the user's go for
    that row. For any other need, nothing."""
    return need["key"].partition(":")[2] if need["kind"] == "approve" else ""


def _items(read: Read, found: dict[str, item.Item], rows: set[str]) -> list[dict[str, Any]]:
    """A need for each proposed item that the user can approve only by its id. Such an item is
    one whose row does not wait for a go, such as one with no row, or one that was redirected."""
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
                "slug": one.slug or "",
            }
        )
    return made


def _work(read: Read, value: str, slug: str, listed: dict[str, Any] | None) -> dict[str, Any]:
    """What a need of work has that its kind gives: its kind, verb, risk and route. A row
    that the list of what waits on the user names opens that item's drawer."""
    kind = KIND_OF.get(value, value)
    here = quote(read.name, safe="")
    return {
        "kind": kind,
        "verb": waiting.verb(kind) if kind in ROWS else LOOK,
        "risk": MERGES if kind == "hold" else REVERSIBLE,
        "open": _route(read.name, listed, slug)
        if listed
        else f"#/{here}/task/{quote(slug, safe='')}",
        "answerable": False,
        "default": "",
        "due": None,
        "item": "",
        "seen": "",
        "slug": slug,
    }


def _rows(read: Read, listed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """A need for each row of `work.json` whose holder is the user: what it is, what holds it,
    and since when it is in that state, as the task has it. Where the task keeps no time, the
    need has the time of the item of the list that names the row, if there is one."""
    made = []
    for task in read.tasks:
        if task["who"] != USER:
            continue
        slug, value, said = task["slug"], task["state"]["kind"], task["state"]["say"]
        kind = KIND_OF.get(value, value)
        key = task["pr"] if kind == "hold" and task["pr"] else f"{kind}:{slug}"
        title = _title(read, slug)
        said = said or task["state"]["waits"]
        what = title or (said if kind == "row" else slug)
        if kind == "hold":
            what = f"Pull request {task['pr']}" + (f": {title}" if title else "")
        one = listed.get(key)
        depends = [
            other["slug"]
            for other in read.tasks
            if any(each["slug"] == slug for each in other["depends"])
        ]
        made.append(
            {
                "project": read.name,
                "key": key,
                "what": _cut(what, 100),
                "why": _cut(said if what != said else "", WHY),
                "since": task["since"] or (one["since"] if one else None),
                "unblocks": list(dict.fromkeys([*(one["unblocks"] if one else []), *depends])),
            }
            | _work(read, value, slug, one)
        )
    return made


def _threads(read: Read) -> list[dict[str, Any]]:
    """A need for each thread of no row whose holder in `work.json` is the user, since it last
    wrote."""
    wrote = {
        one.get("id"): when(one.get("wrote") or one.get("updatedAt"))
        for one in read.mine.get("threads") or []
        if isinstance(one, dict)
    }
    made = []
    for line in (read.work or {}).get("work", []):
        if not isinstance(line, dict) or line.get("kind") != "thread" or line.get("who") != USER:
            continue
        value, key = text(line.get("value"), 20), text(line.get("key"), 120)
        said = SAYS.get(value, "")
        if value == "lost":
            said = LOST.get((line.get("facts") or {}).get("thread", ""), LOST["completed"])
        role, slug = text(line.get("role"), 20), text(line.get("slug"), 80)
        made.append(
            {
                "project": read.name,
                "key": key,
                "what": _cut(text(line.get("title")) or key, 100),
                "why": _cut(said or text(line.get("waits")), WHY),
                "since": wrote.get(line.get("key")),
                "unblocks": [],
            }
            | _work(read, value, slug, None)
            | {
                "open": "#/"
                + "/".join(quote(one, safe="") for one in (read.name, "thread", role, slug))
            }
        )
    return made


def _needs(read: Read, waits: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
    """The two queues of the page: what only the user can move, oldest first, and the gates
    that go ahead on their default, soonest first. An item of the list that names a row is
    the row's, and the row is a need where `work.json` says the user holds it (`_rows`)."""
    asked = {str(one.number): one for one in questions.load(read.state)}
    queues: dict[str, list[dict[str, Any]]] = {NEEDS: [], PROCEEDS: []}
    found = item.items(read.state)
    redirected = {one.slug for one in found.values() if one.slug and one.redirect}
    for one in waits:
        if one["kind"] in ROWS:
            continue
        held = asked.get(one["number"]) if one["answerable"] else None
        tier = _tier(one, held)
        if tier:
            queues[tier].append(_need(read, one, held, tier))
    listed = {one["key"]: one for one in waits if one["kind"] in ROWS}
    rows = [one for one in _rows(read, listed) if _approves(one) not in redirected]
    approving = {_approves(one) for one in rows} - {""}
    needs = oldest([*queues[NEEDS], *rows, *_threads(read), *_items(read, found, approving)])
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
