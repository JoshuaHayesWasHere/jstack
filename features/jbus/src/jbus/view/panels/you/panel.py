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
whose default is already taken. It closes with that default in the first pass that sees it
(`questions.QUIET`). A gate of a home's `gates.md` instead stands until its home closes it, and
its default says so. A gate of a retired scope (`retired`) waits on nobody: neither queue has
an open one, and the list of gates keeps only its answered ones. A link's conflict is a
question for its home, not for the user, so it is on neither queue.

A proposed work item is a need too, of the kind `ITEM`, which the user approves by its id on the
page (`_items`). The need carries the two things a steer names: its `item`, and the line it was
last `seen` at. Every other need has those two empty. Each need names the task it is about, its
`slug`, or none, so the page draws that task once. Every need names its subject, `subj`: the row
or question it is about (`waiting.subject`), or the title of a thread of no row, so that no need
reads only as its question. Where a proposed item's row waits for its
approval, the panel leaves the item to that row. A go by the item's id is no go of the row. But
for a row whose item was redirected, the item's id is the only thing that approves it
(`jbus.steer.approvable`). So the item's need then takes the row's place.

Each need has one action, its `act` (`ACTS`): `answer` closes a question jbus holds, through
`POST /answer`; `approve` gives a row its go, or approves a proposed item through `POST /steer`;
`steer` gives the user's line about it to the home that owns it, as `jbus word` does; `open`
only opens it, for setup that no home can do. Each need says what happens if the user does
nothing, its `default` (`IDLE` where the kind has none of its own).

The panel takes two writes of its own (`WRITES`). `approve` keeps the user's word that approves
a row and records the go on it, as `jbus word` and `jbus queue approve --word` do, for the brief
whose sha the page showed (`sha`). `hold` takes that go back, as `jbus queue hold` does, while the
row has not launched: it is the undo of `approve`. `steer` keeps the user's line, which starts
with the need's subject, as a word. A need goes from the list as soon as its action is recorded:
a question that closed, a row with a go that holds for its brief as it is now (whose proposed
item then stays left to the row, as it was while the row waited), an item approved, and a need
whose subject a word kept after the need began names (`steered`). A steered need is on the list
`steered`, with its home, and comes back to `needs` if its state changes after the word. A need
that keeps no time (`since`) has no change to come back on, so a steer leaves it on `needs`, with
the time of the line."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jbus
from jbriefs import home as jbriefs
from jbus import asks, dispatch, item, mirror, passes, questions, queue, steer, t3, waiting, word
from jbus.view.homes import Owner
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
from jbus.view.writes import SEND, Answer, said

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
        "subj",
        "home",
        "act",
        "sha",
        "steered",
    )
} | {"answerable": None, "unblocks": [None]}
SHAPE = {
    "waiting": [_WAITS],
    "gates": [_GATE],
    "needs": [_NEED],
    "proceeds": [_NEED],
    "steered": [_NEED],
}
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
ANSWERS, APPROVES, STEERS, OPENS = "answer", "approve", "steer", "open"
ACTS = {"approve": APPROVES, ITEM: APPROVES, "config": OPENS}
"""The action of a need by its kind. A gate's is `answer` where jbus holds its question, and
`steer` where it lives in a home's file. Any other kind's is `steer`."""
IDLE = {
    "approve": "It stays queued, and nothing launches it.",
    ITEM: "It stays proposed, and no work starts on it.",
    "row": "It stays at its gate, and nothing launches it.",
    "left": "It stays as it was left, and nothing cleans it up.",
    "hold": "The pull request waits, and nothing merges it.",
    "config": "jbus goes on without it.",
    "gate": "It waits for your answer.",
}
"""What happens if the user does nothing, for a need whose kind has no default of its own. A
thread's need, such as one that hung, has `QUIET`."""
QUIET = "jbus says it and interrupts nothing, so the thread stays as it is."
SAID_IN = "jbus view"
SOURCES = (
    WAITING_FILE,
    Source("gates.md", "server", lambda read: {"at": _mtime(read.home / "gates.md")}, 140),
)


