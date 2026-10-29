"""The open alerts: each failure that repeats, each incident, and each line jbus raises once, kept
until it ends. This module is the only place that keeps a streak.

A streak is the failures in a row of one thing, under a key:

- `pass` for a pass that did not finish;
- `home thread <project>` for a wake of the project's that its home thread did not get;
- `blocking <project>` for a body of the project's that the second target did not take;
- `jmerge <project>` for a `jmerge` that did not run;
- `snapshot` for a snapshot of the homes' state tree that did not finish;
- `stale` for a look by `jbus alarm --stale` that found no pass ended within its limit;
- `health <check>` for an incident `jbus.health` found;
- `sign-in` for jbus's sign-in to T3 Code running out (`jbus.signin`);
- `home-stall <home>` for a home quiet with work out (`jbus.children`);
- `once <digest>` for a line raised once, which ends by itself after `LASTS` (`deliver`).

`failed` counts one failure, and returns the alert line once the count has reached the threshold.
`ok` ends the streak, and returns the recovered line when the streak had alerted. An incident is a
streak that `opened` starts and `closed` ends, with the line its caller passes. Everything else is
silent: the failures before the threshold, the ones after the alert, and a success with no alert
before it.

A streak that alerted is an open item of the one list (`jbus.wakes`), and that list is how a home
hears of it. `raise_` opens it with its `owner`: a project's name, or `MACHINE` for what belongs to
no project. `jbus.Config.owner` turns the owner into the one project whose home gets it: that
project, or for the machine and for a name no project has, the infra project. An alert of the
machine's is also raised on the desk when it opens. An alert that ends leaves the list and wakes
no one. Each line is logged once in the owning project's events, as a quiet event.

The streaks are in `streaks.json`. Only this module writes that file, and it writes under a
lock, because `jbus alarm` and `jbus snapshot` run outside the pass lock and may count while a pass
ends another streak. The status file shows a copy, under `streaks`.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jbus
import jsettings
from jbus import locked, passes, read_json, verbs, wake, write_json

LOCK = "streaks.lock"
EVENTS = {"alert": "quiet", "recovered": "quiet"}
RECOVERED = "recovered"
AFTER = 3
PASS = "pass"
SNAPSHOT = "snapshot"
STALE = "stale"
MACHINE = ""
LASTS = timedelta(days=1)


@dataclass
class Streak:
    """One streak, under its key, with `why` the cause of its last failure. Once `alerted` it is an
    open item: `line` is what it says, and `owner` whose it is. `ends` is when a line raised once
    leaves the list by itself."""

    key: str
    count: int
    since: str
    alerted: bool
    owner: str = MACHINE
    line: str = ""
    ends: str = ""
    why: str = ""


def home(project: str) -> str:
    return f"home thread {project}"


def blocking(project: str) -> str:
    return f"{wake.BLOCKING} {project}"


def jmerge(project: str) -> str:
    return f"jmerge {project}"


def _path(state: Path) -> Path:
    return state / "streaks.json"


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
    with locked(state, LOCK):
        one = streak(state, key) or Streak(key, 0, now.isoformat(), False)
        one.count, one.why = one.count + 1, why
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
    with locked(state, LOCK):
        one = streak(state, key)
        if one is not None and not one.alerted:
            _keep(state, key, None)
    if one is None or not one.alerted:
        return None
    return f"recovered: {key} after {one.count} failures since {_since(one, user)}"


def raise_(
    config: jbus.Config, key: str, line: str, *, owner: str = MACHINE, now: datetime, ends: str = ""
) -> None:
    """Open the alert under `key` for `owner`, or give an open one this line, and log the line in
    the owning project's events. Raise it on the desk when it opens and is the machine's: what no
    project owns. A line raised once ends by itself at `ends`, which `raise_` prunes."""
    state = config.state_dir
    with locked(state, LOCK):
        one = streak(state, key) or Streak(key, 1, now.isoformat(), False)
        new = not one.alerted or one.line != line
        one.alerted, one.owner, one.line, one.ends = True, owner, line, ends
        _keep(state, key, one)
        for name, kept in streaks(state).items():
            if kept.get("ends") and datetime.fromisoformat(kept["ends"]) <= now:
                _keep(state, name, None)
    if not new:
        return
    _log(config, owner, "alert", line)
    if owner not in {one.name for one in config.projects}:
        wake.notify(line)


def end(config: jbus.Config, key: str, line: str) -> None:
    """End the alert under `key`, which leaves the list, and log the recovered line."""
    one = streak(config.state_dir, key)
    retire(config.state_dir, key)
    if one is not None:
        _log(config, one.owner, "recovered", line)


def _log(config: jbus.Config, owner: str, kind: str, line: str) -> None:
    project = config.owner(owner)
    if project is not None:
        wake.Box(config.state(project), project).send("", kind, line)


def open_items(state: Path, now: datetime) -> list[Streak]:
    """Every alert that is open now, the items of the one list."""
    found = [Streak(**one) for one in streaks(state).values()]
    return [
        one
        for one in found
        if one.alerted and (not one.ends or datetime.fromisoformat(one.ends) > now)
    ]


def opened(config: jbus.Config, key: str, line: str, *, now: datetime) -> str | None:
    """Open an incident of the machine's under `key`, and return `alert: <line>` when this look
    found it. A later look leaves the line as it was opened, so a number that moves wakes no
    one again. An incident is not a failure in a row, so its count stays 1."""
    if streak(config.state_dir, key) is not None:
        return None
    said = f"alert: {line}"
    raise_(config, key, said, now=now)
    return said


def closed(config: jbus.Config, key: str, line: str) -> str | None:
    """End the incident under `key`, and return `recovered: <line>`, or nothing where there is
    none."""
    if streak(config.state_dir, key) is None:
        return None
    said = f"{RECOVERED}: {line}"
    end(config, key, said)
    return said


def recovered(config: jbus.Config, say: Callable[[str], None]) -> None:
    """After a pass in which nothing raised, end the `PASS` streak and the `STALE` one."""
    for key in (PASS, STALE):
        line = ok(config.state_dir, key, user=config.user)
        if line:
            end(config, key, line)
            say(line)


def retire(state: Path, key: str) -> None:
    """End a streak with no line, since what counted it is gone or its alert ended."""
    with locked(state, LOCK):
        if key in streaks(state):
            _keep(state, key, None)


def deliver(run: passes.Pass, line: str | None) -> None:
    """Raise a line of the project's once, an alert that ends by itself after `LASTS`. Its key is
    the line's, so the same line raised again is the same alert."""
    if not line:
        return
    run.say(f"{run.project.name}: {line}")
    key = f"once {hashlib.sha256(line.encode()).hexdigest()[:12]}"
    ends = (run.now + LASTS).isoformat()
    raise_(run.config, key, line, owner=run.project.name, now=run.now, ends=ends)


