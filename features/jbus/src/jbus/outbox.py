"""Every message jbus sends to a thread goes out through `send`, and through no other call: a test
scans the package for any other module that names the tool.

A sender names the thread, the row the message is about, its retry key, its text, the name of its
template, and what it needs of the receiver: `act`, where the receiver has work, or `decide`, where
a person or a home must choose. There is no third kind, since a message that needs neither is not
sent.

`send` holds a message to a thread whose instance is capped (`jroles.ledger`), since a message sent
then starts a turn that ends at once on the limit. The key stays unsent, the pass says so in one
`wait` line, and the first pass after the reset sends it, since each sender asks again on each pass
until a message goes.

Each send and each hold is one line of `outbox.jsonl` in the project's state: the time, the thread,
the row, the template, what the message needs, its key, `sent` or `held`, and the rule that held it.
A census of what jbus sent is a read of that one file. It is not `outbox.json`, the queue of events
that waits for the webhook (`jbus.wake`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from jbus.t3 import Client, T3Error
from jroles import ledger

if TYPE_CHECKING:
    from jbus.passes import Pass

FILE = "outbox.jsonl"
NEEDS = ("act", "decide")
Needs = Literal["act", "decide"]


def capped(run: Pass, client: Client, thread: str) -> int | None:
    """Return the Unix time the cap on a thread's instance resets, or None while that instance
    has headroom, or where T3 Code did not say which instance the thread is on. A thread whose
    instance is not known is not held: the send that follows says what T3 Code said of it."""
    if not thread:
        return None
    try:
        asked = client.call("t3_thread_configuration", {"threadId": thread})
    except T3Error:
        return None
    chosen = asked.get("modelSelection") or {}
    instance = chosen.get("instanceId") or chosen.get("provider") or ledger.BUILT_IN
    until = ledger.capped_until(ledger.read([instance]), instance, run.now)
    return int(until.timestamp()) if until else None


def send(
    run: Pass,
    client: Client,
    *,
    thread: str,
    row: str,
    key: str,
    text: str,
    template: str,
    needs: Needs,
) -> bool:
    """Queue one message to a thread under its retry key, and return whether it went. Return
    False where the thread's instance is capped: nothing is sent, and the caller leaves the key
    unmarked so a later pass sends it. Raise what `Client.call` raises where T3 Code refused the
    message or gave no answer."""
    if needs not in NEEDS:
        raise ValueError(f"a message needs act or decide of its receiver, not {needs!r}")
    until = capped(run, client, thread)
    if until:
        at = datetime.fromtimestamp(until, UTC).isoformat()
        run.say(
            f"wait {row}: {thread} is capped until {at}, so its {template} message waits for the "
            "reset"
        )
        _log(run, thread, row, key, template, needs, "held", f"cap: until {at}")
        return False
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": text, "mode": "queue", "clientRequestId": key}
    client.call("t3_thread_send", asked)
    _log(run, thread, row, key, template, needs, "sent", "")
    return True


def _log(
    run: Pass,
    thread: str,
    row: str,
    key: str,
    template: str,
    needs: str,
    went: str,
    rule: str,
) -> None:
    line = {
        "at": run.now.isoformat(),
        "thread": thread,
        "row": row,
        "template": template,
        "needs": needs,
        "key": key,
        "went": went,
        "rule": rule,
    }
    run.state.mkdir(parents=True, exist_ok=True)
    with (run.state / FILE).open("a") as kept:
        kept.write(json.dumps(line) + "\n")
