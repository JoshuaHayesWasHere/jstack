"""Tell the user once about a failure that repeats, and once about its end. This module is the
only place that keeps a streak.

A streak is the failures in a row of one thing, under a key:

- `pass` for a pass that did not finish;
- `webhook <project>` for a POST the project's own webhook did not take;
- `top-level webhook <project>` for a POST of the project's that the top-level webhook did not
  take;
- `blocking webhook <project>` for a body of the project's that the second target did not take;
- `jmerge <project>` for a `jmerge` that did not run;
- `snapshot` for a snapshot of the homes' state tree that did not finish;
- `stale` for a look by `jbus alarm --stale` that found no pass ended within its limit;
- `health <check>` for an incident `jbus.health` found.

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

import fcntl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbus import read_json, wake, write_json

EVENTS = {"alert": "user"}
AFTER = 3
PASS = "pass"
SNAPSHOT = "snapshot"
STALE = "stale"


@dataclass
class Streak:
    key: str
    count: int
    since: str
    alerted: bool


def webhook(project: str) -> str:
    return f"webhook {project}"


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
        kept[key] = asdict(one)
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
    return f"alert: {key} failed {one.count} times in a row since {_since(one, user)}: {why}"


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
    runs: list[wake.Pass],
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


def deliver(run: wake.Pass, line: str | None, *, desk: bool = True) -> None:
    """Send an alert or a recovered line to the chat. Send nothing when there is no line.

    While the project's webhook is failing, the line would only wait in the outbox, so this
    function tells the desk as well. `desk=False` is for a caller that has told the desk itself.

    The line goes into the queue with no key. A streak returns its line once. A later streak
    that starts at the same minute of another day makes the same line, and that line must go
    out again.
    """
    if not line:
        return
    run.box.send("", "alert", line)
    if desk and streak(run.config.state_dir, webhook(run.project.name)):
        wake.notify(line)


def tell(run: wake.Pass, key: str, line: str | None) -> None:
    """Deliver the line that a streak of this project returned, and only then mark the streak."""
    if line:
        webhook_recovered = key == webhook(run.project.name) and line.startswith("recovered")
        deliver(run, line, desk=not webhook_recovered)
        told(run.config.state_dir, key)


def flush(run: wake.Pass) -> int:
    """Post what waits for the project to each of its webhooks, and count each webhook's
    streak by how the post went. Return how many events the project's own webhook accepted.

    This function posts to the project's own webhook first, so that an alert from that webhook's
    streak goes to the top-level webhook in the same pass. For a project with no top-level route any
    more, it ends that streak with no line and drops what waited for the route. If the top-level
    pair comes back later, the route gets only what is new. It also posts to the second target
    before the others, with its own streak, so that an alert from that streak goes to the others in
    the same pass. The same holds for the second target: for a project with no second target any
    more, it ends that streak with no line and drops what waited for the target.
    """
    state, name = run.config.state_dir, run.project.name
    if run.box.blocking is None:
        retire(state, blocking(name))
        run.box.drop_blocking()
    else:
        ended: list[str] = []
        run.box.flush_blocking(run.now, run.say, went=ended.append)
        _count(run, blocking(name), ended)
    sent = 0
    for route in run.box.routes:
        key = top_level(name) if route.top else webhook(name)
        went: list[str] = []
        took = run.box.flush(run.now, run.say, route=route, went=went.append)
        sent = sent if route.top else took
        _count(run, key, went)
    if not any(route.top for route in run.box.routes):
        retire(state, top_level(name))
        run.box.drop_top_level()
    return sent


def _count(run: wake.Pass, key: str, went: list[str]) -> None:
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
            run = wake.Pass(config, one, now, say)
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
            deliver(wake.Pass(config, one, now, say), line, desk=False)
        except Exception as error:
            say(f"recovered failed {one.name}: {why(error, one)}")
    told(config.state_dir, key)