def tell(run: passes.Pass, key: str, line: str | None) -> None:
    """Raise the alert line that a streak of this project returned, or end the alert with the
    recovered line. A failing route to the project's home thread or its second target is the
    machine's: that home cannot be told of it."""
    if not line:
        return
    name = run.project.name
    run.say(f"{name}: {line}")
    if line.startswith(f"{RECOVERED}: "):
        end(run.config, key, line)
        return
    owner = MACHINE if key in (home(name), blocking(name)) else name
    raise_(run.config, key, line, owner=owner, now=run.now)


def flush(run: passes.Pass) -> None:
    """Post what waits for the project's second target, and count its streak by how the post
    went. For a second target the config does not have any more, drop what waited for it, and if
    the pair comes back later, it gets only what is new."""
    state, name = run.config.state_dir, run.project.name
    if run.box.blocking is None:
        retire(state, blocking(name))
        run.box.drop(wake.BLOCKING)
        return
    ended: list[str] = []
    run.box.flush_blocking(run.now, run.say, went=ended.append)
    count(run, blocking(name), ended)


def count(run: passes.Pass, key: str, went: list[str]) -> None:
    """Count a route's streak by how its sends ended, and tell the line the streak returns."""
    state = run.config.state_dir
    for why in went:
        said = (
            failed(state, key, why, now=run.now, user=run.user)
            if why
            else ok(state, key, user=run.user)
        )
        tell(run, key, said)


def why(error: Exception, config: jbus.Config) -> str:
    """Format an exception as one line, for the journal and the status file.

    An error from a URL of the second target that cannot be used quotes the URL, whole or in part,
    so this function removes the pair's secrets from it (`jbus.secrets`).
    """
    said = " ".join(f"{type(error).__name__}: {error}".split())
    return wake.cut(jbus.redact(said, jbus.secrets(config.blocking, part=2), "[redacted]"), 300)


def sound(
    config: jbus.Config,
    key: str,
    cause: str,
    after: int,
    now: datetime,
    say: Callable[[str], None],
    owner: str = MACHINE,
) -> None:
    """Count one failure of a unit that runs outside the pass, and raise its alert for `owner`
    once it is due. The next pass carries it to the owner's home."""
    line = failed(config.state_dir, key, cause, after, now=now, user=config.user)
    if line:
        say(line)
        raise_(config, key, line, owner=owner, now=now)


def recover(config: jbus.Config, key: str, say: Callable[[str], None]) -> None:
    """Record that a unit outside the pass succeeded: end its streak, and its alert if it had
    one."""
    line = ok(config.state_dir, key, user=config.user)
    if line:
        say(line)
        end(config, key, line)


def failing(run: passes.Pass) -> str | None:
    """Return the alert line of the home thread's streak once it alerted, with the last error the
    home thread gave, or None."""
    one = streak(run.config.state_dir, home(run.project.name))
    return one.line if one is not None and one.alerted else None


def _wakes(args: argparse.Namespace, config: jbus.Config) -> int:
    """Run `jbus wakes`: say whether the project's wakes can come to its home thread, so that a
    thread knows whether to wait for one."""
    run = passes.Pass(config, verbs.here(config, args.project), datetime.now(UTC))
    line = failing(run)
    if line:
        print(f"wakes fail: {line}")
        return 1
    print(f"wakes go: the home thread of {run.project.name} is not failing")
    return 0


VERBS = (
    verbs.Verb(
        "wakes", "whether the wakes of this repo's project are failing", verbs.nothing, _wakes
    ),
)