CLOSED = re.compile(r"^Scope closed:", re.M)


def retired(home: Path) -> set[str]:
    """The retired scopes of the home, each a directory with a `gates.md`. A scope is retired
    when jbriefs no longer counts it as one, since it has no `home-id` and no `Was home:` line,
    or when its handoff says its scope closed, as `skills/handoff` writes it, and its `home-id`
    names no thread, so no home was started for it since."""
    live = {scope.name: scope for scope, _, _ in jbriefs.scopes(home)}
    found = set()
    for file in home.glob("*/gates.md"):
        scope = file.parent
        if scope.name not in live:
            found.add(scope.name)
            continue
        try:
            closed = CLOSED.search((scope / "handoff.md").read_text(errors="replace"))
        except OSError:
            closed = None
        if closed and not jbriefs.thread_of(scope):
            found.add(scope.name)
    return found


def _gates(state: Path, home: Path) -> list[dict[str, Any]]:
    """Every gate of the home's `gates.md` and of each scoped home's, open or not, except one
    that jbus holds as a question, which is on the waiting list while it is open. The panel also
    leaves out a gate whose slug was removed from the queue, and an open gate of a retired
    scope."""
    held = {one.key for one in questions.load(state)}
    gone = queue.removed_slugs(state)
    over = retired(home)
    found = []
    for file, number, asked, body, key in mirror.home_gates(home):
        status = mirror.field(body, "Status")
        if (
            key in held
            or mirror.asker(body) in gone
            or (status.startswith("open") and file.parent != home and file.parent.name in over)
        ):
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
    has what the page needs to answer it (`_question`). A gate of a retired scope is not on it."""
    kept = [one for one in left or [] if one["kind"] in waiting.kinds()]
    since = {one["key"]: one.get("since") for one in kept}
    asked = questions.load(state)
    held = {str(one.number): one for one in asked}
    try:
        over = retired(home)
        live = [
            one
            for one in waiting.gates(home, asked, queue.removed_slugs(state))
            if one["home"] not in over
        ]
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
    rowed = any(row["slug"] == slug for row in read.rows)
    if kind == "gate":
        what, why = waits["question"], _cut(waits["context"])
    else:
        what, why = line, ""
    default = waits["default"]
    if kind == "gate" and one is None and default.strip():
        who = f"the home of {waits['home']}" if waits["home"] else "the home"
        stands = f". It stands until {who} closes it."
        default = _cut(default.strip().rstrip("."), 600 - len(stands)) + stands
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
        "default": _cut(default, 600),
        "risk": one.holds if one and one.holds else REVERSIBLE,
        "unblocks": waits["unblocks"],
        "open": _route(read.name, waits, slug),
        "due": due,
        "item": "",
        "seen": "",
        "slug": slug,
        "subj": waiting.subject(waits | ({} if rowed else {"slug": ""})),
        "home": read.homes.of_gate(waits["home"])
        if waits["home"]
        else read.homes.of_task(slug).name,
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
                "subj": one.slug or one.id,
                "home": read.homes.of_task(one.slug or "").name,
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
                "subj": slug,
                "home": task["home"],
            }
            | _work(read, value, slug, one)
        )
    return made


def _threads(read: Read) -> list[dict[str, Any]]:
    """A need for each thread of no row whose holder in `work.json` is the user, since it last
    wrote. It belongs to the thread's home, or to the root for a thread of no home."""
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
        owner = read.homes.of_thread({"role": role, "slug": slug}, text(line.get("thread"), 80))
        made.append(
            {
                "project": read.name,
                "key": key,
                "what": _cut(text(line.get("title")) or key, 100),
                "why": _cut(said or text(line.get("waits")), WHY),
                "since": wrote.get(line.get("key")),
                "unblocks": [],
                "subj": slug or _cut(text(line.get("title")) or key, 100),
                "home": (owner or Owner()).name,
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
    gone = {
        row["slug"]
        for row in read.rows
        if row.get("approved")
        and queue.approved_text(row, queue.brief(read.state, row["slug"]) or "")
    }
    rows = [one for one in rows if _approves(one) not in gone]
    needs = oldest([*queues[NEEDS], *rows, *_threads(read), *_items(read, found, approving)])
    proceeds = sorted(queues[PROCEEDS], key=lambda one: one["due"] or "~")
    try:
        words = word.load(read.state)
    except word.Unparsable:
        words = []
    return [_acted(read, one, words) for one in needs], [
        _acted(read, one, words) for one in proceeds
    ]


def _steered(one: dict[str, Any], words: list[word.Word]) -> str | None:
    """When the user last steered a need: the latest word that starts with the need's subject
    and was kept after the need began. A need that keeps no time is steered by any such word."""
    began = one["since"] or ""
    mark = f"{one['subj']}: "
    kept = [when(each.kept_at) or "" for each in words if each.words.startswith(mark)]
    return max((at for at in kept if at > began), default=None) if one["subj"] else None


def _quiet(one: dict[str, Any]) -> bool:
    """Whether a steered need leaves the lists until it changes. A need that keeps no time has
    no change to come back on, so it stays, with when it was steered."""
    return bool(one["steered"] and one["since"])


def _acted(read: Read, one: dict[str, Any], words: list[word.Word]) -> dict[str, Any]:
    """A need with its one action, the default it goes ahead on, the sha of the brief that a
    row to approve has now, and when the user steered it."""
    kind = one["kind"]
    act = ACTS.get(kind) or (ANSWERS if kind == "gate" and one["answerable"] else STEERS)
    sha = ""
    if kind == "approve" and _SLUG.fullmatch(one["slug"]):
        sha = queue.brief_sha(queue.brief(read.state, one["slug"]) or "")[:12]
    return one | {
        "act": act,
        "sha": sha,
        "default": one["default"] or IDLE.get(kind, QUIET),
        "steered": _steered(one, words) if act == STEERS else None,
    }


def build(read: Read) -> dict[str, Any]:
    if not read.name:
        return {"waiting": [], "gates": [], "needs": [], "proceeds": [], "steered": []}
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
        "needs": [one for one in needs if not _quiet(one)],
        "proceeds": [one for one in proceeds if not _quiet(one)],
        "steered": [one for one in [*needs, *proceeds] if _quiet(one)],
    }


LONGEST = 600


def _asked(body: bytes, *names: str) -> dict[str, str] | None:
    """The fields a write names, each a string of words, or None where the body is not that."""
    try:
        asked = json.loads(body)
        found = {name: asked[name] for name in names}
    except (ValueError, TypeError, KeyError):
        return None
    shaped = all(isinstance(one, str) and 0 < len(one) <= LONGEST for one in found.values())
    return found if shaped else None


def _config(app: Any) -> jbus.Config:
    return replace(app.config(), state_dir=app.sources.state_dir, home_dir=app.sources.home_dir)


def _pass(app: Any, name: str) -> passes.Pass:
    config = _config(app)
    return passes.Pass(config, config.project(name), app.clock(), say=lambda line: None)


def _keep(app: Any, name: str, words: str) -> tuple[passes.Pass, word.Word]:
    """Keep the user's word for the project, said in the view now, as `jbus word` keeps it."""
    run, user = _pass(app, name), app.sources.user
    return run, word.keep(run, words, user.user, user.stamp(run.now))


def _went(run: passes.Pass, kept: word.Word) -> str:
    """Send the words that wait, as `jbus word` does, and say what became of this one."""
    hidden = run.config.secrets()
    try:
        client: t3.Client | None = t3.Client(run.config.server, run.config.token_path, timeout=SEND)
    except jbus.Refused:
        client = None
    try:
        word.deliver(run, client)
        (one,) = [one for one in word.load(run.state) if one.id == kept.id]
    except (jbus.Refused, OSError, ValueError) as error:
        return jbus.redact(f"It is kept, and the next pass sends it ({error}).", hidden)
    if one.sent_at:
        return f"It went to the home's thread, {one.thread}."
    return jbus.redact(
        f"It is kept and not yet sent, since {one.waits}: the next pass sends it.", hidden
    )


def _refused(status: int, say: str) -> Answer:
    return said(status, {"say": say})


def _approve(app: Any, name: str, body: bytes) -> Answer:
    """Give a row its go on the user's word, for the brief whose sha the page showed. Every check
    of the row is made before the word is kept, so a go that is refused leaves no word."""
    asked = _asked(body, "slug", "sha")
    if asked is None or not _SLUG.fullmatch(asked["slug"]):
        return _refused(400, "An approval is the slug of a row and the sha of its brief.")
    slug, sha, state = asked["slug"], asked["sha"], app.sources.state(name)
    row = queue.fresh(state, slug)
    if row is None or row.get("approved") or row.get("status", "queued") != "queued":
        return _refused(409, f"{slug} is no row that waits for a go, and nothing changed.")
    now_is = queue.brief_sha(queue.brief(state, slug) or "")[:12]
    if now_is != sha:
        say = f"{slug}'s brief is {now_is} now, not the {sha} you saw: read it, then approve it."
        return _refused(409, say)
    try:
        steer.approvable(state, slug)
        run, kept = _keep(app, name, f"Approve {slug}, brief {sha}, in {SAID_IN}")
        rests = ("word", kept.id, "")
        _, *ruled = queue.approve(
            state, slug, rests, sha, app.sources.user, asks._asks(run.config, run.project)
        )
    except jbus.Refused as error:
        return _refused(409, f"{slug} has no go: {str(error).removeprefix('refused: ')}.")
    at = app.sources.user.clock(app.clock())
    say = " ".join([f"{slug} approved at {at}, on your word {kept.id}.", *ruled, _went(run, kept)])
    return said(200, {"say": say, "slug": slug, "word": kept.id})


def _hold(app: Any, name: str, body: bytes) -> Answer:
    """Take back a go that `_approve` gave on the word the body names, as `jbus queue hold`
    does, while the row has not launched and no pass has begun its launch, and then tell its
    home with a word of its own. A hold that is refused keeps no word."""
    asked = _asked(body, "slug", "word")
    if asked is None or not _SLUG.fullmatch(asked["slug"]):
        return _refused(400, "An undo is the slug of a row and the word that approved it.")
    slug, given, state = asked["slug"], asked["word"], app.sources.state(name)
    row = queue.fresh(state, slug) or {}
    approval = row.get("approval") or {}
    if (approval.get("basis"), approval.get("ref")) != ("word", given) or row.get("thread"):
        return _refused(409, f"{slug}'s go is not the one word {given} gave, or it launched.")
    run = _pass(app, name)
    out = dispatch.launched(run, slug) or asks._asks(run.config, run.project).launched(slug)
    if out:
        return _refused(409, f"{slug}'s go stands, since a launch is out: {out}.")
    try:
        held = queue.hold(state, slug)
        run, kept = _keep(app, name, f"Hold {slug}: undo of word {given}, in {SAID_IN}")
    except jbus.Refused as error:
        return _refused(409, f"{slug} was not held: {str(error).removeprefix('refused: ')}.")
    return said(200, {"say": f"{held}: its go is taken back. {_went(run, kept)}", "slug": slug})


def _steer(app: Any, name: str, body: bytes) -> Answer:
    """Keep the user's line about a need as a word, which starts with the need's subject, and
    send it to the home that owns that subject, as `jbus word` does."""
    asked = _asked(body, "subj", "words")
    if asked is None or not " ".join(asked["words"].split()):
        return _refused(400, "A steer is the subject of a need and your line about it.")
    try:
        run, kept = _keep(app, name, f"{asked['subj']}: {' '.join(asked['words'].split())}")
    except jbus.Refused as error:
        return _refused(409, f"The line was not kept: {str(error).removeprefix('refused: ')}.")
    home = f"the {kept.home} home" if kept.home else "the root home"
    say = f"Your line on {asked['subj']} is word {kept.id}, for {home}. {_went(run, kept)}"
    return said(200, {"say": say, "word": kept.id})


WRITES = {"approve": _approve, "hold": _hold, "steer": _steer}
