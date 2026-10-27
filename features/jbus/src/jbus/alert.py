"""Tell the user once about a failure that repeats, and once about its end. This module is the
only place that keeps a streak.

A streak is the failures in a row of one thing, under a key:

- `pass` for a pass that did not finish;
- `home thread <project>` for a wake of the project's that its home thread did not get;
- `webhook <project>` for a POST the project's own webhook did not take;
- `top-level webhook <project>` for a POST of the project's that the top-level webhook did not
  take;
- `blocking webhook <project>` for a body of the project's that the second target did not take;
- `jmerge <project>` for a `jmerge` that did not run;
- `snapshot` for a snapshot of the homes' state tree that did not finish;
- `stale` for a look by `jbus alarm --stale` that found no pass ended within its limit;
- `health <check>` for an incident `jbus.health` found.

`flush` sends a project's wakes to its home thread through T3 Code (`_send`), the route
`wake = "home"` and `wake = "both"` pick. For a project with `wake = "webhook"`, a webhook streak
is told on one more path, which does not go through a webhook: `page` sends the alert to the
project's home thread, at the failures in `PAGES` and at every `EVERY`th after them, and `paged` in
the streak keeps the last count it was sent for. A project whose wakes go to its home thread gets
that alert as a wake. `failing` gives the line of each route's streak that alerted, for
`jbus status`, the heartbeat and `jbus wakes`.

`failed` counts one failure, and returns the alert line once the count has reached the threshold.
`ok` ends the streak, and returns the recovered line when the streak had alerted. An incident is a
streak that `opened` starts and `closed` ends, with the line its caller passes. Everything else is
silent: the failures before the threshold, the ones after the alert, and a success with no alert
before it.

This module returns a line on each count until `told` records that the line is in the queue,
and only `told` marks the streak. A caller may raise or be killed after it gets the line and
before it queues it. Then its next count returns the line again. So a line goes out at least
once, and twice only after such a break.

The streaks are in `streaks.json`. Only this module writes that file, and it writes under a
lock, because `jbus alarm` runs outside the pass lock and may count while a pass ends another
streak. The status file shows a copy, under `streaks`.
"""

from __future__ import annotations

import argparse
import fcntl
import functools
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbriefs.home import thread_of
from jbus import outbox, passes, read_json, verbs, wake, write_json
from jbus.t3 import Client, T3Error

WAKE = """\
jbus: {count} events for the user, each a decision or a stop that is theirs. End the turn by "How a
turn ends" in the home skill, with one line for each, keyed `jbus`, as that section says.
{say}

```json
{body}
```"""
EVENTS = {"alert": "user", "recovered": "quiet"}
RECOVERED = "recovered"
AFTER = 3
PAGES = (AFTER, 30)
EVERY = 120
PAGE = """\
jbus: {line}
This webhook does not take what jbus posts for the user, so nothing jbus posts reaches them \
while it fails: tell the user. jbus tells this thread again at {again} failures, and \
`jbus wakes` says when the webhook takes posts again."""
PASS = "pass"
SNAPSHOT = "snapshot"
STALE = "stale"


@dataclass
class Streak:
    key: str
    count: int
    since: str
    alerted: bool
    paged: int = 0


def webhook(project: str) -> str:
    return f"webhook {project}"


def home(project: str) -> str:
    return f"home thread {project}"


def key_of(name: str, route: wake.Route) -> str:
    """Return the key of a route's streak."""
    return home(name) if route.home else top_level(name) if route.top else webhook(name)


def top_level(project: str) -> str:
    return f"{wake.TOP_LEVEL} webhook {project}"


def blocking(project: str) -> str:
    return f"{wake.BLOCKING} webhook {project}"


def jmerge(project: str) -> str:
    return f"jmerge {project}"


