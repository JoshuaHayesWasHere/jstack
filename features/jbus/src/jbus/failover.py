"""When a thread stops on a usage limit or a login lapse, `failover` moves it to another
instance of its pool, and the thread carries on there.

A turn that ends `failed` on a usage limit cannot carry on where it was. The instance it ran
on is capped until the window resets, and a carry-on sent there fails the same way and spends
one of `threads.CARRY_ONS`. So `failover` reads the limit from the run's items: the
`system_notice` itemId `...:<five_hour|seven_day>:<reset>`, or the items' text where no
item has such an id. It writes the limit to the ledger (`jroles.ledger`) for the instance
the run was on. Then it sends the thread on to the instance of the thread's pool that
`jroles.pool.choose` names:

- The pool is the first line of the role map that names the thread's instance. `failover`
  reads the thread's own role's lines first (`crew`, `review`, `scout`, `home`), then every
  other role's. Where no line names the instance, the pool is the thread's instance alone.
  So a reviewer on the crew's provider moves in the crew's pool when its `review` lines name
  two other instances. `failover` never moves a thread to an instance that shares no line of
  the map with the thread's instance, so no work goes to another provider.
- When an instance has headroom, `failover` puts the thread on the first such instance with
  `t3_thread_configure`, and sends it one queued carry-on. The model and the options (effort,
  fast mode) stay as `t3_thread_configure` read them, and only the `instanceId` changes.
  A thread already on that instance gets only the carry-on. This works both ways: a thread
  capped on a later instance goes back to an earlier one with headroom, just as a thread
  capped on the first instance goes on to the next.
- While every instance of the pool is capped, `failover` sends nothing and raises one `stall`
  event (user level) that names the first reset. The first pass after that reset handles the
  thread as above.

Before a move onto a mirror instance, `failover` asks `jroles mirror --check`, as a launch
does (`dispatch.mirrored`). For that pass it skips an instance that is not mirrored. A thread
with no other instance left gets nothing and waits for a later pass. A replay skips the
check.

`failover` moves a thread only on a cap, and the thread stays on its new instance until that
instance caps. `failover` never moves a thread back once the old instance is free, since each
move is a handoff that loses context.

`movers` picks the threads of the project that failed and are not settled. It finds a crew
(`crew: `), a reviewer (`review: `) or a scout (`scout: `) by the thread's title. It also
takes a crew that a brief names on a `Thread:` line, and the homes in a `home-id`, the root
home's and each scope's. `failover` goes through every project of the config, so this covers every
jbus project. `failover` leaves alone a thread with nothing left to do: a crew whose task
merged or ended clean, a reviewer whose task is over and whose brief's last Review has a
verdict, a scout whose last Report says `Status: done`.

`failover` handles each failed run once. After it queues the carry-on, it keeps the run's
key, `failover|<thread>|<run>`, in `sent.json`. It keys a stall by the reset instead. A
crash between the two calls is safe: the configure call sets the same selection again, and
the send call uses the key as its retry key. `failover` puts the slug of each crew it reads
in `Pass.limited`, and `threads.resume` leaves that crew alone, since the carry-ons of
`threads.resume` are not for a limit or a lapse. jbus keeps the events of a reviewer or a
scout under the id of that thread, not under the slug, so they never count as the events of
the crew of that slug.

A turn that fails on a login lapse cannot carry on where it was either: a signed-out instance
ends each turn within a second with an item whose text `LAPSE` matches (`lapse_of`). That is
no cap, so `failover` writes nothing to the ledger. It asks T3 Code once a pass which
instances can run (`orchestrator_capabilities`): one whose constraints include `Provider is
not authenticated.` cannot, and nor can one that a run failed to sign in on less than `HOLD`
ago, whatever T3 Code says, since T3 Code may not have looked again yet. It sends the thread
on to the first instance of its pool that can, as for a cap, with one carry-on keyed
`lapse|<thread>|<run>`. While no instance of the pool can sign in, it sends nothing, and tells
the user once with an alert of the machine's, `signed-out <pool>` (`jbus.alert`), with one
quiet `stall` in the project's log. Only the user can sign in again. The alert ends on the
first pass that finds an instance of the pool signed in and no thread of the pool still
waiting on one.

`jbus failover --replay <items.json> --thread <id>` tries one recorded cap on one live
thread. It moves the cap to now (`recorded`), lets it fill the window the ledger has running,
runs it through the same `plan` and `apply`, and prints the move. It does not write the cap
to the ledger, because launches read the ledger. `--dry-run` prints the move and writes
nothing.
Replaying the same items on the same thread again sends nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jbus
import jroles
from jbriefs.home import ids, scopes, thread_of
from jbus import alert, dispatch, outbox, owed, roles, threads, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World
from jroles import ledger, pool

EVENTS = {"failover": "quiet"}
ITEMS = 12
CARRY_ON = (
    "jbus: your last turn stopped on a usage limit ({text}). This thread is now on {instance}, "
    "with the model and options it had. Carry on from where you stopped: {where} Do not start "
    "over."
)
LAPSE_CARRY_ON = (
    "jbus: your last turn stopped because {ran} could not sign in ({text}). This thread is now "
    "on {instance}, with the model and options it had. Carry on from where you stopped: {where} "
    "Do not start over."
)
LAPSE = re.compile(r"Not logged in · Please run /login|Claude could not authenticate\.")
LAPSE_KEY = "lapse"
SIGNED_OUT = "signed-out "
HOLD = timedelta(minutes=5)
UNLISTED = "T3 Code does not list it"
CREW = (
    "read `{brief}` and your worktree's `git status` and `git log` first, keep what is committed."
)
HOME = "read your handoff and `jbus`'s view of your queue first."
REVIEWER = "read `{brief}` and the pull request first, keep what your review has found."
SCOUT = "read `{brief}` first, keep what your Report has."
WHERE = {
    "crew": ("tasks", CREW),
    "reviewer": ("tasks", REVIEWER),
    "scout": ("scouts", SCOUT),
    "home": ("", HOME),
}
MAP_ROLE = {"crew": "crew", "reviewer": "review", "scout": "scout", "home": "home"}
_NUMBER = re.compile(r",\s*\d+$")


@dataclass(frozen=True)
class Mover:
    """A `Mover` is a thread failover may move, with its role. `role` is its name in
    `roles.ROLES` (`crew`, `reviewer`, `scout`, `home`). `slug` is the brief it
    works on, and a home has none."""

    role: str
    slug: str = ""

    @property
    def name(self) -> str:
        """Return the name of the thread in the lines jbus says about it: the slug for a crew,
        `home` for a home, or the role and the slug for any other."""
        if self.role == "crew":
            return self.slug
        return "home" if self.role == "home" else f"{MAP_ROLE[self.role]} {self.slug}"

    def subject(self, thread: str) -> str:
        """Return the name jbus keeps its events and gates under: a crew's slug, and any other
        thread's id, so a reviewer's cap is never its crew's."""
        return self.slug if self.role == "crew" else thread

    def where(self, home: Path) -> str:
        folder, text = WHERE[self.role]
        return text.format(brief=home / folder / f"{self.slug}.md") if folder else text


