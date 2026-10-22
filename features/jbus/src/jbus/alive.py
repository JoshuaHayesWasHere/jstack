"""`jbus alarm`: count a pass that did not finish, or, with `--stale`, look for a pass that
ended within a limit. `jbus-failed.service` runs the first when a pass fails.
`jbus-stale.timer` runs the second, so jbus also notices a pass timer that is stopped.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jbus
from jbus import alert, record, verbs

ALARM = "the last pass did not finish (see journalctl --user -u jbus)"


def alarm(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Count a pass that did not finish. On the third in a row, alert every project and the
    desk, once (`alert.sound`)."""
    now = now or datetime.now(UTC)
    failing = alert.streak(config.state_dir, alert.PASS)
    say(f"pass failed: {failing.count + 1 if failing else 1} in a row")
    return alert.sound(config, alert.PASS, ALARM, alert.AFTER, now, say)


SPAN = re.compile(r"([1-9][0-9]*)([mhd])")
UNITS = {"m": "minutes", "h": "hours", "d": "days"}
SIZES = (("d", 1440), ("h", 60), ("m", 1))


def span(given: str) -> timedelta:
    """Parse a limit as the user types it: a number and m, h or d, as `2h`."""
    found = SPAN.fullmatch(given)
    if found is None:
        raise argparse.ArgumentTypeError(f"a limit is a number and m, h or d, as 2h: not {given}")
    return timedelta(**{UNITS[found[2]]: int(found[1])})


def _shown(limit: timedelta) -> str:
    """Write a limit the way `span` reads it, in its largest whole unit."""
    minutes = int(limit.total_seconds() // 60)
    return next(f"{minutes // size}{unit}" for unit, size in SIZES if minutes % size == 0)


def stale(
    config: jbus.Config,
    limit: timedelta,
    now: datetime | None = None,
    say: Callable[[str], None] = print,
) -> int:
    """Look for a pass that ended within `limit`. A timer of its own runs this look. So jbus
    also sees a `jbus.timer` that is stopped or a `jbus.service` that never starts, which
    `jbus-failed.service` does not see, since it runs only when a pass fails.

    The last pass is the `ended` of `pass.json`, or its `started` while a pass runs or after
    a pass that died. When the last pass is past the limit, or there is no record at all, the
    look counts a failure of the `stale` streak. That streak alerts once, at its first failure
    (`alert.sound`). The next pass in which nothing raised ends the streak and says that it
    recovered (`poll`).
    """
    now = now or datetime.now(UTC)
    kept = record.read(config)
    last = kept.get("ended") or kept.get("started")
    if not isinstance(last, str):
        say("no pass: none on record")
        return alert.sound(config, alert.STALE, "no pass on record", 1, now, say)
    ended = datetime.fromisoformat(last)
    if now - ended <= limit:
        say(f"pass seen: last ended {config.user.clock(ended)}")
        return 0
    at = config.user.stamp(ended)
    say(f"no pass: last ended {at}")
    why = f"no pass ended since {at}, more than {_shown(limit)} ago"
    return alert.sound(config, alert.STALE, why, 1, now, say)


def _stale(shown: argparse.ArgumentParser) -> None:
    shown.add_argument(
        "--stale",
        type=span,
        metavar="LIMIT",
        help="look for a pass that ended within LIMIT (as 2h) instead: past it alerts, once",
    )


def run_alarm(args: argparse.Namespace, config: jbus.Config) -> int:
    return alarm(config) if args.stale is None else stale(config, args.stale)


VERBS = (
    verbs.Verb(
        "alarm",
        "count a pass that did not finish: the third in a row alerts",
        _stale,
        run_alarm,
    ),
)
