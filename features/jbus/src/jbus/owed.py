"""An ask of the user's whose turn stopped on a usage limit or an auth error is owed: jbus keeps it,
with its cause, and sends it again once, when the account frees.

T3 Code ends such a turn `failed` with one line, as `You've hit your weekly limit · resets 4pm` or
`Failed to authenticate: OAuth session expired`, and nothing then runs what the user asked. The
week audit (`scouts/week-audit-a-lost-asks.md`) found 5 such asks. `sweep` runs first in each pass,
before any message of that pass can start a new turn on the thread, and looks at each failed thread
of the project once a run (`looked`). A scratch home's threads get the same look in a chore.

An ask is a `user_message` the user wrote (`createdBy: user`) in a run whose last items name the
stop (`stop_of`), and that stopped within `RECENT` of the look: the first pass on a machine, or
after jbus was down, sends no one's old words into a thread that has long moved on. What jbus or a
home sent a thread is no ask, since its sender asks again by itself, but for the user's own word
that jbus carried to a home (`jbus.word`, `CARRIED`): no sender asks again for that. Each
ask is one record of `owed.json` in the project's state, with the thread, the run, the words, the
cause, the line T3 Code ended on, the instance the run was on and when it frees. The record is what
`jbus status` shows (`blocked`), and the `ask-owed` and `ask-resent` events go in the project's log.

The account frees when:

- a limit: the thread's instance is not capped. `outbox.send` holds the message until then, and
  `sweep` writes the cap into the ledger for the run's instance. A thread moved to an instance with
  headroom is free at once. A thread on which `jbus.failover` acts is its to carry on: its carry-on
  quotes the ask (`quoted`), and `taken` closes the record.
- an auth error: the thread is on another instance now, the account home's credentials were written
  after the stop and hold a live token (`jgauge.limits.renewed`), or, for an instance with no such
  home, a thread of the project has completed a turn on it since.

Each ask is sent once. Its retry key, `ask|<thread>|<message>|<try>`, is in `sent.json` and is T3
Code's `clientRequestId`, so a crash between the send and the mark sends nothing twice. A record
that went is `sent` and is never sent again, unless the turn it started stopped on the limit or the
auth error too, since that turn ran nothing: then it is owed again, under the next try's key.

An ask the user repeated is not sent. It is closed as `repeated` when a later message of theirs in
the thread says the same words or asks to go on (`RESUME`), and that message's turn completed. A
later message on something else does not close it, since it does not answer it: 0f8b3189 was left
behind that way, under a new question, for 3 days. The re-send says when the ask was made and tells
the thread to say so in one line if the thread has overtaken it. A settled, archived or deleted
thread owes nothing. jbus cannot see a repeat in another thread, except an ask owed in the same
project: the older of two with the same words is closed.

What goes out is the user's own words with one frame around them, to the thread they were said in.
jbus adds no ask of its own.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbus import outbox, t3, verbs, word
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused, listed
from jgauge import limits
from jroles import ledger
from jsettings import store

EVENTS = {"ask-owed": "quiet", "ask-resent": "quiet"}
FILE = "owed.json"
TEMPLATE = "ask"
LIMIT, AUTH = "usage limit", "auth error"
OWED, SENT, REPEATED, ENDED = "owed", "sent", "repeated", "ended"
WINDOW, PAGES, CHARS = 100, 5, 600
RECENT = timedelta(days=1)
TAIL = ("system_notice", "assistant_message", "error")
"""The kinds of item that can name the stop. Only the last three items of a run are read, so a
command's output or the user's own words that quote a limit are no stop."""
RESUME = frozenset(
    {"continue", "continue where you left off", "go on", "keep going", "resume", "retry"}
)
"""What the user says, or T3 Code's button says, to take the last turn up again."""
MARK = "jbus: the user's ask below stopped"
MESSAGE = (
    MARK + " on a {cause} ({line}) before it was answered, at {stopped}, and jbus sends it again "
    "once, word for word. They asked it at {at}. If this thread has since answered or overtaken "
    "it, say so in one line and do nothing else.\n\n{text}"
)
_AUTH = re.compile(
    r"failed to authenticate|could not authenticate|authentication failed"
    r"|authentication token is expired|oauth session expired",
    re.I,
)
_WORDS = re.compile(r"[^\w/]+")
_HEAD = word.MESSAGE[: word.MESSAGE.index("{at}")]
CARRIED = re.compile("^" + re.escape(_HEAD).replace(re.escape("{by}"), ".+?"))
"""How a word of the user's that `jbus.word` carried to a home begins."""
_CAP_RULE = "cap: until "


