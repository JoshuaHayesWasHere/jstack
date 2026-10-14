"""What waits on the user: the list the last pass left, with the gates as they are now, and
every gate of the home's `gates.md` that jbus does not hold as a question."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jbus import mirror, questions, queue, waiting
from jbus.view.state import WAITING_FILE, WORDS, Read, Source, _mtime, asker, text, when

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
SHAPE = {"waiting": [_WAITS], "gates": [_GATE]}
SOURCES = (
    WAITING_FILE,
    Source("gates.md", "server", lambda read: {"at": _mtime(read.home / "gates.md")}, 140),
)


def _gates(state: Path, home: Path) -> list[dict[str, Any]]:
    """Every gate of the home's `gates.md` and of each scoped home's, open or not, but for
    one jbus holds as a question: that one is on the waiting list while it is open. A gate
    that a slug removed from the queue asked is left out too."""
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
    """What an item of the list has of the question jbus holds for it: whether it can be
    answered on the page, what the gate wrote, and who asked. An item that is no question
    of jbus's, as a gate of a home's `gates.md`, has each of them empty."""
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
    """The list of what waits on the user, as the last pass left it, with the gates as they
    are now, in jbus's questions and in `gates.md`: a gate keeps the `since` the pass gave
    it, a new question has the time it was asked, and a new gate of a file has none. A
    leftover of a task that ended has the words its task says (`words`), not the pass's.
    A question jbus holds has what the page needs to answer it (`_question`)."""
    kept = [one for one in left or [] if one["kind"] in waiting.KINDS]
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
        for one in sorted(listed, key=lambda one: waiting.KINDS.index(one["kind"]))
    ]


def build(read: Read) -> dict[str, Any]:
    if not read.name:
        return {"waiting": [], "gates": []}
    words = {
        one["slug"]: one["state"]["say"]
        for one in read.tasks
        if one["state"]["kind"] in ("leftover", "closed")
    }
    return {
        "waiting": _waiting(read.state, read.home, read.left, words, read.mine.get("threads")),
        "gates": _gates(read.state, read.home),
    }
