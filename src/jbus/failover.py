"""A thread that stopped on a usage limit goes on, on another instance of its pool, once.

A turn that ends `failed` on a usage limit is not a thread to carry on where it was: the
instance it ran on is capped until the window resets, and a carry-on sent there fails the same
way and spends one of `threads.CARRY_ONS`. So `failover` reads the limit from the run's items
(the `system_notice` itemId `...:<five_hour|seven_day>:<reset>`, the text where none has one),
writes it to the ledger (`jroles.ledger`) for the instance the run was on, and sends the
thread on to the instance `jroles.pool.choose` names in its pool:

- the pool is the role line's (`crew` for a crew, `home` for a home) where the thread's
  instance is in it, and the thread's instance alone where it is not. A thread is never moved
  to an instance its role's line does not name, so no work goes to a provider its role
  does not run;
- the first instance with headroom: the thread is put on it with `t3_thread_configure`, the
  model and the options (effort, fast mode) as `t3_thread_configuration` gave them, only the
  `instanceId` changed, and sent one queued carry-on. A thread already on it is only sent the
  carry-on. It works both ways: a thread capped on a later instance goes back to an earlier one
  with headroom, as one capped on the first goes on to the next;
- none, while every instance of the pool is capped: one `stall` event (user level) that names
  the first reset, and nothing sent. The first pass after that reset goes on as above.

Which threads: the crews the briefs name on a `Thread:` line that still owe something, and the
homes in a `home-id`, the root home's and each scope's. Each failed run is handled once: its
key, `failover|<thread>|<run>`, is kept in `sent.json` after the carry-on is queued, and the
stall has its own key, the reset. A crash between the two calls is safe: the configure sets the
same selection again, and the send has the key as its retry key. A slug read here is in
`Pass.limited`, and `threads.resume` leaves it alone: its carry-ons are not for a limit.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import jroles
from jbus import dispatch, mirror, read_json, threads, verbs
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World, unfinished
from jroles import ledger, pool

EVENTS = {"failover": "quiet"}
ITEMS = 12
CARRY_ON = (
    "jbus: your last turn stopped on a usage limit ({text}). This thread is now on {instance}, "
    "with the model and options it had. Carry on from where you stopped: {where} Do not start "
    "over."
)
CREW = (
    "read `{brief}` and your worktree's `git status` and `git log` first, keep what is committed."
)
HOME = "read your handoff and `jbus`'s view of your queue first."
_WORD = re.compile(r"\S+")


def _homes(run: Pass) -> set[str]:
    """The thread in each `home-id` under the project's home directory, the root's and every
    scope's."""
    found = set()
    for file in (run.home / "home-id", *run.home.glob("*/home-id")):
        try:
            word = _WORD.search(file.read_text(errors="replace"))
        except OSError:
            continue
        if word:
            found.add(word[0])
    return found


def _crews(run: Pass) -> dict[str, str]:
    """Each thread a brief names on its `Thread:` line, with the slug of that brief."""
    found = {}
    for path in sorted((run.home / "tasks").glob("*.md")):
        try:
            thread = dispatch.thread_of(path.read_text(errors="replace"))
        except OSError:
            continue
        if thread:
            found[thread] = path.stem
    return found


def _owes(run: Pass, world: World, slug: str) -> bool:
    """Whether a crew that failed still owes its task something: a pull request open, no
    Result yet, or a Result that leaves work. A task that merged or ended clean is left."""
    if slug in world.open:
        return True
    if slug in world.merged:
        return False
    try:
        result = mirror.last_result((run.home / "tasks" / f"{slug}.md").read_text(errors="replace"))
    except OSError:
        return False
    return not result or bool(unfinished(result))


def limit_of(client: Client, thread: dict[str, Any], run: Pass) -> tuple[ledger.Cap, str] | None:
    """The usage limit the thread's last run ended on and the instance that run was on, from
    the last items the thread wrote, or None. The run's instance is what is capped, not the
    thread's now: a thread moved by hand after the failure is on another one. A reset the
    text gives is read at the time the run ended, not at the pass."""
    items = thread.get("itemCount")
    asked = {
        "threadId": thread["threadId"],
        "view": "activity",
        "afterPosition": max(0, items - ITEMS) if isinstance(items, int) else 0,
        "limit": 50,
        "maxCharsPerItem": 600,
    }
    read = client.call("t3_thread_read", asked)
    latest = thread.get("latestRunId")
    run_of = next(
        (
            one
            for one in read.get("recentRuns") or []
            if isinstance(one, dict) and one.get("runId") == latest
        ),
        {},
    )
    last = [
        item
        for item in read.get("items") or []
        if isinstance(item, dict) and item.get("runId") in (None, latest)
    ]
    stamps = [
        run_of.get("completedAt"),
        *sorted((i.get("updatedAt") or "" for i in last), reverse=True),
    ]
    found = ledger.cap_of(last, _when(stamps) or run.now)
    return (found, run_of.get("providerInstanceId") or "") if found else None


