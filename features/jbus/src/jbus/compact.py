"""This module sends a thread `/compact` under two rules: a crew once, when its pull request has
opened and its turn has ended, and a home, a crew or a scout each time its context reaches its
role's ceiling: 430k for a home, 180k for a crew and 330k for a scout (`CEILINGS`). A crew is
compacted at its pull request too, under the first rule, at its own floor of 100k.

T3 Code runs a compaction for any user message that is `/compact`: po-compact-probe sent one to a
finished crew at 137k, and its next call sent 38.9k with the brief still known to it. Each rule
reads the thread's last main call from jbus's telemetry store (`last_call`), and sends only to a
thread that T3 Code says has no turn running or queued (`idle`), so no task is cut in the middle.
A thread the store holds no call of yet waits for a pass whose build has read one, since a
compaction run blind may be a run for nothing.

A crew is at about 160k tokens when its pull request opens, under T3 Code's floor for an idle
compaction, so it is never compacted there, and each call it makes after the pull request (a failed
check, a conflict, a comment) sent 208.7k on average (po-crew-handoff-scout, 2026-11-09). `tell`
sends it to a row's crew thread when, in this pass:

- the row's pull request is open (`World.open`): a merged or closed one gets none;
- the brief's last Result that names a pull request names this one's URL;
- the thread is the row's crew, as its title says (`roles.role_of`), and never a home, a scout or
  a reviewer;
- the thread is idle: a crew still at work on its pull request is compacted at the first pass
  after its turn ends;
- the thread's last call sent at least `FLOOR` tokens: a small context has nothing to gain.

Its key is `compact|<slug>`, so a row is compacted once.

A home is never compacted by T3 Code while it is busy: T3 Code compacts only a thread whose last
run completed, two minutes before its cache expires, and a home woken every few minutes never gets
there (the polish home climbed to 630k on 2026-11-09, po-worse-home-context). A crew or a scout
that sits idle above its ceiling, waiting on a review or a check, replays its whole context on each
call it is woken for. `tell_at_ceiling` sends `/compact` to each thread of a role (`threads`) that
is idle and whose last call sent its role's ceiling or more:

- a home is each home thread of the project (`jbus.t3.homes`): the root home's and each scope's;
- a crew or a scout is each thread of the project that T3 Code lists, whose title gives that role
  (`roles.role_of`): T3 Code lists no archived thread, and `jbus.threads.settle` archives the
  threads of a finished task or scout, which are woken no more and have nothing to save. A row's
  status cannot say this: a scout that sits idle has written its Report, so its row is `done`.

Its key is `compact|<role>|<thread>|<at>`, `<at>` that call's time: a thread climbs many times, and
the store keeps no call for a compaction itself, so the key sends once for a climb, and again only
once a newer call is at the ceiling. A thread whose last call in the store is older than its last
`/compact`, under either rule, is skipped too: the store is built by a chore that can trail a pass,
and a call it reads late from before the compaction is not a new climb, and a crew compacted at its
pull request is not compacted again for the same call. A thread this pass already told something
waits, so a thread told something every pass is not compacted; the step runs before `wakes.tell`,
so it is the wake that waits a pass behind a `/compact` (`outbox.busy`).

Each message goes through `outbox.send`, under the template `compact`, and its key is marked in
`sent.json` once it went or T3 Code refused it. A pass that sends nothing writes no key, so a later
pass asks again. The outbox's own rules still hold it (`outbox.RULES`): a thread that this pass
already told something waits for the next pass."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

import jsettings
from jbriefs import parse
from jbus import crewthread, outbox, roles, t3, telemetry, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, at_work, task_brief

TEMPLATE = "compact"
MESSAGE = "/compact"
FLOOR = 100_000
"""The tokens a crew's last call must have sent for a compaction to be worth its run."""
CEILINGS = {"home": 430_000, "crew": 180_000, "scout": 330_000}
"""The tokens a thread's last call may send, by its role, before it is compacted: the user's
ceilings of 2026-11-12."""
_LAST = (
    "SELECT c.input + c.cache_write + c.cache_read, c.at FROM sessions s "
    "JOIN calls c USING (provider, session) WHERE s.thread = ? "
    "AND c.agent IS NULL ORDER BY c.at DESC LIMIT 1"
)

_AT = re.compile(r'"at": "([^"]+)"')


@dataclass(frozen=True)
class Last:
    """A thread's last main call: the tokens it sent and its time, as the store holds them."""

    tokens: int
    at: str


def key(slug: str) -> str:
    return f"{TEMPLATE}|{slug}"


def ceiling_key(role: str, thread: str, at: str) -> str:
    return f"{TEMPLATE}|{role}|{jsettings.thread_id(thread)}|{at}"


def threads(run: Pass, client: Client, role: str) -> set[str]:
    """The threads of the project of a role that has a ceiling: see the module. Raises what
    `t3.listed` raises."""
    if role == "home":
        return t3.homes(run.home)
    prefix = next(one.prefix for one in roles.ROLES if one.name == role)
    listed = t3.listed(client, run.project.project_id, titleContains=prefix)
    return {
        jsettings.thread_id(str(one["threadId"]))
        for one in listed
        if one.get("threadId") and roles.role_of(str(one.get("title", "")))[0] == role
    }