def _homes(run: Pass) -> set[str]:
    """Return the thread in each `home-id` under the project's home directory, the root's and every
    scope's."""
    return {ids(run.home)[0], *(now for _, now, _ in scopes(run.home))} - {""}


def _named(run: Pass) -> dict[str, str]:
    """Return each thread a brief names on its `Thread:` line, with the slug of that brief."""
    found = {}
    for path in sorted((run.home / "tasks").glob("*.md")):
        if thread := thread_of(run.home, path.stem):
            found[thread] = path.stem
    return found


def movers(run: Pass, listed: list[dict[str, Any]]) -> dict[str, Mover]:
    """Return each of the `listed` threads failover may move, keyed by its id. Those are a home
    in a `home-id`, a crew that a brief names on its `Thread:` line, and a crew, a reviewer or
    a scout found by its title. It leaves out a thread whose title names no crew, reviewer or
    scout. That includes a `home: ` title. A reviewer's title may end in its number,
    `review: <slug>, <n>`, and that number is not part of its slug."""
    homes, named = _homes(run), _named(run)
    found = {}
    for thread in listed:
        at = thread.get("threadId")
        role, slug = roles.role_of(str(thread.get("title", "")))
        if at in homes:
            found[at] = Mover("home")
        elif at in named:
            found[at] = Mover("crew", named[at])
        elif role in WHERE and role != "home" and slug:
            found[at] = Mover(role, _NUMBER.sub("", slug) if role == "reviewer" else slug)
    return found