def _path(state: Path) -> Path:
    return state / "streaks.json"


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    """Hold the lock from a streak's read to its write, so that no count and no `alerted` is
    lost."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "streaks.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def streaks(state: Path) -> dict[str, dict]:
    """Return every open streak, by key, as the status file shows them."""
    return read_json(_path(state), {})


def streak(state: Path, key: str) -> Streak | None:
    """Return the streak that is open under this key, or None when the last try under the key
    succeeded."""
    kept = streaks(state).get(key)
    return Streak(**kept) if kept else None


def _keep(state: Path, key: str, one: Streak | None) -> None:
    kept = {name: other for name, other in streaks(state).items() if name != key}
    if one:
        kept[key] = {name: value for name, value in asdict(one).items() if name != "paged" or value}
    write_json(_path(state), kept, mode=0o600)


def _since(one: Streak, user: jsettings.Settings) -> str:
    return user.clock(datetime.fromisoformat(one.since))


def failed(
    state: Path,
    key: str,
    why: str,
    after: int = AFTER,
    *,
    now: datetime | None = None,
    user: jsettings.Settings,
) -> str | None:
    """Count one failure. From the count `after` on, return the alert line on each call until
    `told` records it."""
    now = now or datetime.now(UTC)
    with _locked(state):
        one = streak(state, key) or Streak(key, 0, now.isoformat(), False)
        one.count += 1
        _keep(state, key, one)
    if one.count < after or one.alerted:
        return None
    return _line(one, why, user)


def _line(one: Streak, why: str, user: jsettings.Settings) -> str:
    return f"alert: {one.key} failed {one.count} times in a row since {_since(one, user)}: {why}"


def ok(state: Path, key: str, *, user: jsettings.Settings) -> str | None:
    """Record a try that succeeded. For a streak that alerted, return the recovered line on
    each call until `told` records it.

    A streak that had not alerted ends here, with no line.
    """
    with _locked(state):
        one = streak(state, key)
        if one is not None and not one.alerted:
            _keep(state, key, None)
    if one is None or not one.alerted:
        return None
    return f"recovered: {key} after {one.count} failures since {_since(one, user)}"


def opened(state: Path, key: str, line: str, *, now: datetime) -> str | None:
    """Record an incident found under `key`. Return `alert: <line>` on each look, from the look that
    found the incident until `told` records the line, and nothing after that. So jbus pages the
    incident once. `line` gives the number and the limit it is against. This function writes the
    streak when the incident starts and not on each look, so its count stays 1: an incident is not a
    failure in a row."""
    with _locked(state):
        one = streak(state, key)
        if one is None:
            one = Streak(key, 1, now.isoformat(), False)
            _keep(state, key, one)
    return None if one.alerted else f"alert: {line}"


def closed(state: Path, key: str, line: str, *, user: jsettings.Settings) -> str | None:
    """Record that a look found the incident under `key` back under its limit. For an
    incident that jbus paged, return `recovered: <line>` on each look until `told` records the
    line. Return nothing where there is no incident.

    When the page for an incident's start did not go out, jbus still tells the user that the
    incident ended. The answer then also says when the incident began, and this function marks
    the streak as paged. So `told` ends the streak, and if this page does not go out either,
    the next look sends a plain recovered line."""
    with _locked(state):
        one = streak(state, key)
        owed = one is not None and not one.alerted
        if one is not None and owed:
            one.alerted = True
            _keep(state, key, one)
    if one is None:
        return None
    began = f" (it began {_since(one, user)}, and that page did not go)" if owed else ""
    return f"recovered: {line}{began}"


def told(state: Path, key: str) -> None:
    """Mark the streak alerted, or end it, once the line that `failed` or `ok` returned is in
    the queue."""
    with _locked(state):
        one = streak(state, key)
        if one is None:
            return
        if one.alerted:
            _keep(state, key, None)
        else:
            one.alerted = True
            _keep(state, key, one)


def recovered(
    config: jbus.Config,
    runs: list[passes.Pass],
    guarded: Callable[[str, Callable[[], Any]], Any],
    raised: dict[str, str],
) -> None:
    """After a pass in which nothing raised, end the `PASS` streak and then the `STALE` one.
    Send each recovered line to every project, and wrap each send in `guarded` with its
    project's name. When a send raises, this function leaves that streak and the next one
    open, and the next pass ends them."""
    for key in (PASS, STALE):
        if raised:
            break
        line = ok(config.state_dir, key, user=config.user)
        for run in runs:
            guarded(run.project.name, lambda run=run, line=line: deliver(run, line))
        if line and not raised:
            told(config.state_dir, key)


def retire(state: Path, key: str) -> None:
    """End a streak that nothing counts any more, with no line, since what counted it is gone."""
    with _locked(state):
        if streak(state, key):
            _keep(state, key, None)


def deliver(run: passes.Pass, line: str | None, *, desk: bool = True) -> None:
    """Send an alert to the chat, log a recovered line (`queue`), and print either in the
    journal as `<project>: <line>`. Send nothing when there is no line.

    While the project's webhook is failing, the line would only wait in the outbox, so this
    function tells the desk as well. `desk=False` is for a caller that has told the desk itself.

    The line goes into the queue with no key. A streak returns its line once. A later streak
    that starts at the same minute of another day makes the same line, and that line must go
    out again.
    """
    if not line:
        return
    run.say(f"{run.project.name}: {line}")
    queue(run.box, line)
    name, state = run.project.name, run.config.state_dir
    if desk and (streak(state, webhook(name)) or streak(state, home(name))):
        wake.notify(line)


def queue(box: wake.Box, line: str, *, machine: bool = False) -> None:
    """Queue a line of this module. A `recovered` line ends a streak or an incident: it asks
    nothing of the user and reports no stop, so it is quiet, in the log and the digest and in no
    outbox. Every other line is an `alert`, for the user."""
    if line.startswith(f"{RECOVERED}: "):
        box.send("", RECOVERED, line, machine=machine)
    else:
        box.send("", "alert", line, machine=machine)


def tell(run: passes.Pass, key: str, line: str | None) -> None:
    """Deliver the line that a streak of this project returned, and only then mark the streak."""
    if line:
        mine = (webhook(run.project.name), home(run.project.name))
        deliver(run, line, desk=not (key in mine and line.startswith(RECOVERED)))
        told(run.config.state_dir, key)


def flush(run: passes.Pass, client: Client | None = None) -> int:
    """Send what waits for the project to each of its routes, and count each route's streak by how
    the send went. Then tell the project's home thread of a webhook streak whose page is due
    (`page`). Return how many events went, the most that any one route took.

    This function sends to the project's first route first, so that an alert from that route's
    streak goes to the others in the same pass. It sends to the second target before them all, with
    its own streak, for the same reason. Before them all, what waits for a route the project's
    `wake` leaves out moves to the routes in effect (`moved`), and that route's streak ends with
    no line. For a top-level pair or a second target the config does not have any more, it drops
    what waited for it, and if the pair comes back later, its route gets only what is new. Last, it
    tells once of each event for the user that waits unposted while a route takes posts
    (`unposted`).
    """
    state, name = run.config.state_dir, run.project.name
    moved(run)
    if run.box.blocking is None:
        retire(state, blocking(name))
        run.box.drop(wake.BLOCKING)
    else:
        ended: list[str] = []
        run.box.flush_blocking(run.now, run.say, went=ended.append)
        _count(run, blocking(name), ended)
    sent, taken, working = 0, set(), None
    for route in run.box.routes:
        went: list[str] = []
        post = None
        if route.home:
            thread = _thread(run, route)
            if not thread:
                continue
            post = functools.partial(_send, run, client, thread)
        before = run.box.ids(route)
        took = run.box.flush(run.now, run.say, route=route, went=went.append, post=post)
        sent = max(sent, took)
        taken |= before - run.box.ids(route)
        if working is None and not run.box.waiting(route) and not any(went[-1:]):
            working = route
        _count(run, key_of(name, route), went)
    if not any(route.home for route in run.box.routes):
        retire(state, home(name))
    if not any(route.top for route in run.box.routes):
        retire(state, top_level(name))
        if tuple(run.box.top) in (("", ""), (run.project.webhook_url, run.project.webhook_key)):
            run.box.drop(wake.TOP_LEVEL)
    page(run, client)
    unposted(run, taken, working)
    return sent


def moved(run: passes.Pass) -> None:
    """Move what waits for a route the project's `wake` leaves out to the routes in effect
    (`wake.Box.rehome`), and say in one journal line how many moved, from where and to where."""
    old, count = run.box.rehome()
    if old:
        where = " and the ".join(route.name for route in old)
        to = " and the ".join(route.name for route in run.box.routes)
        outboxes = "outboxes" if len(old) > 1 else "outbox"
        run.say(
            f"moved {run.project.name}: {count} events for the user from the {where} {outboxes} "
            f"to the {to}, which `wake` picks now"
        )


def unposted(run: passes.Pass, taken: set[str], working: wake.Route | None) -> None:
    """Tell on the desk and in the journal, once, of each event for the user that still waits
    after `wake.AFTER` passes in which a route in effect, `working`, took posts. `working` is the
    first route that waits for nothing after its flush and whose last POST did not fail."""
    for one in run.box.unposted(taken, working is not None):
        line = (
            f"unposted {run.project.name}: an event for the user waits after {wake.AFTER} passes "
            f"while the {working.name} takes posts: {one.get('say') or one['line']}"
        )
        run.say(line)
        wake.notify(line)


def _thread(run: passes.Pass, route: wake.Route) -> str:
    """Return the thread that gets the project's wakes: its home's, or else the config's
    `home_thread`. With neither, say so once in the journal, until a thread is found."""
    thread = thread_of(run.home) or run.config.home_thread
    marks = read_json(route.folder / "wake.json", {})
    if bool(thread) == bool(marks.get("no_thread")):
        route.folder.mkdir(parents=True, exist_ok=True)
        write_json(route.folder / "wake.json", {**marks, "no_thread": not thread})
        if not thread:
            run.say(
                f"wake waits {run.project.name}: no home thread, and the config names no "
                "home_thread, so its events wait in the outbox"
            )
    return thread


def _send(
    run: passes.Pass, client: Client | None, thread: str, _: wake.Route, made: dict[str, Any]
) -> str:
    """Send one body of events to the thread through T3 Code, keyed by the body, so that a retry
    sends the same message. Return why it failed, or nothing."""
    try:
        client = client or Client(run.config.server, run.config.token_path)
    except jbus.Refused as error:
        return str(error)
    text = json.dumps(made, indent=1)
    message = WAKE.format(count=len(made["events"]), say="\n".join(made["say"]), body=text)
    retry = f"wake|{run.project.name}|{wake._id(made)}"
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=run.project.name,
            key=retry,
            text=message,
            template="wake",
            needs="decide",
        )
    except T3Error as error:
        return f"T3 Code did not take the wake: {error}"
    return "" if went else f"{thread} is capped, so the wake waits for the reset"


def _count(run: passes.Pass, key: str, went: list[str]) -> None:
    """Count a webhook's streak by how its flush ended, and tell the line the streak returns."""
    state = run.config.state_dir
    for why in went:
        said = (
            failed(state, key, why, now=run.now, user=run.user)
            if why
            else ok(state, key, user=run.user)
        )
        tell(run, key, said)


