"""`acts.jsonl`, each act jbus or a thread took, with its party and its evidence."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry import asks
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _count, _dict, _length, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    action, evidence, party = (_dict(one.get(name)) for name in ("action", "evidence", "party"))
    return {
        "id": _text(one.get("id")),
        "at": utc(one.get("at"), zone),
        "verb": _text(action.get("verb")),
        "subject": _text(action.get("subject")),
        "outcome": _text(one.get("outcome")),
        "party": _text(party.get("kind")),
        "party_name": _text(party.get("name")),
        "route": _text(party.get("route")),
        "source": _text(evidence.get("source")),
        "ref": _text(evidence.get("ref")),
        "said_in": _text(evidence.get("said_in")),
        "said_at": utc(evidence.get("said_at"), zone),
        "gate": _number(one.get("gate")),
        "doors": _count(action.get("doors")),
        "picks": _count(evidence.get("picks")),
        "words_len": _length(evidence.get("words")),
        "line_len": _length(one.get("line")),
        "checked": evidence.get("checked") if isinstance(evidence.get("checked"), bool) else None,
        "asks": _asks(action.get("verb"), evidence.get("words")),
    }


def _asks(verb: object, words: object) -> str | None:
    """What a word asks, by the rule of a T3 Code message's; no other act has a label."""
    if verb != "word":
        return None
    return asks.label(words if isinstance(words, str) else None)


SOURCE = Source(
    "acts",
    "acts.jsonl",
    "log",
    _columns(
        "id",
        "at",
        "verb",
        "subject",
        "outcome",
        "party",
        "party_name",
        "route",
        "source",
        "ref",
        "said_in",
        "said_at",
        "gate",
        "doors",
        "picks",
        "words_len",
        "line_len",
        "checked",
        "asks",
    ),
    row,
)