def _over(run: Pass, world: World) -> dict[str, set[str]]:
    """Return, by role, the slugs whose threads have nothing left to do. The rule is the one
    jbus settles threads by (`threads.finished`): a crew whose task merged or ended clean, a
    reviewer whose task is over and whose brief's last Review has a verdict, and a scout whose
    last Report says `Status: done` and waits on nobody. A verdict alone does not finish a
    reviewer. A verdict is what makes jbus launch a scoped or second-pass reviewer, and that new
    reviewer still has its own pass to do."""
    done = threads.finished(run, world)
    return {"crew": done["crew: "], "reviewer": done["review: "], "scout": done["scout: "]}


@dataclass(frozen=True)
class Lapse:
    """A `Lapse` is a run that failed because its instance could not sign in: the provider's
    words for it, and when the run ended."""

    text: str
    ended: datetime


def lapse_of(items: list[dict[str, Any]], ended: datetime) -> Lapse | None:
    """Return the login lapse that a run's items name, or None for a run that hit none. An
    instance that is signed out ends a turn at once with an assistant message, an error item, or
    both, whose text starts with one of the provider's words in `LAPSE`. An item counts only
    where its text starts with them, so a turn that only quotes them is no lapse."""
    for item in items:
        text = str(item.get("text") or "").strip()
        if LAPSE.match(text):
            return Lapse(text, ended)
    return None


def failure_of(
    client: Client, thread: dict[str, Any], run: Pass
) -> tuple[ledger.Cap | Lapse, str] | None:
    """Return what the thread's last run failed on, a usage limit or a login lapse, and the
    instance that run was on, or None for a run that failed on neither. It reads both from the
    last items the thread wrote. The failure is the run's instance's, not the thread's instance's
    now: a thread that the user moved by hand after the failure is on another one. When the text
    of a cap gives a reset, it reads that reset relative to the time the run ended, not to the
    time of the pass. A run whose items name a cap is a cap, whatever else they say."""
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
    ended = owed.when(stamps) or run.now
    found = ledger.cap_of(last, ended) or lapse_of(last, ended)
    return (found, run_of.get("providerInstanceId") or "") if found else None


def pool_of(run: Pass, role: str, instance: str) -> tuple[str, ...]:
    """Return the pool a thread of `role` on `instance` moves in. It is the first line of the
    role map that names the instance. The function reads the thread's own role's lines first,
    then every other role's in the map's order. Where no line names the instance, the pool is
    the instance alone. A reviewer on the crew's provider moves in the crew's pool when its
    `review` lines name two other instances."""
    own = MAP_ROLE[role]
    for name in (own, *(one for one in jroles.ROLES if one != own)):
        try:
            chosen = pool.selections(name)
        except jroles.Refused as error:
            run.say(f"wait {run.project.name}: the role map gives {name} no pool ({error})")
            continue
        for one in chosen:
            if instance in one.instances:
                return one.instances
    return (instance,)


def failover(run: Pass, client: Client, world: World) -> None:
    """Move each thread that failed on a usage limit to an instance that is not capped, and
    each thread that failed on a login lapse to one that can sign in, and tell it to carry on.
    See the module for the rules."""
    found = _failed(run, client, world)
    if found is not None:
        carry_lapses(run, client, *found)


