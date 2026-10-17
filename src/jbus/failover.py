"""A thread that stopped on a usage limit goes on, on the other provider instance, once.

A turn that ends `failed` on "You've hit your weekly limit · resets Oct 18, 4pm" is not a
thread to carry on where it was: the instance it runs on is capped until the reset, and a
carry-on sent there fails the same way and spends one of `threads.CARRY_ONS`. So `failover`
reads the failure, keeps the reset as the instance's capped-until (`jroles.failover`, in
`capped.json` beside `pass.json`), and sends the thread on to the instance `choose` names:

- the primary (`jroles.failover.PRIMARY`) once its cap has passed, the fallback (`FALLBACK`)
  while it has not. The thread is put on it with the model and the options it had (effort,
  fast mode), read from `t3_thread_configuration`, and sent one queued carry-on;
- neither, while both are capped: one `capped` alert that names the earlier reset, and
  nothing sent. The pass that finds the earlier reset passed goes on as above.

Which threads: the crews the briefs name on a `Thread:` line that still owe something, and the
homes in a `home-id`. Each failed run is handled once: its key, `failover|<thread>|<run>`, is
kept in `sent.json` after the carry-on is queued. A crash between the two calls is safe: the
configure sets the same selection again, and the send has the key as its retry key. A thread
that is already on the instance `choose` names is not configured again. A slug read here is in
`Pass.limited`, and `threads.resume` leaves it alone: its carry-ons are not for a limit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jbus import dispatch, mirror, read_json, verbs
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World, unfinished
from jroles import failover as roles

EVENTS = {"failover": "quiet", "capped": "user"}
ITEMS = 12
CARRY_ON = (
    "jbus: your last turn stopped on a usage limit ({text}). This thread is now on {instance}, "
    "with the model and options it had. Carry on from where you stopped: {where} Do not start "
    "over."
)
CREW = (
    "read `tasks/{slug}.md` and your worktree's `git status` and `git log` first, keep what is "
    "committed."
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


def limit_of(client: Client, thread: dict[str, Any], run: Pass) -> tuple[roles.Limit, str] | None:
    """The usage limit the thread's last run ended on and the instance that run was on, from
    the last items the thread wrote, or None. The run's instance is what is capped, not the
    thread's now: a thread moved by hand after the failure is on the other one."""
    items = thread.get("itemCount")
    asked = {
        "threadId": thread["threadId"],
        "view": "activity",
        "afterPosition": max(0, items - ITEMS) if isinstance(items, int) else 0,
        "limit": 50,
        "maxCharsPerItem": 600,
    }
    read = client.call("t3_thread_read", asked)
    found = None
    ran = next(
        (
            one.get("providerInstanceId")
            for one in read.get("recentRuns") or []
            if isinstance(one, dict) and one.get("runId") == thread.get("latestRunId")
        ),
        None,
    )
    for item in read.get("items") or []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        if item.get("runId") not in (None, thread.get("latestRunId")):
            continue
        found = roles.read_limit(item["text"], run.now) or found
    return (found, ran or "") if found else None


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
    file = roles.path()
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
            handle(run, client, thread, slug, found, file, key)
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
    found: tuple[roles.Limit, str],
    file: Path,
    key: str,
) -> None:
    limit, ran = found
    at, name = thread["threadId"], slug or "home"
    client.recipients = client.recipients | {at}
    configuration = client.call("t3_thread_configuration", {"threadId": at})
    selection = dict(configuration.get("modelSelection") or {})
    instance = selection.get("instanceId") or roles.PRIMARY
    capped = ran or instance
    if instance not in roles.PAIR or capped not in roles.PAIR or not selection.get("model"):
        run.limited.discard(slug)
        return
    if roles.mark(file, capped, limit, run.now):
        run.say(f"capped {capped}: until {limit.until.isoformat()} ({limit.kind} limit)")
    choice = roles.choose(roles.load(file), run.now)
    if choice.instance is None:
        line = f"capped {name}: {choice.why}; it is sent on at the earlier reset"
        if run.find(slug or at, "capped", line, key=choice.until.isoformat()):
            run.say(line)
        return
    if choice.instance != instance:
        moved = {**selection, "instanceId": choice.instance}
        client.call("t3_thread_configure", {"threadId": at, "modelSelection": moved})
    where = CREW.format(slug=slug) if slug else HOME
    message = CARRY_ON.format(text=limit.text, instance=choice.instance, where=where)
    asked = {"threadId": at, "message": message, "mode": "queue", "clientRequestId": key}
    client.call("t3_thread_send", asked)
    options = ", ".join(f"{o.get('id')}={o.get('value')}" for o in selection.get("options") or [])
    way = f"{instance} to {choice.instance}" if choice.instance != instance else instance
    line = (
        f"failover {name}: {limit.kind} limit until {limit.until.isoformat()}, carry-on on "
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
