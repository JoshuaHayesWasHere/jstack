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

`send` also holds a message that needs `act` while its receiver cannot act on it now, by the rules
of `RULES`, the one table of them. A new rule is a row of that table, and no sender checks it:

- `slot`: the thread waits on a test slot and is not woken yet (`jgauge.waiters`);
- `review`: the row's pull request waits on a review that a reviewer the crew launched has not
  written at its head, as jmerge's judge says (`ready.short_of`). A crew puts off what it is told
  while its review is out (the crew skill's "A conflict");
- `busy`: the thread has a turn running (`watch.at_work`), or this pass already sent it a message
  that needs `act` (`Pass.told`), so a thread gets at most one such message a pass.

The two that read local files come first, and `busy`, which asks T3 Code, last.

A row spares what the receiver must still get while it waits. `slot` and `review` spare the wakes:
a slot's wake and a pool's (`jbus.slotwait`) and the stall clock's line (`jbus.clock`), so a waiting
crew is still woken, and still told when it has waited too long. `review` also spares a message that
asks for the review itself (`ASKS`), which would otherwise wait on what it asks for. Every rule
spares the user's own word and steer to a home (`jbus.word`, `jbus.steer`), which are the user's and
not jbus's, so jbus never delays them behind a home's turn.

A held message is not queued: its key stays unsent, and the sender, which asks again on each pass,
sends the message the state then calls for, under that state's key, the first pass no rule holds.
So nothing is lost and nothing stale is sent.

Each send and each hold is one line of `outbox.jsonl` in the project's state: the time, the thread,
the row, the template, what the message needs, its key, `sent` or `held`, and the rule that held it.
A census of what jbus sent is a read of that one file. It is not `outbox.json`, the queue of events
that waits for the webhook (`jbus.wake`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import jsettings
from jbus.t3 import Client, T3Error
from jgauge import slot, waiters
from jmerge import ready
from jroles import ledger

if TYPE_CHECKING:
    from jbus.passes import Pass

FILE = "outbox.jsonl"
NEEDS = ("act", "decide")
Needs = Literal["act", "decide"]
WAKES = frozenset({"slot-wake", "pool-wake", "clock"})
"""The templates of a wake: `jbus.slotwait`'s two and the stall clock's line to the thread a wait
is on. `slot` and `review` never hold them."""
ASKS = frozenset(
    {"unreviewed", "twice", "second", "fix", "declines", "unruled", "rereview", "proof"}
)
"""The templates that ask for the review itself: `jbus.expedite`'s kinds whose reason is a review
not written, and `jbus.rebase`'s asks for a scoped review. `review` never holds them, since the
review it waits on is what they ask for."""
USERS = frozenset({"word", "item"})
"""The templates of the user's word and steer to a home (`jbus.word`, `jbus.steer`). No rule
holds them."""


@dataclass(frozen=True)
class Rule:
    """`Rule` is one row of `RULES`: its name, which `outbox.jsonl` keeps for a message it held,
    whether it holds a message to a thread about a row now, and the templates it spares."""

    name: str
    holds: Callable[[Pass, Client, str, str], bool]
    spares: frozenset[str]


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


def busy(run: Pass, client: Client, thread: str, row: str = "") -> bool:
    """Say whether the thread has a turn running, as T3 Code says of it now, or was sent a
    message that needs `act` in this pass (`Pass.told`). A thread that T3 Code says nothing of is
    not busy: the send that follows says what T3 Code said of it."""
    from jbus.watch import at_work

    if jsettings.thread_id(thread) in run.told:
        return True
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return False
    return at_work([(read or {}).get("thread") or {}], settled_too=True)


def waiting(run: Pass, client: Client, thread: str, row: str) -> bool:
    """Say whether the thread waits on a test slot and is not woken yet: a woken one is `busy`
    while it takes up its wake."""
    thread = jsettings.thread_id(thread)
    return any(one.thread == thread and not one.woken for one in waiters.read(slot.locks_dir()))


def reviewing(run: Pass, client: Client, thread: str, row: str) -> bool:
    """Say whether the row's pull request waits on a review at its head that a reviewer the crew
    launched has not written: jmerge's judge (`ready.short_of`) says the review or a scoped review
    is not written, and the brief names a reviewer with no `## Review` yet (`rebase.reviewing`).
    A row with no open pull request in what this pass saw waits on no review."""
    from jbus import clock, rebase
    from jbus.watch import task_brief

    pull = run.world.open.get(row) if run.world else None
    head = (pull or {}).get("headRefOid", "")
    if not head:
        return False
    brief = task_brief(run, row)
    unwritten = clock.class_of(ready.short_of(brief, head)) in ("review", "scoped")
    return unwritten and rebase.reviewing(brief)


RULES = (
    Rule("slot", waiting, WAKES | USERS),
    Rule("review", reviewing, WAKES | ASKS | USERS),
    Rule("busy", busy, USERS),
)
"""Every rule that holds a message that needs `act`, in the order `send` asks them."""


def held(run: Pass, client: Client, thread: str, row: str, template: str, needs: Needs) -> str:
    """Return the name of the first rule of `RULES` that holds a message of this template to the
    thread about the row now, or nothing. A message that needs `decide` is held by none."""
    if needs != "act" or not thread:
        return ""
    rules = (rule for rule in RULES if template not in rule.spares)
    return next((rule.name for rule in rules if rule.holds(run, client, thread, row)), "")


def hold(
    run: Pass, client: Client, *, thread: str, row: str, key: str, template: str, needs: Needs
) -> bool:
    """Say whether the outbox holds this message now: the thread's instance is capped, or a rule of
    `RULES` holds it. A held message gets one `wait` line and one `held` line in `outbox.jsonl`
    with its rule. `send` asks this first, and so does a sender that asks GitHub something before
    it sends (`rebase.held`), so it asks nothing for a message the outbox would hold."""
    until = capped(run, client, thread)
    if until:
        at = datetime.fromtimestamp(until, UTC).isoformat()
        run.say(
            f"wait {row}: {thread} is capped until {at}, so its {template} message waits for the "
            "reset"
        )
        _log(run, thread, row, key, template, needs, "held", f"cap: until {at}")
        return True
    rule = held(run, client, thread, row, template, needs)
    if rule:
        run.say(f"wait {row}: {thread} is held by the {rule} rule, so its {template} message waits")
        _log(run, thread, row, key, template, needs, "held", rule)
    return bool(rule)


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
    False where the outbox holds it (`hold`): nothing is sent, and the caller leaves the key
    unmarked so a later pass sends what is due then. Raise what `Client.call` raises where T3 Code
    refused the message or gave no answer."""
    if needs not in NEEDS:
        raise ValueError(f"a message needs act or decide of its receiver, not {needs!r}")
    if hold(run, client, thread=thread, row=row, key=key, template=template, needs=needs):
        return False
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": text, "mode": "queue", "clientRequestId": key}
    client.call("t3_thread_send", asked)
    if needs == "act":
        run.told.add(jsettings.thread_id(thread))
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