def _failed(run: Pass, client: Client, world: World) -> tuple[list[Lapsed], dict[str, bool]] | None:
    """Handle each thread that failed on a usage limit, and return the ones that failed on a
    login lapse with the mirror checks of the pass, or None where T3 Code did not list the
    failed threads."""
    try:
        failed = owed.failed(run, client)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the failed threads could not be listed ({error})")
        return None
    listed = [thread for thread in failed if not thread.get("snoozed")]
    found = movers(run, listed)
    lapsed: list[Lapsed] = []
    checked: dict[str, bool] = {}
    if not found:
        return lapsed, checked
    over = _over(run, world)
    sent = run.box.sent()
    for thread in listed:
        at, ended = thread["threadId"], thread["latestRunId"]
        mover = found.get(at)
        if mover is None or mover.slug in over.get(mover.role, ()):
            continue
        crew = {mover.slug} if mover.role == "crew" else set()
        if crew & run.gated:
            continue
        key, lapse_key = f"failover|{at}|{ended}", f"{LAPSE_KEY}|{at}|{ended}"
        if key in sent or lapse_key in sent:
            run.limited |= crew
            continue
        try:
            failure = failure_of(client, thread, run)
            if failure is None:
                continue
            run.limited |= crew
            if isinstance(failure[0], Lapse):
                lapsed.append(Lapsed(thread, mover, failure[0], failure[1], lapse_key))
                continue
            handle(run, client, thread, mover, (failure[0], failure[1]), key, checked)
        except T3Refused as error:
            what = "T3 Code refused the failover"
            run.gate(mover.subject(at), what, str(error), key=f"{what} {at} {ended}")
        except T3Error as error:
            run.say(f"wait {mover.name}: the failover could not be made ({error})")
    return lapsed, checked


@dataclass(frozen=True)
class Lapsed:
    """A `Lapsed` is a thread whose last run failed on a login lapse: the lapse, the instance
    the run was on, and the retry key of its one carry-on."""

    thread: dict[str, Any]
    mover: Mover
    lapse: Lapse
    ran: str
    key: str


def signed_in(run: Pass, client: Client, lapsed: list[Lapsed]) -> dict[str, str] | None:
    """Return why each provider instance that T3 Code lists cannot take a carry-on now, and
    nothing for one that can, or None where T3 Code did not say. T3 Code's capabilities give the
    why: a signed-out instance has `Provider is not authenticated.` among its constraints. A
    run that failed to sign in on an instance less than `HOLD` ago says more than T3 Code's word
    that it can, since T3 Code may not have looked again yet."""
    try:
        said = client.call("orchestrator_capabilities", {})
    except T3Error as error:
        run.say(f"wait {run.project.name}: T3 Code did not say which instances sign in ({error})")
        return None
    why = {
        str(one["providerInstanceId"]): " ".join(str(c) for c in one.get("constraints") or [])
        for one in said.get("providers") or []
        if isinstance(one, dict) and one.get("providerInstanceId")
    }
    for one in lapsed:
        if not why.get(one.ran, UNLISTED) and run.now - one.lapse.ended < HOLD:
            why[one.ran] = f"a turn on it failed to sign in at {one.lapse.ended.isoformat()}"
    return why


def carry_lapses(run: Pass, client: Client, lapsed: list[Lapsed], checked: dict[str, bool]) -> None:
    """Send each thread that failed on a login lapse on to the first instance of its pool that
    can sign in, with one carry-on for the failed run. While no instance of a pool can, send
    nothing, and tell the user once (`signed_out`). End that alert once an instance of the pool
    can sign in and no thread of the pool waited this pass."""
    opened = [key for key in alert.streaks(run.config.state_dir) if key.startswith(SIGNED_OUT)]
    if not lapsed and not opened:
        return
    why = signed_in(run, client, lapsed)
    if why is None:
        return
    waited: set[tuple[str, ...]] = set()
    for one in lapsed:
        try:
            instances = carry_lapse(run, client, one, why, checked)
        except T3Refused as error:
            what = "T3 Code refused the failover"
            at = one.thread["threadId"]
            run.gate(one.mover.subject(at), what, str(error), key=f"{what} {one.key}")
            continue
        except T3Error as error:
            run.say(f"wait {one.mover.name}: the failover could not be made ({error})")
            continue
        waited.add(instances)
    for key in opened:
        instances = tuple(key.removeprefix(SIGNED_OUT).split(","))
        able = [name for name in instances if not why.get(name, UNLISTED)]
        if able and instances not in waited:
            alert.closed(run.config, key, f"signed in: {able[0]} can sign in again")