@dataclass
class Ask:
    """`Ask` is one record of `owed.json`. `position` is the ask's place in its thread's items, and
    `state` is `owed`, `sent`, `repeated` or `ended`."""

    id: str
    thread: str
    row: str
    run: str
    text: str
    at: str
    cause: str
    line: str
    instance: str
    until: str
    stopped: str
    position: int = 0
    state: str = OWED
    tries: int = 1
    closed: str = ""

    @property
    def key(self) -> str:
        return f"{TEMPLATE}|{self.thread}|{self.id}|{self.tries}"

    def message(self) -> str:
        return MESSAGE.format(**asdict(self))


@dataclass(frozen=True)
class Stop:
    """`Stop` is what ended a run: its cause, the line it ended on, and a limit's cap."""

    cause: str
    line: str
    cap: ledger.Cap | None = None


def when(stamps: list[Any]) -> datetime | None:
    """Return when the run ended, from the first of `stamps` that parses. A text's
    `resets 11pm` means 11pm of that day, whichever pass reads it."""
    for stamp in stamps:
        try:
            at = jsettings.when(str(stamp))
        except ValueError:
            continue
        return at if at.tzinfo else at.replace(tzinfo=UTC)
    return None


def stop_of(items: list[Mapping[str, Any]], now: datetime) -> Stop | None:
    """Return what the last items of a failed run name as its stop, or None for any other failure,
    such as a stream that closed, which is no cap and no sign-in."""
    tail = [item for item in items[-3:] if item.get("type") in TAIL]
    cap = ledger.cap_of(tail, now)
    if cap:
        return Stop(LIMIT, cap.text, cap)
    for item in tail:
        text = str(item.get("text") or "")
        if _AUTH.search(text):
            return Stop(AUTH, text.strip().splitlines()[0])
    return None


def _words(text: str) -> str:
    return _WORDS.sub(" ", text.lower()).strip()