def why(error: Exception, *hooks: jbus.Project | jbus.Hook) -> str:
    """Format an exception as one line, for the journal and the status file.

    An error from a webhook URL that cannot be used quotes the URL, whole or in part, so this
    function removes each hook's secrets from it (`jbus.secrets`).
    """
    said = " ".join(f"{type(error).__name__}: {error}".split())
    return wake.cut(jbus.redact(said, jbus.secrets(*hooks, part=2), "[webhook]"), 300)


def sound(
    config: jbus.Config,
    key: str,
    cause: str,
    after: int,
    now: datetime,
    say: Callable[[str], None],
) -> int:
    """Count one failure of a unit that runs outside the pass, and alert once the alert is due.

    The alert goes to the desk and waits in each project's outbox like any other event. This
    function flushes what waits each time, so an alert the webhook did not accept goes out
    with the next alarm or with the next pass that ends. It marks the streak alerted only after
    it has told the desk and the projects. So when something stops an alarm before then, the
    next alarm alerts again.
    """
    line = failed(config.state_dir, key, cause, after, now=now, user=config.user)
    if line:
        wake.notify(line)
    code = 0
    for one in config.projects:
        try:
            run = passes.Pass(config, one, now, say)
            deliver(run, line, desk=False)
            flush(run)
            if line:
                say(f"alert {'waits' if run.box.waiting() else 'sent'}: {one.name}")
        except Exception as error:
            say(f"alarm failed {one.name}: {why(error, one)}")
            code = 1
    if line:
        told(config.state_dir, key)
    return code