def carry_lapse(
    run: Pass, client: Client, one: Lapsed, why: dict[str, str], checked: dict[str, bool]
) -> tuple[str, ...]:
    """Send one thread that failed on a login lapse on, as `carry_lapses` says, and return its
    pool. A pool whose thread went on this pass keeps its alert until a pass sees none of its
    threads fail again, so an instance that fails to sign in now and then is told once."""
    at, mover = str(one.thread["threadId"]), one.mover
    configuration = client.call("t3_thread_configure", {"threadId": at})
    selection = dict(configuration.get("modelSelection") or {})
    if not selection.get("model"):
        run.limited.discard(mover.slug if mover.role == "crew" else "")
        return ()
    here = _instance(selection)
    instances = pool_of(run, mover.role, here)
    skip = {
        name: f"{name} cannot sign in ({why.get(name, UNLISTED)})"
        for name in instances
        if why.get(name, UNLISTED)
    }
    if len(skip) == len(instances):
        signed_out(run, instances)
        return instances
    subject = mover.subject(at)
    choice = dispatch.mirrored_choice(run, subject, instances, checked, here, skip=skip)
    if choice.instance is None:
        run.say(f"wait {mover.name}: no move: {choice.why}")
        return instances
    ran = one.ran or here
    message = threads.resume_message(
        LAPSE_CARRY_ON,
        str(one.thread.get("title", "")),
        run.home,
        ran=ran,
        text=one.lapse.text,
        instance=choice.instance,
        where=mover.where(run.home),
        slug=mover.slug,
    )
    line = f"failover {mover.name}: {ran} could not sign in, {_way(selection, choice.instance)}"
    _go(
        run,
        client,
        one.thread,
        mover,
        (selection, instances),
        choice.instance,
        one.key,
        message,
        line,
    )
    return instances


def signed_out(run: Pass, instances: tuple[str, ...]) -> None:
    """Tell the user once that no instance of the pool can sign in, since only the user can sign
    it in again: an alert of the machine's (`jbus.alert`), which the desk and the infra home get,
    and one quiet `stall` in the project's log while it is open."""
    names = " and ".join(
        [", ".join(instances[:-1]), instances[-1]] if len(instances) > 1 else instances
    )
    line = (
        f"signed out: {names} cannot sign in, so the threads that failed on a login lapse wait: "
        "sign one in again"
    )
    key = SIGNED_OUT + ",".join(instances)
    alert.opened(run.config, key, line, now=run.now)
    opened = alert.streak(run.config.state_dir, key)
    since = opened.since if opened else ""
    if run.find("", "stall", line, key=f"{key} {since}"):
        run.say(line)


def _instance(selection: dict[str, Any]) -> str:
    return selection.get("instanceId") or selection.get("provider") or ledger.BUILT_IN


def _way(selection: dict[str, Any], to: str) -> str:
    """Return the end of a failover's line: the instance the carry-on goes on, and the model and
    options it keeps."""
    options = ", ".join(f"{o.get('id')}={o.get('value')}" for o in selection.get("options") or [])
    way = _instance(selection)
    if to != way:
        way = f"{way} to {to}"
    return f"carry-on on {way}, model {selection['model']}{f', {options}' if options else ''}"


def _go(
    run: Pass,
    client: Client,
    thread: dict[str, Any],
    mover: Mover,
    chosen: tuple[dict[str, Any], tuple[str, ...]],
    to: str,
    key: str,
    message: str,
    line: str,
) -> bool:
    """Put the thread on instance `to` of its pool, where it is not there yet, with its
    selection as it was, and queue its one carry-on under the retry key `key`, with the user's
    ask that the failed run stopped on quoted below it (`owed.quoted`). Log and say `line` once
    it went, close that ask (`owed.taken`), and return whether it went."""
    at = str(thread["threadId"])
    selection, instances = chosen
    client.recipients = client.recipients | {at}
    if to != _instance(selection):
        client.moves[at] = (selection, instances)
        moved = {**selection, "instanceId": to}
        client.call("t3_thread_configure", {"threadId": at, "modelSelection": moved})
    sent = outbox.send(
        run,
        client,
        thread=at,
        row=mover.name,
        key=key,
        text=message + owed.quoted(run, at),
        template="failover",
        needs="act",
    )
    if not sent:
        return False
    run.find(mover.subject(at), "failover", line, key=key)
    run.box.mark(key)
    owed.taken(run, at)
    run.say(line)
    return True


