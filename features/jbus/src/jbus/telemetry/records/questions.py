"""`questions.json`, a snapshot of each question asked of the user, by its number."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.readers import questions
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _count, _dict, _length, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    answer = _dict(one.get("answer"))
    return {
        "number": _number(one.get("number")),
        "slug": _text(one.get("slug")),
        "thread": _text(one.get("thread")),
        "asked_at": utc(one.get("asked_at"), zone),
        "holds": bool(one.get("holds")),
        "options": _count(one.get("options")),
        "answered_at": utc(answer.get("at"), zone),
        "answered_by": _text(answer.get("by")),
        "closed_by": _text(answer.get("closed_by")),
        "answer_place": _text(answer.get("where")),
        "keeps": answer.get("keeps") if isinstance(answer.get("keeps"), bool) else None,
        "ref": _text(answer.get("ref")),
        "question_len": _length(one.get("question")),
        "default_len": _length(one.get("default")),
        "context_len": _length(one.get("context")),
        "words_len": _length(answer.get("words")),
    }


SOURCE = Source(
    "questions",
    "questions.json",
    "snapshot",
    _columns(
        "number",
        "slug",
        "thread",
        "asked_at",
        "holds",
        "options",
        "answered_at",
        "answered_by",
        "closed_by",
        "answer_place",
        "keeps",
        "ref",
        "question_len",
        "default_len",
        "context_len",
        "words_len",
    ),
    row,
    at="asked_at",
    records=questions,
    natural="number",
)