def _when(stamps: list[Any]) -> datetime | None:
    """When the run ended, from the first of `stamps` that reads: a text's `resets 11pm` is
    of that day, whichever pass reads it."""
    for stamp in stamps:
        try:
            at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        return at if at.tzinfo else at.replace(tzinfo=UTC)
    return None


def pool_of(run: Pass, role: str, instance: str) -> tuple[str, ...]:
    """The pool a thread of `role` on `instance` moves in: the first of its role's lines that
    names the instance, else the instance alone."""
    try:
        chosen = pool.selections(role)
    except jroles.Refused as error:
        run.say(f"wait {run.project.name}: the role map gives {role} no pool ({error})")
        chosen = ()
    lines = [one.instances for one in chosen if instance in one.instances]
    return lines[0] if lines else (instance,)


def failover(run: Pass, client: Client, world: World) -> None:
    """Move each thread that failed on a usage limit to the instance that is not capped, and
    tell it to carry on. See the module for the rules."""
    crews, homes = _crews(run), _homes(run)
    try:
        said = client.call(
            "t3_thread_list",
            {
                "projectId": run.project.project_id,
                "settled": False,
                "statuses": ["failed"],
                "limit": 100,
            },
        )
    except T3Error as error:
        run.say(f"wait {run.project.name}: the failed threads could not be listed ({error})")
        return
    sent = read_json(run.state / "sent.json", [])
    for thread in said.get("threads") or []:
        at, ended = thread.get("threadId"), thread.get("latestRunId")
        slug = crews.get(at, "")
        if thread.get("status") != "failed" or not ended or thread.get("settled"):
            continue
        if thread.get("snoozed") or not (slug or at in homes):
            continue
        if slug and (slug in run.gated or not _owes(run, world, slug)):
            continue
        key = f"failover|{at}|{ended}"
        if key in sent:
            run.limited.add(slug)
            continue
        try:
            found = limit_of(client, thread, run)
            if found is None:
                continue
            run.limited.add(slug)
            handle(run, client, thread, slug, found, key)
        except T3Refused as error:
            what = "T3 Code refused the failover"
            run.gate(slug or at, what, str(error), key=f"{what} {at} {ended}")
        except T3Error as error:
            run.say(f"wait {slug or at}: the failover could not be made ({error})")


def handle(
    run: Pass,
    client: Client,
    thread: dict[str, Any],
    slug: str,
    found: tuple[ledger.Cap, str],
    key: str,
) -> None:
    cap, ran = found
    at, name = thread["threadId"], slug or "home"
    client.recipients = client.recipients | {at}
    configuration = client.call("t3_thread_configuration", {"threadId": at})
    selection = dict(configuration.get("modelSelection") or {})
    instance = selection.get("instanceId") or selection.get("provider") or ledger.BUILT_IN
    if not selection.get("model"):
        run.limited.discard(slug)
        return
    capped = ran or instance
    if ledger.write(cap.record(capped)):
        run.say(f"capped {capped}: {cap.window} until {cap.resets.isoformat()}")
    instances = pool_of(run, "crew" if slug else "home", instance)
    choice = pool.choose(instances, ledger.read(instances), run.now)
    if choice.instance is None:
        line = f"capped {name}: {choice.why}; it is sent on at the first reset"
        if run.find(slug or at, "stall", line, key=f"capped {choice.until.isoformat()}"):
            run.say(line)
        return
    if choice.instance != instance:
        client.moves[at] = (selection, instances)
        moved = {**selection, "instanceId": choice.instance}
        client.call("t3_thread_configure", {"threadId": at, "modelSelection": moved})
    where = CREW.format(brief=run.home / "tasks" / f"{slug}.md") if slug else HOME
    message = threads.resume_message(
        CARRY_ON,
        str(thread.get("title", "")),
        run.home,
        text=cap.text,
        instance=choice.instance,
        where=where,
        slug=slug,
    )
    asked = {"threadId": at, "message": message, "mode": "queue", "clientRequestId": key}
    client.call("t3_thread_send", asked)
    options = ", ".join(f"{o.get('id')}={o.get('value')}" for o in selection.get("options") or [])
    way = f"{instance} to {choice.instance}" if choice.instance != instance else instance
    line = (
        f"failover {name}: {cap.window} limit until {cap.resets.isoformat()}, carry-on on "
        f"{way}, model {selection['model']}{f', {options}' if options else ''}"
    )
    run.find(slug or at, "failover", line, key=key)
    run.box.mark(key)
    run.say(line)


STEPS = (
    verbs.Step(
        "tellers",
        55,
        "failover.failover",
        lambda half: failover(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