@dataclass(frozen=True)
class Move:
    """A `Move` is the result of a cap for one thread. It has the cap and the instance the cap
    is for, the thread's selection and pool, and the instance that `pool.choose` picked. That
    instance is None while every instance of the pool is capped."""

    thread: dict[str, Any]
    mover: Mover
    cap: ledger.Cap
    capped: str
    selection: dict[str, Any]
    pool: tuple[str, ...]
    choice: pool.Choice

    @property
    def at(self) -> str:
        return str(self.thread["threadId"])

    @property
    def instance(self) -> str:
        return _instance(self.selection)

    def line(self) -> str:
        """Return the line jbus says and logs for the move: the failover, or the stall."""
        name, cap, choice = self.mover.name, self.cap, self.choice
        if choice.instance is None:
            return f"capped {name}: {choice.why}; it is sent on at the first reset"
        way = _way(self.selection, choice.instance)
        return f"failover {name}: {cap.window} limit until {cap.resets.isoformat()}, {way}"


def plan(
    run: Pass,
    client: Client,
    thread: dict[str, Any],
    mover: Mover,
    found: tuple[ledger.Cap, str],
    *,
    fill: bool = False,
    checked: dict[str, bool] | None = None,
) -> Move | None:
    """Return the move that a cap makes of the thread. `plan` reads the ledger with the cap added,
    chooses the move, and writes nothing. It returns None for a thread whose configuration names no
    model.

    A replay sets `fill`. Then, when the ledger has a window running for the capped instance
    and that window resets later, the cap fills that window. Without `fill`, a cap moved to now
    would lose to that window, because the ledger keeps the later reset. A real cap carries
    that window's own reset. A pass sets `checked`. With it, `plan` skips an instance that is not
    mirrored (`dispatch.mirrored_choice`), and that check may run the mirror."""
    cap, ran = found
    configuration = client.call("t3_thread_configure", {"threadId": thread["threadId"]})
    selection = dict(configuration.get("modelSelection") or {})
    if not selection.get("model"):
        return None
    instance = _instance(selection)
    capped = ran or instance
    instances = pool_of(run, mover.role, instance)
    running = ledger.read([capped]).get((capped, cap.window))
    if fill and running and running.resets > cap.resets.timestamp():
        cap = replace(cap, resets=datetime.fromtimestamp(running.resets, UTC))
    kept = ledger.merge(ledger.read(instances), [cap.record(capped)])
    if checked is None:
        choice = pool.choose(instances, kept, run.now)
    else:
        subject = mover.subject(thread["threadId"])
        choice = dispatch.mirrored_choice(run, subject, instances, checked, instance, kept)
    return Move(thread, mover, cap, capped, selection, instances, choice)


def apply(run: Pass, client: Client, move: Move, key: str, *, record: bool = True) -> None:
    """Make the move. Write the cap into the ledger when `record` is on. Then raise the stall,
    or send the configure call (only where the instance changes) and the one queued carry-on whose
    retry key is `key`."""
    at, cap, choice, line = move.at, move.cap, move.choice, move.line()
    client.recipients = client.recipients | {at}
    if record and ledger.write(cap.record(move.capped)):
        run.say(f"capped {move.capped}: {cap.window} until {cap.resets.isoformat()}")
    subject = move.mover.subject(at)
    if choice.instance is None and (choice.until is None or choice.passed):
        run.say(f"wait {move.mover.name}: no move: {choice.why}")
        return
    if choice.instance is None:
        if run.find(subject, "stall", line, key=f"capped {choice.until.isoformat()}"):
            run.say(line)
        return
    message = threads.resume_message(
        CARRY_ON,
        str(move.thread.get("title", "")),
        run.home,
        text=cap.text,
        instance=choice.instance,
        where=move.mover.where(run.home),
        slug=move.mover.slug,
    )
    _go(
        run,
        client,
        move.thread,
        move.mover,
        (move.selection, move.pool),
        choice.instance,
        key,
        message,
        line,
    )


