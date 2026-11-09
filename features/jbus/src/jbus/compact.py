"""This module sends a crew `/compact` once, when its pull request has opened and its turn has
ended.

A crew is at about 160k tokens when its pull request opens, under T3 Code's 200k floor for an idle
compaction, so it is never compacted there, and each call it makes after the pull request (a failed
check, a conflict, a comment) sent 208.7k on average (po-crew-handoff-scout, 2026-11-09). T3 Code
runs a compaction for any user message that is `/compact`: po-compact-probe sent one to a finished
crew at 137k, and its next call sent 38.9k with the brief still known to it. So jbus sends that
message once, at the first pass where it is safe.

`tell` sends it to a row's crew thread when, in this pass:

- the row's pull request is open (`World.open`): a merged or closed one gets none;
- the brief's last Result that names a pull request names this one's URL;
- the thread is the row's crew, as its title says (`roles.role_of`), and never a home, a scout or
  a reviewer;
- T3 Code says the thread has no turn running or queued (`watch.at_work`): a crew still at work
  on its pull request is compacted at the first pass after its turn ends;
- the thread's last call, as jbus's telemetry store holds it, sent at least `FLOOR` tokens: a
  small context has nothing to gain, and a thread the store holds no call of yet waits for a pass
  whose build has read one, since a compaction run blind may be a run for nothing. The pass builds
  the store each time (`jbus.telemetry`), so a crew's calls are in it within a pass or two.

The message goes through `outbox.send`, under the template `compact` and the key `compact|<slug>`,
which `sent.json` keeps once it went, so a row is compacted once. A pass that sends nothing writes
no key, so a later pass asks again. The outbox's own rules still hold it (`outbox.RULES`): a
thread that this pass already told something waits for the next pass."""

from __future__ import annotations

import sqlite3

import jsettings
from jbriefs import parse
from jbus import outbox, roles, telemetry, verbs
from jbus.passes import Pass
from jbus.rebase import crew
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, at_work, task_brief

TEMPLATE = "compact"
MESSAGE = "/compact"
FLOOR = 100_000
"""The tokens a thread's last call must have sent for a compaction to be worth its run."""
_LAST = (
    "SELECT c.input + c.cache_write + c.cache_read FROM calls c JOIN sessions s "
    "USING (provider, session) WHERE s.thread = ? AND c.agent IS NULL ORDER BY c.at DESC LIMIT 1"
)


def key(slug: str) -> str:
    return f"{TEMPLATE}|{slug}"


def last_call(run: Pass, thread: str) -> int | None:
    """Return the tokens the thread's last call sent, as the telemetry store holds it, or None
    where the store holds no call of the thread, or is not there or cannot be read: opened read
    only, a store that is not there raises as one that cannot be read does."""
    where = telemetry.path(run.config)
    try:
        with sqlite3.connect(f"file:{where}?mode=ro", uri=True, timeout=1) as store:
            found = store.execute(_LAST, (jsettings.thread_id(thread),)).fetchone()
    except sqlite3.Error:
        return None
    return int(found[0]) if found else None


def idle_crew(client: Client, thread: str) -> bool:
    """Say whether T3 Code says the thread is a crew's with no turn running or queued."""
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return False
    found = (read or {}).get("thread") or {}
    role, _ = roles.role_of(str(found.get("title", "")))
    return role == "crew" and bool(found.get("status")) and not at_work([found], settled_too=True)


def tell(run: Pass, client: Client, world: World) -> None:
    """Send each crew whose pull request is open and named by its Result `/compact`, once."""
    sent = run.box.sent()
    for slug, pull in world.open.items():
        if key(slug) in sent:
            continue
        thread = crew(run, slug)
        named = parse.brief(slug, task_brief(run, slug)).pull_request
        url = str(pull.get("url") or "").rstrip("/")
        if not thread or not named or not url or (named.url or "").rstrip("/") != url:
            continue
        if not idle_crew(client, thread):
            continue
        tokens = last_call(run, thread)
        if tokens is None or tokens < FLOOR:
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
            line = f"#{pull['number']}, its last call at {tokens:,} tokens"
            run.say(f"compact {slug}: sent its crew /compact ({line})")


STEPS = (
    verbs.Step(
        "after-expedite",
        35,
        "compact.tell",
        lambda half: tell(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
