"""Every message jbus sends to a thread goes out through `send`, and through no other call: a test
scans the package for any other module that names the tool.

A sender names the thread, the row the message is about, its retry key, its text, the name of its
template, and what it needs of the receiver: `act`, where the receiver has work, or `decide`, where
a person or a home must choose. There is no third kind, since a message that needs neither is not
sent. A message goes in T3 Code's mode `queue`, which starts a turn, but for a template of `STEERS`,
which goes in mode `auto`: into a turn the thread already runs, as a steer.

A thread whose instance is capped (`jroles.ledger`) moves to the first instance of its pool with
headroom, as `jbus.failover` moves a thread that failed, and the message goes there. Asking `capped`
makes the move, so each sender gets it. A thread with a turn running stays, since nothing moves
under a turn: the turn ends on the limit, and failover moves it then.

`send` holds a message to a thread that could not move, since a message sent then starts a turn that
ends at once on the limit. The key stays unsent, the pass says so in one `wait` line, and the first
pass after the reset sends it, since each sender asks again on each pass until a message goes.

The user's own word is not held behind a ledger that is out of date (`jgauge.limits.unread`): the
ledger keeps what it last read, and launches still go by it, but what it read is no reason to sit on
what the user said. If the account is in fact capped, the turn stops on the limit, the ledger is
written from that, and `jbus.owed` keeps the ask and sends it again when the account frees.

`send` also holds a message that needs `act` while its receiver cannot act on it now, by the rules
of `RULES`, the one table of them, and a message of a template a rule names as the only ones it
holds, whatever it needs. A new rule is a row of that table, and no sender checks it:

- `held`: the row is held in the queue (`jbus queue hold`, or jbus's own at a check that failed
  at two heads, `jbus.stall.twice`), so its crew gets no rebase, no fix message and no restart
  of a failed check (`FIXES`) until it is approved again. It holds no other template: a held
  row's crew still gets the user's answers, its review's findings and every other message;
- `slot`: the thread waits on a test slot and is not woken yet (`jgauge.waiters`);
- `review`: the thread is the row's crew, and the row's pull request waits on a review that a
  reviewer the crew launched has not written at its head, as jmerge's judge says
  (`ready.short_of`). A crew puts off what it is told while its review is out (the crew skill's
  "A conflict"), and a home told of the row is not the crew;
- `busy`: the thread has a turn running (`watch.at_work`), or this pass already sent it a message
  that needs `act` (`Pass.told`), so a thread gets at most one such message a pass;
- `idle`: the thread has no turn running. It holds only the templates of `STEERS`, whatever they
  need: the notice that a merge changed a skill the thread loaded (`jbus.reload`), which asks
  nothing of the thread but to read the skill again before it next follows it, so it goes only
  into a turn the thread already runs and never starts one.

The three that read local files come first, and `busy` and `idle`, which ask T3 Code, last.

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
that waits for the home thread's wake (`jbus.wake`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import jsettings
from jbriefs import meets
from jbriefs.home import thread_of
from jbus import dispatch, queue, review, roles
from jbus.t3 import Client, T3Error
from jbus.watch import at_work, task_brief
from jgauge import limits, slot, waiters
from jmerge import ready, rows
from jroles import ledger
from jsettings import store

if TYPE_CHECKING:
    from jbus.passes import Pass

FILE = "outbox.jsonl"
NEEDS = ("act", "decide")
Needs = Literal["act", "decide"]
WAKES = frozenset({"slot-wake", "pool-wake", "slot-end", "clock"})
"""The templates of a wake: `jbus.slotwait`'s three and the stall clock's line to the thread a wait
is on. `slot` and `review` never hold them."""
ASKS = frozenset(
    {
        "unreviewed",
        "fix",
        "meets-no",
        "meets-unread",
        "meets-miscounted",
        "unruled",
        "rereview",
    }
)
"""The templates that ask for the review itself: `jbus.expedite`'s kinds whose reason is a review
not written, and `jbus.rebase`'s asks for a scoped review. `review` never holds them, since the
review it waits on is what they ask for."""
FIXES = frozenset({"rebase", "restack", "failed", "refailed", "conflict", "drops", "restart"})
"""The templates of a rebase or a fix message to a crew: `jbus.rebase`'s and `jbus.stack`'s, and
the stall clock's restart of a crew whose check failed (`jbus.clock`). `held` holds these and no
other."""
STEERS = frozenset({"reload"})
"""The templates that go only into a turn their thread already runs, as a steer: `idle` holds them
while it has none, and `send` sends them in mode `auto`. The notice of `jbus.reload` is one."""
USERS = frozenset({"word", "item"})
"""The templates of the user's word and steer to a home (`jbus.word`, `jbus.steer`). No rule
holds them."""


@dataclass(frozen=True)
class Rule:
    """`Rule` is one row of `RULES`: its name, which `outbox.jsonl` keeps for a message it held,
    whether it holds a message to a thread about a row now, the templates it spares, and the only
    templates it holds, where it names them."""

    name: str
    holds: Callable[[Pass, Client, str, str], bool]
    spares: frozenset[str]
    only: frozenset[str] | None = None


def selection_of(client: Client, thread: str) -> dict:
    """Return the model selection a thread is on now, as T3 Code says of it. Raise what
    `Client.call` raises where it says nothing."""
    return client.call("t3_thread_configure", {"threadId": thread}).get("modelSelection") or {}


def _instance(chosen: dict) -> str:
    return chosen.get("instanceId") or chosen.get("provider") or ledger.BUILT_IN


def instance_of(client: Client, thread: str) -> str:
    """Return the instance a thread is on now, as T3 Code says of it. Raise what `Client.call`
    raises where it says nothing."""
    return _instance(selection_of(client, thread))


MOVES = {"crew": "crew", "reviewer": "review", "scout": "scout", "home": "home"}
"""The role map's role for each thread role that a capped instance moves, as `jbus.failover` moves
the same roles. A thread of no role stays, and its message waits for the reset."""


def _rolled(run: Pass, client: Client, thread: str, chosen: dict, instance: str, row: str) -> bool:
    """Move an idle thread off its capped `instance` to the first instance of its pool with
    headroom, with its model and options, and say whether it moved. A move T3 Code did not make
    leaves the thread where it is, and its message waits, as does a thread of no role (`MOVES`)."""
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return False
    found = (read or {}).get("thread") or {}
    if not chosen.get("model") or at_work([found], settled_too=True):
        return False
    role, slug = roles.role_of(str(found.get("title", "")))
    if role not in MOVES:
        return False
    instances = dispatch.pool_of(run, MOVES[role], instance)
    subject = row or slug or thread
    choice = dispatch.mirrored_choice(run, subject, instances, {}, instance)
    at = choice.instance
    if at is None or at == instance:
        return False
    client.recipients = client.recipients | {thread}
    client.moves[thread] = (chosen, instances)
    try:
        moved = {**chosen, "instanceId": at}
        client.call("t3_thread_configure", {"threadId": thread, "modelSelection": moved})
    except T3Error as error:
        run.say(f"wait {subject}: the move off {instance} could not be made ({error})")
        return False
    line = f"rollover {subject}: {thread} moved from {instance} to {at}: {choice.why}"
    run.find(subject, "rollover", line)
    run.say(line)
    return True


def capped(run: Pass, client: Client, thread: str, template: str = "", row: str = "") -> int | None:
    """Return the Unix time the cap on a thread's instance resets, or None while that instance
    has headroom, once the thread has moved off it (`_rolled`), or where T3 Code did not say which
    instance the thread is on. A thread whose instance is not known is not held: the send that
    follows says what T3 Code said of it. For the user's own word, a cap the ledger read long ago
    and cannot read now holds nothing."""
    if not thread:
        return None
    try:
        chosen = selection_of(client, thread)
    except T3Error:
        return None
    instance = _instance(chosen)
    until = ledger.capped_until(ledger.read([instance]), instance, run.now)
    if not until:
        return None
    if template in USERS and (why := limits.unread(instance, run.now)):
        run.say(f"{thread}: its {template} message goes past a cap not read lately ({why})")
        return None
    if _rolled(run, client, thread, chosen, instance, row):
        return None
    return int(until.timestamp())


def busy(run: Pass, client: Client, thread: str, row: str = "") -> bool:
    """Say whether the thread has a turn running, as T3 Code says of it now, or was sent a
    message that needs `act` in this pass (`Pass.told`). A thread that T3 Code says nothing of is
    not busy: the send that follows says what T3 Code said of it."""
    return jsettings.thread_id(thread) in run.told or _turning(client, thread) is True


def idle(run: Pass, client: Client, thread: str, row: str = "") -> bool:
    """Say whether the thread has no turn running, as T3 Code says of it now. A thread that T3
    Code says nothing of is not idle: the send that follows says what T3 Code said of it."""
    return _turning(client, thread) is False


def _turning(client: Client, thread: str) -> bool | None:
    """Say whether the thread has a turn running, as T3 Code says of it now, or None where it
    says nothing of it."""
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return None
    return at_work([(read or {}).get("thread") or {}], settled_too=True)


def waiting(run: Pass, client: Client, thread: str, row: str) -> bool:
    """Say whether the thread waits on a test slot and is not woken yet: a woken one is `busy`
    while it takes up its wake."""
    thread = jsettings.thread_id(thread)
    return any(one.thread == thread and not one.woken for one in waiters.read(slot.locks_dir()))


def heard(run: Pass, row: str, brief: str) -> frozenset[meets.Waiver]:
    """Return the brief's `Waived:` lines whose word jbus checked as the user's own, or the bot's,
    of this row, waiving the line each names (`jmerge.rows.heard`): the waivers `jmerge` counts.
    jbus's own callers of `ready.short_of` pass them, so jbus judges a waived row as `jmerge`
    does."""
    checkout = run.project.checkout
    return frozenset(one for one in meets.waivers(brief) if not rows.heard(checkout, one, row))


def reviewing(run: Pass, client: Client, thread: str, row: str) -> bool:
    """Say whether the thread is the row's crew and its pull request waits on a review at its head
    that a reviewer the crew launched has not written: jmerge's judge (`ready.short_of`) says the
    review or a scoped review is not written, and the brief names a reviewer with no `## Review` yet
    (`review.reviewing`). A row with no open pull request in what this pass saw waits on no review,
    and a home told of the row (`jbus.wakes`, of a stall of that very review) waits on none."""
    pull = run.world.open.get(row) if run.world else None
    head = (pull or {}).get("headRefOid", "")
    if not head:
        return False
    brief = task_brief(run, row)
    if jsettings.thread_id(thread) != jsettings.thread_id(thread_of(run.home, row)):
        return False
    judged = ready.short_of(brief, head, heard(run, row, brief))
    unwritten = review.class_of(judged) in ("review", "scoped")
    return unwritten and review.reviewing(brief)


def on_hold(run: Pass, client: Client, thread: str, row: str) -> bool:
    """Say whether the row is held in the queue, as the table is now."""
    return bool((queue.fresh(run.state, row) or {}).get("held"))


RULES = (
    Rule("held", on_hold, frozenset(), FIXES),
    Rule("slot", waiting, WAKES | USERS),
    Rule("review", reviewing, WAKES | ASKS | USERS),
    Rule("busy", busy, USERS),
    Rule("idle", idle, frozenset(), STEERS),
)
"""Every rule that holds a message that needs `act`, in the order `send` asks them."""


def held(run: Pass, client: Client, thread: str, row: str, template: str, needs: Needs) -> str:
    """Return the name of the first rule of `RULES` that holds a message of this template to the
    thread about the row now, or nothing. A message that needs `decide` is held only by a rule that
    names its template in `only`."""
    if not thread:
        return ""
    rules = (
        rule
        for rule in RULES
        if template not in rule.spares
        and (template in rule.only if rule.only is not None else needs == "act")
    )
    return next((rule.name for rule in rules if rule.holds(run, client, thread, row)), "")


def hold(
    run: Pass, client: Client, *, thread: str, row: str, key: str, template: str, needs: Needs
) -> bool:
    """Say whether the outbox holds this message now: the thread's instance is capped, or a rule of
    `RULES` holds it. A held message gets one `wait` line and one `held` line in `outbox.jsonl`
    with its rule. `send` asks this first, and so does a sender that asks GitHub something before
    it sends (`rebase.held`), so it asks nothing for a message the outbox would hold."""
    until = capped(run, client, thread, template, row)
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
    mode = "auto" if template in STEERS else "queue"
    asked = {"threadId": thread, "message": text, "mode": mode, "clientRequestId": key}
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
    store.append_jsonl(run.state / FILE, [line])
