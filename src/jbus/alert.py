"""A failure that repeats is told once, and so is its end. This is the only place a streak lives.

A streak is the failures in a row of one thing, under a key: `pass` for a pass that did not
finish, `webhook <project>` for a POST the project's own webhook did not take, `top-level
webhook <project>` for a POST of the project's that the top-level webhook did not take,
`blocking webhook <project>` for a body of the project's that the second target did not take,
`jmerge <project>` for a `jmerge` that did not run, `snapshot` for a snapshot of the homes'
state tree that did not finish. `failed` counts one and gives the alert
line once the count has reached the threshold. `ok` ends the streak, and gives the recovered
line when it had alerted. Everything else is silence: the failures before the threshold, the
ones after the alert, and a success with no alert before it.

A line is owed until `told` says it is queued, and only then is the streak marked: a
caller that raises, or is killed, between the line and the queue gets the line again on
its next count. So a line goes at least once, and twice only after such a break.

The streaks are in `streaks.json`, which only this module writes, under a lock: `jbus alarm`
runs outside the pass lock, and may count while a pass ends another streak. The status file
shows a copy, under `streaks`.
"""

from __future__ import annotations

import fcntl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import jbus
import jsettings
from jbus import read_json, wake, write_json

EVENTS = {"alert": "user"}
AFTER = 3
PASS = "pass"
SNAPSHOT = "snapshot"


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
    """Held from a streak's read to its write, so no count and no `alerted` is lost."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "streaks.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def streaks(state: Path) -> dict[str, dict]:
    """Every open streak, by key, as the status file shows them."""
    return read_json(_path(state), {})


def streak(state: Path, key: str) -> Streak | None:
    """The streak that is open under this key, or None when its last try went."""
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
    """Count one failure. The answer is the alert line, from the count `after` until `told`."""
    now = now or datetime.now(UTC)
    with _locked(state):
        one = streak(state, key) or Streak(key, 0, now.isoformat(), False)
        one.count += 1
        _keep(state, key, one)
    if one.count < after or one.alerted:
        return None
    return f"alert: {key} failed {one.count} times in a row since {_since(one, user)}: {why}"


def ok(state: Path, key: str, *, user: jsettings.Settings) -> str | None:
    """A try went. The answer is the recovered line of a streak that alerted, until `told`.

    A streak that had not alerted ends here, with no line.
    """
    with _locked(state):
        one = streak(state, key)
        if one is not None and not one.alerted:
            _keep(state, key, None)
    if one is None or not one.alerted:
        return None
    return f"recovered: {key} after {one.count} failures since {_since(one, user)}"


def told(state: Path, key: str) -> None:
    """The line `failed` or `ok` gave is queued: mark the streak alerted, or end it."""
    with _locked(state):
        one = streak(state, key)
        if one is None:
            return
        if one.alerted:
            _keep(state, key, None)
        else:
            one.alerted = True
            _keep(state, key, one)


def retire(state: Path, key: str) -> None:
    """End a streak nothing counts any more, with no line: what counted it is gone."""
    with _locked(state):
        if streak(state, key):
            _keep(state, key, None)


def deliver(run: wake.Pass, line: str | None, *, desk: bool = True) -> None:
    """Send an alert or a recovered line to the chat, and nothing when there is no line.

    While the project's webhook is failing the line would only wait in the outbox, so the
    desk is told as well. `desk=False` is for a caller that has told the desk itself.

    The line is queued with no key: a streak gives it once, and a later streak that starts
    at the same minute of another day makes the same line, which must go again.
    """
    if not line:
        return
    run.box.send("", "alert", line)
    if desk and streak(run.config.state_dir, webhook(run.project.name)):
        wake.notify(line)


def tell(run: wake.Pass, key: str, line: str | None) -> None:
    """Deliver the line a streak of this project gave, and only then mark the streak."""
    if line:
        webhook_recovered = key == webhook(run.project.name) and line.startswith("recovered")
        deliver(run, line, desk=not webhook_recovered)
        told(run.config.state_dir, key)


def flush(run: wake.Pass) -> int:
    """Post what waits for the project to each of its webhooks, and keep each webhook's streak
    by how that went. The answer is how many the project's own webhook took.

    The own webhook goes first, so an alert it gives is posted to the top-level one in the
    same pass. A project with no top-level route any more ends that streak, with no line, and
    drops what waited for it: a pair that comes back later is posted only what is new. The
    second target goes first, with its own streak, so an alert it gives is posted to the
    others in the same pass, and the same holds for it.
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
    """Keep a webhook's streak by how its flush ended, and tell what the streak gives."""
    state = run.config.state_dir
    for why in went:
        said = (
            failed(state, key, why, now=run.now, user=run.user)
            if why
            else ok(state, key, user=run.user)
        )
        tell(run, key, said)


def why(error: Exception, *hooks: jbus.Project | jbus.Hook) -> str:
    """An exception as one line, for the journal and the status file.

    An error from a webhook URL that cannot be used quotes it, whole or in part, so what
    is secret of each hook is taken out (`jbus.secrets`).
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
    """Count one failure of a unit that runs outside the pass, and alert once it is due.

    The alert goes to the desk and waits in each project's outbox like any other event, and
    what waits is flushed each time, so one the webhook did not take goes with the next alarm
    or the next pass that ends. The streak is marked alerted after the desk and the projects
    were told, so an alarm that is stopped before then alerts again on the next one.
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
    """A unit outside the pass went: end its streak, and tell each project it recovered when
    the streak had alerted."""
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