def recover(config: jbus.Config, key: str, now: datetime, say: Callable[[str], None]) -> None:
    """Record that a unit outside the pass succeeded: end its streak. If the streak had
    alerted, tell each project that the unit recovered."""
    line = ok(config.state_dir, key, user=config.user)
    if not line:
        return
    wake.notify(line)
    for one in config.projects:
        try:
            deliver(passes.Pass(config, one, now, say), line, desk=False)
        except Exception as error:
            say(f"recovered failed {one.name}: {why(error, one)}")
    told(config.state_dir, key)


def _routes(run: passes.Pass) -> Iterator[tuple[wake.Route, str]]:
    """Each route that posts the project's events for the user, with the key of its streak."""
    for route in run.box.routes:
        yield route, key_of(run.project.name, route)


def failing(run: passes.Pass) -> list[tuple[str, str]]:
    """Return the key and the alert line of each webhook of the project whose streak alerted, with
    the last error the webhook gave."""
    found = []
    for route, key in _routes(run):
        one = streak(run.config.state_dir, key)
        if one is not None and one.count >= AFTER:
            why = run.box.marks(route).get("last_error", "")
            found.append((key, _line(one, why, run.user)))
    return found


def _due(count: int) -> int:
    """Return the last count at or under `count` that a page is due at, or 0 for none."""
    if count >= EVERY:
        return count - count % EVERY
    return max((one for one in PAGES if one <= count), default=0)


