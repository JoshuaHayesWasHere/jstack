"""What waits on the user: the list the last pass left, with the gates as they are now, and every
gate of the home's `gates.md` that jbus does not hold as a question.

The panel builds the page's two queues, as closed records (`_NEED`), in a person's words and with
no command line in them, from one source: jbus's list of what waits on the user, the list that
each pass writes and logs as its `waiting` event (`jbus.waiting`). `needs` is each item of that
list that is not on its default: a row at a gate, one to approve, a held merge, a leftover, a
hold no thread works on, a gate that holds (`Holds:`) or has no default, and a setup. So every
widget that counts Needs you counts that list, and nothing that the system fixes by itself, such
as a hung turn or a lost thread, is a need. An item that names a row (`ROWS`) takes the row's
title, home and the rows behind it from the row's task (`_row`). `proceeds` is a gate whose
default is already taken. It asks the user nothing, and the page draws all of them as one line.
A question jbus holds closes with its default in the first pass that sees it
(`questions.QUIET`). A gate of a home's `gates.md` instead stands until its home closes it, and
its default says so. A gate of a retired scope (`retired`) waits on nobody: neither queue has
an open one, and the list of gates keeps only its answered ones. A link's conflict is a
question for its home, not for the user, so it is on neither queue.

Each need names the task it is about, its `slug`, or none, so the page draws that task once.
Every need names its subject, `subj`: the row or question it is about (`waiting.subject`).

Each need has one action, its `act` (`ACTS`): `answer` closes a question jbus holds, through
`POST /answer`; `approve` gives a row its go; `thread` links to the thread of the home that owns
it in T3 Code, its `thread` (`THREAD`), where the user writes about it; `open` only opens it,
for setup that no home can do.
Each need says what happens if the user does nothing, its `default` (`IDLE` where the kind has
none of its own).
Each need names its `doors`, the cases of the one door table (`party.DOORS`) its action opens, so
a bot can tell what it may not act on: a row to approve has those its brief's `Holds:` lines name,
a gate those its own `Holds:` line names, and any other need none.

The panel takes two writes of its own (`WRITES`). `approve` keeps the user's word that approves
a row and records the go on it, as `jbus word` and `jbus queue approve --word` do, for the brief
whose sha the page showed (`sha`). `hold` takes that go back, as `jbus queue hold` does, while the
row has not launched: it is the undo of `approve`. A need goes from the list as soon as its action
is recorded: a question that closed, and a row with a go that holds for its brief as it is now.
A need whose act is `thread` goes once what holds it changes."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jbus
import jsettings
from jbriefs import below
from jbriefs import home as jbriefs
from jbus import acts, asks, dispatch, mirror, party, passes, questions, queue, t3, waiting, word
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
from jbus.view.writes import SEND, VIEW, Answer, said

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
        "holds",
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
        "slug",
        "subj",
        "home",
        "act",
        "sha",
        "brief_at",
        "thread",
    )
} | {"answerable": None, "unblocks": [None], "doors": [None]}
SHAPE = {
    "waiting": [_WAITS],
    "gates": [_GATE],
    "needs": [_NEED],
    "proceeds": [_NEED],
}
ANSWER = "Answer"
REVERSIBLE, MERGES = "reversible", "merge to main"
NEEDS, PROCEEDS = "needs", "proceeds"
LINE = 200
WHY = 60
ROWS = frozenset({"row", "approve", "hold", "left"})
"""The kinds of the list of what waits on the user whose item names a row of the queue."""
ANSWERS, APPROVES, THREADS, OPENS = "answer", "approve", "thread", "open"
ACTS = {"approve": APPROVES, "config": OPENS, "github": OPENS}
"""The action of a need by its kind. A gate's is `answer` where jbus holds its question, and
`thread` where it lives in a home's file. Any other kind's is `thread`."""
IDLE = {
    "approve": "It stays queued, and nothing launches it.",
    "row": "It stays at its gate, and nothing launches it.",
    "left": "It stays as it was left, and nothing cleans it up.",
    "hold": "The pull request waits, and nothing merges it.",
    "config": "jbus goes on without it.",
    "github": "It clears by itself when GitHub's window starts again, and until then jmerge "
    "still merges.",
    "gate": "It waits for your answer.",
}
"""What happens if the user does nothing, for a need whose kind has no default of its own. Any
other kind's need, such as a hold no thread works on, has `QUIET`."""
QUIET = "jbus says it and interrupts nothing, so the thread stays as it is."
THREAD = "t3-thread://v1/{}"
"""The link that opens a thread in T3 Code, by its id."""
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
        status = below.line(body, "Status:")
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
                "default": text(below.line(body, "Default:"), 600),
                "built_on": text(below.line(body, "Built on it:")),
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
    state: Path,
    home: Path,
    left: list[Any] | None,
    words: dict[str, str],
    threads: Any = None,
    user: jsettings.Settings | None = None,
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
    why = questions.waits(state, user) if user is not None else lambda one: ""
    try:
        over = retired(home)
        live = [
            one
            for one in waiting.gates(home, asked, queue.removed_slugs(state), why)
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
            "holds": text(one.get("holds")),
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


def _queued_brief(read: Read, slug: str) -> str:
    """The brief that `slug` has in the project's `briefs/`, empty where there is no such
    brief."""
    try:
        return (queue.brief(read.state, slug) if _SLUG.fullmatch(slug) else None) or ""
    except ValueError:
        return ""


def _title(read: Read, slug: str) -> str:
    """The title line of the brief that `slug` has in the project's `briefs/`, empty where
    there is no such brief."""
    titled = (line[2:] for line in _queued_brief(read, slug).splitlines() if line.startswith("# "))
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
    and goes ahead on its default where it has one and no `Holds:` line."""
    if waits["kind"] != "gate":
        return NEEDS
    if one is None:
        return PROCEEDS if waits["default"].strip() and not waits["holds"] else NEEDS
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
    if kind == "gate" and one is None and default.strip() and not waits["holds"]:
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
        "risk": (one.holds if one else waits["holds"]) or REVERSIBLE,
        "doors": list(party.held(waits["holds"])) if waits["holds"] else [],
        "unblocks": waits["unblocks"],
        "open": _route(read.name, waits, slug),
        "due": due,
        "slug": slug,
        "subj": waiting.subject(waits | ({} if rowed else {"slug": ""})),
        "home": read.homes.of_gate(waits["home"])
        if waits["home"]
        else read.homes.of_task(slug).name,
    }


def _work(read: Read, kind: str, slug: str, waits: dict[str, Any]) -> dict[str, Any]:
    """What the need of a row has that its kind gives: its kind, verb, risk, and the route of
    the item's drawer."""
    return {
        "kind": kind,
        "verb": waiting.verb(kind),
        "risk": MERGES if kind == "hold" else REVERSIBLE,
        "doors": list(party.doors(_queued_brief(read, slug))) if kind == "approve" else [],
        "open": _route(read.name, waits, slug),
        "answerable": False,
        "default": "",
        "due": None,
        "slug": slug,
    }


def _task(read: Read, waits: dict[str, Any]) -> dict[str, Any] | None:
    """The task of the row that an item of the list names: by its slug, or by its pull request
    for a hold. None where no task of the queue is that row."""
    for task in read.tasks:
        if waits["slug"] and task["slug"] == waits["slug"]:
            return task
        if waits["kind"] == "hold" and task["pr"] and task["pr"] == waits["key"]:
            return task
    return None


def _row(read: Read, waits: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """The need of an item of the list that names a row of the queue: the row's title, what
    holds it in the task's words (the item's line only where the task says nothing), since when
    the row is in that state (or else since when the item waits), its home, and the rows that
    wait behind it. A row to approve is since when it came onto the list, as the drawer of what
    waits counts it: its brief's own time is `brief_at`."""
    kind, slug = waits["kind"], task["slug"]
    title = _title(read, slug)
    said = task["state"]["say"] or task["state"]["waits"] or _after(waits["line"], waits["slug"])
    what = title or (said if kind == "row" else slug)
    if kind == "hold":
        what = f"Pull request {task['pr']}" + (f": {title}" if title else "")
    depends = [
        other["slug"]
        for other in read.tasks
        if any(each["slug"] == slug for each in other["depends"])
    ]
    return {
        "project": read.name,
        "key": waits["key"],
        "what": _cut(what, 100),
        "why": _cut(said if what != said else "", WHY),
        "since": (waits["since"] or task["since"])
        if kind == "approve"
        else (task["since"] or waits["since"]),
        "unblocks": list(dict.fromkeys([*waits["unblocks"], *depends])),
        "subj": slug,
        "home": task["home"],
    } | _work(read, kind, slug, waits)


def _needs(read: Read, waits: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
    """The two queues of the page, both from the list of what waits on the user and from nothing
    else: each item of it that is not on its default, oldest first, and the gates that go ahead
    on their default, soonest first. An item that names a row of the queue takes its words and
    home from the row's task (`_row`). A row to approve whose go holds for its brief as it is now
    is no need, since the next pass takes it off the list."""
    asked = {str(one.number): one for one in questions.load(read.state)}
    approved = {
        row["slug"]
        for row in read.rows
        if row.get("approved")
        and queue.approved_text(row, queue.brief(read.state, row["slug"]) or "")
    }
    queues: dict[str, list[dict[str, Any]]] = {NEEDS: [], PROCEEDS: []}
    for one in waits:
        if one["kind"] == "approve" and one["slug"] in approved:
            continue
        held = asked.get(one["number"]) if one["answerable"] else None
        tier = _tier(one, held)
        if not tier:
            continue
        task = _task(read, one) if one["kind"] in ROWS else None
        queues[tier].append(_row(read, one, task) if task else _need(read, one, held, tier))
    needs = oldest(queues[NEEDS])
    proceeds = sorted(queues[PROCEEDS], key=lambda one: one["due"] or "~")
    return [_acted(read, one) for one in needs], [_acted(read, one) for one in proceeds]


def _thread(read: Read, home: str) -> str:
    """The link to the thread of the home by its name, the root's for none, or nothing where it
    has none."""
    found = jbriefs.thread_of(read.home / home if home else read.home)
    return THREAD.format(found) if found else ""


def _acted(read: Read, one: dict[str, Any]) -> dict[str, Any]:
    """A need with its one action, the default it goes ahead on, the sha of the brief that a
    row to approve has now and when that brief was written, and the thread of its home where the
    action is to write there."""
    kind = one["kind"]
    act = ACTS.get(kind) or (ANSWERS if kind == "gate" and one["answerable"] else THREADS)
    sha, written = "", None
    if kind == "approve" and _SLUG.fullmatch(one["slug"]):
        sha = queue.brief_sha(queue.brief(read.state, one["slug"]) or "")[:12]
        written = _mtime(queue.brief_path(read.state, one["slug"]))
    return one | {
        "act": act,
        "sha": sha,
        "brief_at": written,
        "default": one["default"] or IDLE.get(kind, QUIET),
        "thread": _thread(read, one["home"]) if act == THREADS else "",
    }


def build(read: Read) -> dict[str, Any]:
    if not read.name:
        return {"waiting": [], "gates": [], "needs": [], "proceeds": []}
    words = {
        one["slug"]: one["state"]["say"]
        for one in read.tasks
        if one["state"]["kind"] in ("leftover", "closed")
    }
    waits = _waiting(read.state, read.home, read.left, words, read.mine.get("threads"), read.user)
    needs, proceeds = _needs(read, waits)
    return {
        "waiting": waits,
        "gates": _gates(read.state, read.home),
        "needs": needs,
        "proceeds": proceeds,
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
    """Keep the user's word for the project, said in the view now, as the view's act."""
    run = _pass(app, name)
    heard = party.Evidence("view", "", words, app.sources.user.stamp(run.now), SAID_IN)
    return run, word.keep(run, VIEW, heard)


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
        run, kept = _keep(app, name, f"Approve {slug}, brief {sha}, in {SAID_IN}")
        heard = party.Evidence("typed", kept.id, kept.words, kept.at, SAID_IN)
        made = acts.act(
            run,
            VIEW,
            party.Action("go", slug, sha),
            heard,
            asks=asks._asks(run.config, run.project),
        )
    except jbus.Refused as error:
        return _refused(409, f"{slug} has no go: {str(error).removeprefix('refused: ')}.")
    if made.outcome == "gated":
        say = f"{slug} waits for your own word, read in T3 Code or on a Lavish page: {made.line}."
        return said(200, {"say": " ".join([say, _went(run, kept)]), "slug": slug, "word": kept.id})
    _, *ruled = made.line.split("\n")
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
    words = f"Hold {slug}: undo of word {given}, in {SAID_IN}"
    try:
        held = acts.act(
            run,
            VIEW,
            party.Action("hold", slug),
            party.Evidence("view", "", words, app.sources.user.stamp(run.now), SAID_IN),
            does=lambda: queue.hold(state, slug),
        ).line
        run, kept = _keep(app, name, words)
    except jbus.Refused as error:
        return _refused(409, f"{slug} was not held: {str(error).removeprefix('refused: ')}.")
    return said(200, {"say": f"{held}: its go is taken back. {_went(run, kept)}", "slug": slug})


WRITES = {"approve": _approve, "hold": _hold}
