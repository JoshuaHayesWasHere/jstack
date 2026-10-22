"""The user's words, as jbus keeps them: each question the user answered, each word that
`jbus word` sent, and each approval of a row with what the approval is based on. The panel gives
one list, newest first, of three kinds of entry, each with the key that the page opens it by. An
approval with no record has no time, and such approvals come last, by slug.

The panel reads `questions.json`, `words.json` and the queue, and writes none of them. An
answered question is on no waiting list (`waiting.gates`), so this panel is the one place that
lists it. An approval is the record that `queue.approve` writes. For a row approved before jbus
kept that record, the approval is the string the row held then, marked as no record.
"""

from __future__ import annotations

from typing import Any

from jbus import questions, queue, word
from jbus.view.state import QUEUE_FILE, WORDS, Read, kept, text, when

FIRST = True
NO_RECORD = "no record: approved before the record was kept"
_ENTRY = {
    key: None
    for key in (
        "kind",
        "key",
        "at",
        "slug",
        "number",
        "question",
        "default",
        "words",
        "by",
        "where",
        "keeps",
        "home",
        "said_at",
        "said_in",
        "checked",
        "kept_at",
        "sent_at",
        "waits",
        "basis",
        "ref",
        "rests",
        "follows",
        "who",
        "ran_at",
        "line",
    )
}
SHAPE = {"words": [_ENTRY]}


def _asked(read: Read) -> list[questions.Question] | None:
    try:
        return questions.read(read.state) if read.name else None
    except questions.Unparsable:
        return None


def _kept(read: Read) -> list[word.Word] | None:
    try:
        return word.load(read.state) if read.name else None
    except word.Unparsable:
        return None


SOURCES = (
    kept(questions.NAME, lambda read: read.once(_asked), 80),
    kept(word.NAME, lambda read: read.once(_kept), 85),
    QUEUE_FILE,
)


def _answer(one: questions.Question, said: questions.Answer, read: Read) -> dict[str, Any]:
    return {
        "kind": "answer",
        "key": f"question:{one.number}",
        "at": when(said.at, read.user),
        "slug": text(one.slug, 80),
        "number": one.number,
        "question": text(one.question, WORDS),
        "default": text(one.default, WORDS),
        "words": text(said.words, WORDS),
        "by": text(said.by, 80),
        "where": "" if said.closed_by == questions.HOME else text(said.where),
        "keeps": said.keeps,
        "home": said.closed_by == questions.HOME,
        "said_in": text(said.said_in),
        "checked": said.checked,
    }


def _word(one: word.Word, read: Read) -> dict[str, Any]:
    return {
        "kind": "word",
        "key": f"word:{one.id}",
        "at": when(one.at, read.user),
        "words": text(one.words, WORDS),
        "by": text(one.by, 80),
        "said_in": text(one.said_in),
        "checked": one.checked,
        "kept_at": when(one.kept_at),
        "sent_at": when(one.sent_at),
        "waits": text(one.waits),
    }


_RESTS = {"word": "word", "answer": "question"}


def _approval(row: queue.Row, read: Read) -> dict[str, Any] | None:
    """The row's approval from its record, or, where there is no record, the string the row
    holds."""
    slug, made = text(row.get("slug"), 80), queue.record(row)
    entry = {"kind": "approval", "key": f"approval:{slug}", "slug": slug}
    if made is None:
        typed = text(row.get("approved"))
        return entry | {"at": None, "line": NO_RECORD, "words": typed} if typed else None
    rests = _RESTS.get(made.basis)
    return entry | {
        "at": when(made.ran_at),
        "basis": text(made.basis, 20),
        "ref": text(made.ref, 120),
        "rests": f"{rests}:{text(made.ref, 120)}" if rests else "",
        "words": text(made.words, WORDS),
        "said_at": when(made.said_at, read.user),
        "said_in": text(made.said_in),
        "checked": made.checked,
        "follows": text(made.follows, 80),
        "who": text(made.who()),
        "ran_at": when(made.ran_at),
        "line": text(made.line()),
    }


def build(read: Read) -> dict[str, Any]:
    answered = [_answer(one, one.answer, read) for one in read.once(_asked) or [] if one.answer]
    sent = [_word(one, read) for one in read.once(_kept) or []]
    approved = [made for row in read.rows if (made := _approval(row, read))]
    found = answered + sent + approved
    timed = sorted((one for one in found if one["at"]), key=lambda one: one["at"], reverse=True)
    untimed = sorted((one for one in found if not one["at"]), key=lambda one: one["key"])
    return {"words": timed + untimed}