def _again(count: int) -> int:
    return next((one for one in PAGES if one > count), (count // EVERY + 1) * EVERY)


def page(run: passes.Pass, client: Client | None) -> None:
    """Send each alert of the project's webhook streaks to the project's home thread, once at each
    count `_due` gives. A send that T3 Code refused goes again on the next pass. Nothing goes where
    T3 Code is not signed in, or the project's home has no thread, or the project's wakes go to its
    home thread, which gets the alert as a wake."""
    thread = thread_of(run.home)
    if client is None or not thread or run.project.to_home:
        return
    state, name = run.config.state_dir, run.project.name
    for key, line in failing(run):
        if key == home(name):
            continue
        one = streak(state, key)
        due = _due(one.count) if one else 0
        if one is None or due <= one.paged:
            continue
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=name,
                key=f"page|{key}|{one.since}|{due}",
                text=PAGE.format(line=line, again=_again(one.count)),
                template="page",
                needs="decide",
            )
        except T3Error as error:
            run.say(f"page failed {name}: {error}")
            continue
        if not went:
            continue
        with _locked(state):
            kept = streak(state, key)
            if kept is not None and kept.since == one.since:
                kept.paged = due
                _keep(state, key, kept)
        run.say(f"paged {name}'s home, thread {thread}: {line}")


def _wakes(args: argparse.Namespace, config: jbus.Config) -> int:
    """Run `jbus wakes`: say whether the project's wakes can come, so that a thread knows whether to
    wait for one. The home thread decides it where the project's wakes go there, and a failing
    webhook beside it is named on a line of its own, since the home thread still gets them."""
    run = passes.Pass(config, verbs.here(config, args.project), datetime.now(UTC))
    name, by = run.project.name, "home thread" if run.project.to_home else "webhook"
    found = failing(run)
    fails = [line for key, line in found if key == home(name) or not run.project.to_home]
    for line in fails:
        print(f"wakes fail: {line}")
    if not fails:
        print(f"wakes go: the {by} of {name} is not failing")
    for line in [line for _, line in found if line not in fails]:
        print(f"webhook fails (optional): {line}")
    return 1 if fails else 0


VERBS = (
    verbs.Verb(
        "wakes", "whether the wakes of this repo's project are failing", verbs.nothing, _wakes
    ),
)
