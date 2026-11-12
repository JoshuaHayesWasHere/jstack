"""The two passes that approve a row of the queue on something other than a verb typed for it.

`entered` keeps the entry rule on the table: under the setting `go = "entry"` a row filed under a
plan entry (`queue add --entry`) is approved by that entry's go, basis `queue.ENTRY`, and an
unlaunched one waits for the user again once that go no longer holds (`jbus.plan.holding`).
jbus's pass runs it on each pass, and `jbus plan go` and `stop` run it at once.

`gone_ahead` approves the row a gate asked about once the gate closed on its default `approve`,
basis `queue.ANSWER`: on the user's answer under any setting, or on silence where the setting
`go` is `silence` and silence starts the row (`queue.unsilenced`).

Both write the table only through the queue's own lock and grant (`queue._changing`,
`queue._grant`), so a row they approve holds the same record as one a verb approved.
"""

from __future__ import annotations

from pathlib import Path

import jsettings
from jbus import queue


def entered(state: Path, user: jsettings.Settings, entry_go: queue.EntryGo) -> list[str]:
    """Keep the entry rule on the table, as jbus's pass does on each pass and `jbus plan` does at
    a go or a stop. An unlaunched row whose go is its entry's goes back to waiting for the user
    when that go no longer holds or its brief now names a case of `gates.md`: a launched row keeps
    its go. Then each waiting row whose entry's go holds is approved (`queue._entered`). Return a
    line for each."""
    said: list[str] = []
    with queue._one_batch(state) as batch:
        rows = batch.rows
        for row in sorted(rows, key=queue.order):
            made, text = queue.record(row), batch.brief(row["slug"])
            if (
                not made
                or made.basis != queue.ENTRY
                or not queue._unlaunched(row)
                or row.get("held")
            ):
                continue
            why = queue.case(text) if text is not None else "its brief is gone"
            if not why and entry_go(text or "", queue.given_entry(row)) is None:
                why = f"the go of its plan entry {queue.given_entry(row)} no longer holds"
            if why:
                back = ", ".join(queue._void(batch, row, queue.who(queue.PASS)))
                said.append(f"{back} waits for the user's go: {why}")
        for row in sorted(rows, key=queue.order):
            line = queue._entered(batch, row["slug"], user, entry_go, queue.PASS)
            if line:
                said.append(line)
    return said


def gone_ahead(
    state: Path, slug: str, number: int, at: str, user: jsettings.Settings, heard: queue.Said | None
) -> str:
    """Approve the row that a gate with the default `approve` asked about, once the gate closed on
    that default, and return the line that says so, or why the row still waits.

    `heard` is the user's answer that kept the default: it is the user's word, and approves the
    row under any setting. With no `heard`, silence closed the gate: the setting `go` is
    `silence`, and silence starts the row (`queue.unsilenced`)."""
    with queue._one_batch(state) as batch:
        row = next((row for row in batch.rows if row["slug"] == slug), None)
        text = batch.brief(slug)
        if row is None or text is None or not queue._waits(row, text):
            return ""
        if heard is not None:
            return queue._grant(batch, row, text, queue.ANSWER, str(number), heard, user, None)
        why = queue.unsilenced(text)
        if user.go != jsettings.SILENCE:
            why = f"the setting go is {user.go}, not {jsettings.SILENCE}"
        if why:
            return f"{slug} waits for the user's go after question {number}: {why}"
        rests = queue.Said("default", at, "", True, str(number))
        return queue._grant(
            batch, row, text, queue.ANSWER, str(number), rests, user, queue.PASS, "", "silence"
        )