def last_call(run: Pass, thread: str) -> Last | None:
    """Return the thread's last main call, as the telemetry store holds it, read through its
    index of sessions by thread, or None where the store holds no call of the thread, or is not
    there or cannot be read: opened read only, a store that is not there raises as one that cannot
    be read does."""
    where = telemetry.path(run.config)
    try:
        with sqlite3.connect(f"file:{where}?mode=ro", uri=True, timeout=1) as store:
            found = store.execute(_LAST, (jsettings.thread_id(thread),)).fetchone()
    except sqlite3.Error:
        return None
    return Last(int(found[0]), str(found[1])) if found else None


def idle(client: Client, thread: str, role: str) -> bool:
    """Say whether T3 Code says the thread is one of this role with no turn running or queued."""
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return False
    found = (read or {}).get("thread") or {}
    titled, _ = roles.role_of(str(found.get("title", "")))
    return titled == role and bool(found.get("status")) and not at_work([found], settled_too=True)


def _when(stamp: str) -> datetime:
    """A time as the store (`...Z`) or the outbox (`+00:00`) writes it."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def compacted(run: Pass, thread: str) -> datetime | None:
    """Return when this project's outbox last sent the thread `/compact`, under either rule, or
    None. A line of `outbox.jsonl` is parsed only where it holds the template `compact` and `went`
    `sent`."""
    path = run.state / outbox.FILE
    want = jsettings.thread_id(thread)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sent = [
        json.loads(line)
        for line in text.splitlines()
        if f'"template": "{TEMPLATE}"' in line and '"went": "sent"' in line
    ]
    found = [
        str(one["at"])
        for one in sent
        if jsettings.thread_id(str(one.get("thread") or "")) == want and one.get("at")
    ]
    return _when(found[-1]) if found else None


def tell(run: Pass, client: Client, world: World) -> None:
    """Send each crew whose pull request is open and named by its Result `/compact`, once."""
    sent = run.box.sent()
    for slug, pull in world.open.items():
        if key(slug) in sent:
            continue
        thread = crewthread.crew(run, slug) if crewthread.tended(run, slug) else ""
        named = parse.brief(slug, task_brief(run, slug)).pull_request
        url = str(pull.get("url") or "").rstrip("/")
        if not thread or not named or not url or (named.url or "").rstrip("/") != url:
            continue
        if not idle(client, thread, "crew"):
            continue
        last = last_call(run, thread)
        if last is None or last.tokens < FLOOR:
            continue
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=slug,
                key=key(slug),
                text=MESSAGE,
                template=TEMPLATE,
                needs="act",
            )
        except T3Refused as error:
            run.say(f"compact {slug}: T3 Code refused it ({error}), so it is not sent again")
            run.box.mark(key(slug))
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be compacted ({error})")
            continue
        if went:
            run.box.mark(key(slug))
            line = f"#{pull['number']}, its last call at {last.tokens:,} tokens"
            run.say(f"compact {slug}: sent its crew /compact ({line})")


def tell_at_ceiling(run: Pass, client: Client, role: str) -> None:
    """Send each idle thread of the role whose last call sent the role's ceiling or more
    `/compact`, once for that call."""
    sent = set(run.box.sent())
    ceiling = CEILINGS[role]
    try:
        found = threads(run, client, role)
    except T3Error as error:
        run.say(f"wait {run.project.name}: T3 Code did not list its {role} threads ({error})")
        return
    for thread in sorted(found):
        last = last_call(run, thread)
        if last is None or last.tokens < ceiling:
            continue
        mark = ceiling_key(role, thread, last.at)
        if mark in sent:
            continue
        was = compacted(run, thread)
        if was is not None and _when(last.at) <= was:
            continue
        if not idle(client, thread, role):
            continue
        name = run.project.name
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=name,
                key=mark,
                text=MESSAGE,
                template=TEMPLATE,
                needs="act",
            )
        except T3Refused as error:
            run.say(
                f"compact {name}: T3 Code refused {role} {thread}'s, so it is not sent again "
                f"({error})"
            )
            run.box.mark(mark)
            continue
        except T3Error as error:
            run.say(f"wait {name}: {role} {thread} could not be compacted ({error})")
            continue
        if went:
            run.box.mark(mark)
            tokens = f"{last.tokens:,}"
            run.say(
                f"compact {name}: sent {role} {thread} /compact (its last call at {tokens} tokens)"
            )


STEPS = (
    verbs.Step(
        "after-expedite",
        35,
        "compact.tell",
        lambda half: tell(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
    verbs.Step(
        "after-expedite",
        36,
        "compact.ceilings",
        lambda half: [tell_at_ceiling(half.run, half.client, role) for role in CEILINGS],
        ("client",),
    ),
)
