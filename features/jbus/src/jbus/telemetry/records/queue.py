"""`queue.json`, a snapshot of each row of the queue, by its slug, with the go it rests on."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.readers import listed
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _dict, _number, _pull, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    approval = _dict(one.get("approval"))
    return {
        "slug": _text(one.get("slug")),
        "status": _text(one.get("status")),
        "item": _text(one.get("item")),
        "entry": _text(one.get("entry")) or _text(one.get("parent_entry")),
        "priority": _number(one.get("priority")),
        "thread": _text(one.get("thread")),
        "pr": _pull(one.get("pr")),
        "on_hold": bool(one.get("held")),
        "role": _text(one.get("role")),
        "updated": utc(one.get("updated"), zone),
        "approval_basis": _text(approval.get("basis")),
        "approval_ref": _text(approval.get("ref")),
        "approval_said_at": utc(approval.get("said_at"), zone),
        "approval_ran_at": utc(approval.get("ran_at"), zone),
        "follows": _text(approval.get("follows")) or None,
        "queued_by_session": _text(_dict(one.get("queued_by")).get("session")),
        "approval_message": _approval_message(approval),
    }


def _approval_message(approval: Row) -> str | None:
    """The `<thread id>/<message id>` a row's go rests on: an entry's go keeps it in `message`,
    a go on the user's message or pick in `ref`, and any other go names none."""
    basis = approval.get("basis")
    if basis == "entry":
        return _text(approval.get("message"))
    return _text(approval.get("ref")) if basis in ("message", "pick") else ""


SOURCE = Source(
    "queue",
    "queue.json",
    "snapshot",
    _columns(
        "slug",
        "status",
        "item",
        "entry",
        "priority",
        "thread",
        "pr",
        "on_hold",
        "role",
        "updated",
        "approval_basis",
        "approval_ref",
        "approval_said_at",
        "approval_ran_at",
        "follows",
        "queued_by_session",
        "approval_message",
    ),
    row,
    at="approval_ran_at",
    records=listed,
    natural="slug",
)