def _users(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the user's own messages among the items: typed by them, or their word as jbus
    carried it."""
    return [
        item
        for item in items
        if item.get("type") == "user_message"
        and (item.get("createdBy") == "user" or CARRIED.match(str(item.get("text") or "")))
        and not _words(str(item.get("text") or "")).startswith("/compact")
    ]


def load(state: Path) -> list[Ask]:
    known = {one.name for one in fields(Ask)}
    kept = store.read_dict(state / FILE).get("asks") or []
    return [Ask(**{k: v for k, v in one.items() if k in known}) for one in kept]


def _looked(state: Path) -> dict[str, str]:
    return store.read_dict(state / FILE).get("looked") or {}


def _save(state: Path, asks: list[Ask], looked: dict[str, str]) -> None:
    kept = {"asks": [asdict(one) for one in asks], "looked": looked}
    store.write_json(state / FILE, kept)


def _whole(client: Client, thread: str, item: dict[str, Any]) -> str:
    """Return the whole text of an item that a read cut off."""
    text, offset = str(item.get("text") or ""), item.get("nextTextOffset")
    while item.get("textTruncated") and offset is not None:
        asked = {
            "threadId": thread,
            "itemId": item["itemId"],
            "textOffset": offset,
            "maxCharsPerItem": 20000,
        }
        (more,) = client.call("t3_thread_read", asked).get("items") or [{}]
        text, offset = text[: int(offset)] + str(more.get("text") or ""), more.get("nextTextOffset")
    return text


def _last_run(
    client: Client, thread: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the items of the thread's last run and that run, reading back from the thread's end
    until a read reaches an item of an older run."""
    latest, items = thread["latestRunId"], []
    count = thread.get("itemCount")
    after = max(0, count - WINDOW) if isinstance(count, int) else 0
    runs: list[dict[str, Any]] = []
    for _ in range(PAGES):
        read = client.call(
            "t3_thread_read",
            {
                "threadId": thread["threadId"],
                "view": "activity",
                "afterPosition": after,
                "limit": WINDOW,
                "maxCharsPerItem": CHARS,
                "runLimit": 5,
            },
        )
        runs = runs or read.get("recentRuns") or []
        got = [one for one in read.get("items") or [] if isinstance(one, dict)]
        items = got + items
        if after == 0 or any(one.get("runId") not in (latest, None) for one in got):
            break
        after = max(0, after - WINDOW)
    run_of = next((one for one in runs if isinstance(one, dict) and one.get("runId") == latest), {})
    return [one for one in items if one.get("runId") in (None, latest)], run_of


def _record(run: Pass, client: Client, thread: dict[str, Any], asks: list[Ask], left: bool) -> None:
    """Keep each ask of the thread's last run if that run stopped on a limit or an auth error, and
    owe again what a re-send of ours asked if its turn stopped too."""
    at = thread["threadId"]
    items, run_of = _last_run(client, thread)
    ended = when(
        [
            run_of.get("completedAt"),
            *sorted((str(one.get("updatedAt") or "") for one in items), reverse=True),
        ]
    )
    stop = stop_of(items, ended or run.now)
    if stop is None or run.now - (ended or run.now) > RECENT:
        return
    instance = run_of.get("providerInstanceId") or ledger.BUILT_IN
    until = stop.cap.resets.isoformat() if stop.cap else ""
    stopped = (ended or run.now).isoformat()
    ours = [
        str(one.get("text") or "")
        for one in items
        if one.get("type") == "user_message" and MARK in str(one.get("text") or "")
    ]
    owes = False
    for ask in asks:
        if ask.thread == at and ask.state == SENT and any(ask.text in text for text in ours):
            ask.state, ask.closed, ask.tries = OWED, "", ask.tries + 1
            ask.cause, ask.line, ask.until, ask.stopped = stop.cause, stop.line, until, stopped
            ask.instance = instance
            owes = True
    for item in _users(items):
        made = item.get("messageId") or item.get("itemId")
        text = _whole(client, at, item)
        here = [one for one in asks if one.thread == at and one.state == OWED]
        same = {_words(one.text) for one in here}
        if any(one.id == made for one in asks) or _words(text) in same:
            continue
        if here and _words(text) in RESUME:
            continue
        ask = Ask(
            str(made),
            at,
            str(thread.get("title") or at),
            str(thread["latestRunId"]),
            text,
            str(item.get("updatedAt") or stopped),
            stop.cause,
            stop.line,
            instance,
            until,
            stopped,
            item.get("position") or 0,
        )
        for older in asks:
            if older.state == OWED and _words(older.text) == _words(text):
                older.state, older.closed = REPEATED, run.now.isoformat()
        asks.append(ask)
        frees = until or f"when {instance} is signed in again"
        line = f"owed {ask.row}: its ask stopped on a {stop.cause} ({stop.line}), frees {frees}"
        run.find(at, "ask-owed", line, key=ask.id)
        run.say(line)
        owes = True
    if owes and stop.cap and not left and ledger.write(stop.cap.record(instance)):
        run.say(f"capped {instance}: {stop.cap.window} until {stop.cap.resets.isoformat()}")


def _since(client: Client, ask: Ask) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    """Return the thread, its items after the ask, and the status of each of its recent runs."""
    items: list[dict[str, Any]] = []
    after, read = ask.position, {}
    for _ in range(PAGES):
        read = client.call(
            "t3_thread_read",
            {
                "threadId": ask.thread,
                "view": "activity",
                "afterPosition": after,
                "limit": WINDOW,
                "maxCharsPerItem": CHARS,
                "runLimit": 50,
            },
        )
        items += [one for one in read.get("items") or [] if isinstance(one, dict)]
        if not read.get("hasMore"):
            break
        after = read.get("nextPosition") or after + WINDOW
    ids = [one.get("messageId") or one.get("itemId") for one in items]
    if ask.id in ids:
        items = items[ids.index(ask.id) + 1 :]
    runs = {str(one.get("runId")): str(one.get("status")) for one in read.get("recentRuns") or []}
    return read.get("thread") or {}, items, runs


def _repeated(ask: Ask, items: list[dict[str, Any]], runs: dict[str, str]) -> bool:
    """Say whether a later message of the user's asks this again and its turn completed. A turn
    still going says nothing yet, and a turn that stopped too ran nothing."""
    said = _words(ask.text)
    return any(
        _words(str(one.get("text") or "")) in (said, *RESUME)
        and runs.get(str(one.get("runId"))) == "completed"
        for one in _users(items)
    )


def _renewed(run: Pass, client: Client, ask: Ask) -> bool:
    """Say whether the account of an ask that stopped on an auth error is signed in again."""
    if outbox.instance_of(client, ask.thread) != ask.instance:
        return True
    stopped = when([ask.stopped]) or run.now
    try:
        homes = {one.instance: one for one in limits.homes()}
    except limits.Stale:
        homes = {}
    if ask.instance in homes:
        return limits.renewed(homes[ask.instance], stopped, run.now)
    done = listed(client, run.project.project_id, statuses=["completed"], settled=False)
    return any(
        one.get("providerInstanceId") == ask.instance
        and (when([one.get("updatedAt")]) or stopped) > stopped
        for one in done
    )


def _settle(run: Pass, client: Client, ask: Ask, carried: bool) -> None:
    """Close the ask if nothing is owed any more, and otherwise send it if its account is free."""
    try:
        thread, items, runs = _since(client, ask)
    except T3Refused as error:
        if not t3.GONE.search(str(error)):
            run.say(f"wait {ask.row}: T3 Code refused to read its thread ({error})")
            return
        ask.state, ask.closed = ENDED, run.now.isoformat()
        return
    if thread.get("settled") or thread.get("archived"):
        ask.state, ask.closed = ENDED, run.now.isoformat()
        return
    if _repeated(ask, items, runs):
        ask.state, ask.closed = REPEATED, run.now.isoformat()
        run.say(f"owed {ask.row}: the user asked again, so its ask is not sent")
        return
    if thread.get("snoozed") or (carried and thread.get("status") == "failed"):
        return
    if ask.key in run.box.sent():
        ask.state, ask.closed = SENT, run.now.isoformat()
        return
    if ask.cause == AUTH and not _renewed(run, client, ask):
        run.say(f"wait {ask.row}: its ask waits for {ask.instance} to be signed in again")
        return
    if outbox.send(
        run,
        client,
        thread=ask.thread,
        row=ask.row,
        key=ask.key,
        text=ask.message(),
        template=TEMPLATE,
        needs="act",
    ):
        run.box.mark(ask.key)
        ask.state, ask.closed = SENT, run.now.isoformat()
        line = f"resent {ask.row}: its ask that stopped on a {ask.cause}"
        run.find(ask.thread, "ask-resent", line, key=ask.key)
        run.say(line)


def failed(run: Pass, client: Client) -> list[dict[str, Any]]:
    """Return the project's failed threads that are not settled and have a run, listed once a
    pass (`Pass.failed`). Raise what `Client.call` raises where T3 Code gives no list."""
    if run.failed is None:
        said = client.call(
            "t3_thread_list",
            {
                "projectId": run.project.project_id,
                "settled": False,
                "statuses": ["failed"],
                "limit": 100,
            },
        )
        run.failed = [
            one
            for one in said.get("threads") or []
            if one.get("status") == "failed" and one.get("latestRunId") and not one.get("settled")
        ]
    return run.failed


def sweep(
    run: Pass,
    client: Client,
    movers: Callable[[list[dict[str, Any]]], Mapping[str, Any]] = lambda _: {},
) -> None:
    """Keep what each failed thread's last run owes, then close or send each ask still owed.
    `movers` names the threads `jbus.failover` may carry on: an ask on such a thread, stopped on a
    limit, is left to the carry-on while the thread stays failed. See the module for the rules."""
    asks, looked = load(run.state), _looked(run.state)
    try:
        listed = failed(run, client)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the failed threads could not be listed ({error})")
        listed = []
    carried = set(movers(listed))
    for thread in listed:
        at = thread["threadId"]
        if looked.get(at) == thread["latestRunId"]:
            continue
        try:
            _record(run, client, thread, asks, at in carried)
        except T3Error as error:
            run.say(f"wait {thread.get('title')}: its last run could not be read ({error})")
            continue
        looked[at] = thread["latestRunId"]
    looked = {
        one["threadId"]: looked[one["threadId"]] for one in listed if one["threadId"] in looked
    }
    _save(run.state, asks, looked)
    for ask in asks:
        if ask.state != OWED:
            continue
        try:
            _settle(run, client, ask, ask.cause == LIMIT and ask.thread in carried)
        except T3Refused as error:
            what = "T3 Code refused an owed ask"
            run.gate(ask.thread, what, str(error), key=f"{what} {ask.key}")
        except T3Error as error:
            run.say(f"wait {ask.row}: its owed ask could not be sent ({error})")
        _save(run.state, asks, looked)


def quoted(run: Pass, thread: str) -> str:
    """Return what `jbus.failover`'s carry-on adds for the asks the thread owes: each one's words
    and frame, or nothing."""
    return "".join(
        f"\n\n{ask.message()}"
        for ask in load(run.state)
        if ask.thread == thread and ask.state == OWED
    )


def taken(run: Pass, thread: str) -> None:
    """Close the asks of a thread whose carry-on quoted them."""
    asks = load(run.state)
    for ask in asks:
        if ask.thread == thread and ask.state == OWED:
            ask.state, ask.closed = SENT, run.now.isoformat()
    _save(run.state, asks, _looked(run.state))


def _held(state: Path) -> list[dict[str, Any]]:
    """Return the last line of each key of `outbox.jsonl`'s tail, by the key."""
    try:
        with open(state / outbox.FILE) as file:
            tail = deque(file, maxlen=2000)
    except OSError:
        return []
    last: dict[str, dict[str, Any]] = {}
    for line in tail:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        last[str(one.get("key"))] = one
    return list(last.values())


def blocked(
    state: Path, user: jsettings.Settings, now: datetime, sent: list[str]
) -> list[dict[str, str]]:
    """Return what `jbus status` shows of each row or ask a cap holds now: what waits, the cause and
    when it frees. They are the asks still owed, the messages the outbox held at a cap that has
    not reset, and the launches and failovers that raised a stall for one, by the keys `sent` that
    the project's box has sent."""
    found = []
    for ask in load(state):
        if ask.state == OWED:
            at = when([ask.until])
            frees = user.stamp(at) if at else f"when {ask.instance} is signed in again"
            what = f"the ask {ask.text[:60]!r}"
            found.append({"row": ask.row, "what": what, "cause": ask.line, "frees": frees})
    for one in _held(state):
        rule = str(one.get("rule") or "")
        at = when([rule.removeprefix(_CAP_RULE)]) if rule.startswith(_CAP_RULE) else None
        if one.get("went") == "held" and at and at > now and one.get("template") != TEMPLATE:
            what = f"its {one.get('template')} message"
            found.append(
                {
                    "row": str(one.get("row")),
                    "what": what,
                    "cause": "usage cap",
                    "frees": user.stamp(at),
                }
            )
    for key in sent:
        kind, _, rest = str(key).partition("|")
        row, _, why = rest.partition("|")
        at = when([why.removeprefix("capped ")]) if why.startswith("capped ") else None
        if kind == "stall" and at and at > now:
            found.append(
                {
                    "row": row,
                    "what": "its launch or carry-on",
                    "cause": "usage cap",
                    "frees": user.stamp(at),
                }
            )
    return found


def _scratch(
    config: jbus.Config, client: Client | None, now: datetime, say: Callable[[str], None]
) -> None:
    """Sweep the scratch homes' projects, one look for each. A scratch home is not one of the
    projects a pass works through, and it is where no-project threads run."""
    if client is None:
        return
    seen = set()
    for one in config.scratch:
        if one.project_id not in seen:
            seen.add(one.project_id)
            sweep(Pass(config, one.addressee(), now, say), client)


CHORES = (verbs.Chore(25, "the asks the scratch homes owe", _scratch),)