def handle(
    run: Pass,
    client: Client,
    thread: dict[str, Any],
    mover: Mover,
    found: tuple[ledger.Cap, str],
    key: str,
    checked: dict[str, bool],
) -> None:
    move = plan(run, client, thread, mover, found, checked=checked)
    if move is None:
        run.limited.discard(mover.slug if mover.role == "crew" else "")
        return
    apply(run, client, move, key)


def _items(path: Path) -> list[dict[str, Any]]:
    """Read the items of a recording: a list of T3 Code's thread items, or an object whose
    `items` is such a list."""
    try:
        found = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise jbus.Refused(f"refused: {path} cannot be read as JSON ({error})") from error
    items = found.get("items") if isinstance(found, dict) else found
    if not isinstance(items, list) or not all(isinstance(one, dict) for one in items):
        raise jbus.Refused(f"refused: {path} is not a list of items")
    return items


def recorded(items: list[dict[str, Any]], now: datetime) -> ledger.Cap:
    """Return the cap in a recording, moved to `now`. Its reset is as far after `now` as it
    was after the last item's `updatedAt`, so `resets in 17m` reads as 17 minutes from now."""
    stamps = sorted((str(one.get("updatedAt") or "") for one in items), reverse=True)
    then = owed.when(stamps)
    cap = ledger.cap_of(items, then or now)
    if cap is None:
        raise jbus.Refused("refused: the recording holds no usage limit")
    return replace(cap, resets=cap.resets + (now - then)) if then else cap


def _replay(args: argparse.Namespace, config: jbus.Config) -> int:
    """`jbus failover --replay` runs one recorded cap through the move a pass makes, for one
    live thread, as its line in `VERBS` says."""
    project = verbs.project(config, args.project)
    now = datetime.now(UTC)
    run = Pass(config, project, now)
    items = _items(Path(args.replay))
    cap = recorded(items, now)
    client = Client(config.server, config.token_path)
    thread = client.call("t3_thread_read", {"threadId": args.thread, "limit": 1}).get("thread")
    thread = thread if isinstance(thread, dict) else {}
    if thread.get("projectId") not in (None, project.project_id):
        raise jbus.Refused(f"refused: {args.thread} is no thread of {project.name}")
    mover = movers(run, [{**thread, "threadId": args.thread}]).get(args.thread)
    if mover is None:
        raise jbus.Refused(
            f"refused: {args.thread} is no crew, reviewer, scout or home of {project.name}"
        )
    noted = sorted(str(one.get("itemId") or "") for one in items)
    digest = hashlib.sha256("\n".join(noted).encode()).hexdigest()[:12]
    key = f"failover|{args.thread}|replay:{digest}"
    if key in run.box.sent():
        print(f"already replayed: {key} was sent, and nothing is sent again")
        return 0
    move = plan(run, client, {**thread, "threadId": args.thread}, mover, (cap, ""), fill=True)
    if move is None:
        raise jbus.Refused(f"refused: {args.thread} has no model in its configuration")
    if args.dry_run:
        print(f"dry run, nothing written: {move.line()}")
        return 0
    run.say = print
    apply(run, client, move, key, record=False)
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--replay", required=True, type=Path, metavar="ITEMS", help=REPLAY_ITEMS)
    parser.add_argument("--thread", required=True, help="the live thread the cap is replayed on")
    parser.add_argument("--dry-run", action="store_true", help="print the move and write nothing")


REPLAY_ITEMS = "a JSON list of T3 Code thread items, or an object whose items is one"
VERBS = (
    verbs.Verb(
        "failover",
        "replay a recorded usage limit on one thread: the move a pass makes, the cap kept out of "
        "the ledger",
        _arguments,
        _replay,
    ),
)
STEPS = (
    verbs.Step(
        "before-watch",
        7,
        "owed.sweep",
        lambda half: owed.sweep(half.run, half.client, lambda listed: movers(half.run, listed)),
        ("client",),
    ),
    verbs.Step(
        "tellers",
        55,
        "failover.failover",
        lambda half: failover(half.run, half.client, half.seen.world),
        ("client", "world"),
        shared=True,
    ),
)
