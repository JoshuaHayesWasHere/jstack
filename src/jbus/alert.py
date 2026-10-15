"""A failure that repeats is told once, and so is its end. This is the only place a streak lives.

A streak is the failures in a row of one thing, under a key: `pass` for a pass that did not
finish, `webhook <project>` for a POST the project's own webhook did not take, `top-level
webhook <project>` for a POST of the project's that the top-level webhook did not take,
`jmerge <project>` for a `jmerge` that did not run. `failed` counts one and gives the alert
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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import jsettings
from jbus import read_json, wake, write_json

EVENTS = {"alert": "user"}
AFTER = 3
PASS = "pass"


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
    same pass. A project with no top-level route any more ends that streak, with no line.
    """
    state, name = run.config.state_dir, run.project.name
    sent = 0
    for route in run.box.routes:
        key = top_level(name) if route.top else webhook(name)
        went: list[str] = []
        took = run.box.flush(run.now, run.say, route=route, went=went.append)
        sent = sent if route.top else took
        for why in went:
            said = (
                failed(state, key, why, now=run.now, user=run.user)
                if why
                else ok(state, key, user=run.user)
            )
            tell(run, key, said)
    if not any(route.top for route in run.box.routes):
        retire(state, top_level(name))
    return sent
