"""The reminder that jbus's sign-in to T3 Code runs out. jbus launches nothing once it has,
until `jbus t3 login` signs in again, so the user is told before, as a `sign-in` event.

The days left are counted by the calendar of the user's zone, from the day of the pass to the
day the stored token runs out (`t3.expiry`). The reminder says, each time with the expiry and
the days left:

- once, on the first pass `WEEK` days out or fewer;
- once a day from `DAILY` days out, the day it runs out included;
- once more, on the first pass after it has run out.

A pass says the mark it is in, and nothing for one it has passed by: a first pass 2 days out
says that day and not the week. What is said is kept by the expiry it was said of, so an
expiry later than the last one seen is a renewal: it is said once, with the new expiry, and
the count starts over. The expiry last seen is in `sign-in.json` in jbus's state. The first
expiry jbus sees is no renewal.

It is the machine's sign-in, so it is told once and not once a project: it is queued in the
box of the config's first project as an event of the machine (`wake.Box.send`), which waits
for the top-level webhook alone, and that project's flush posts it. `jbus events` of that
project lists it.

The `sign_in` line of each project in the status file is another thing, and stays as it was:
`cli.expiring`, within `warn_days`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import jsettings
from jbus import Config, read_json, t3, wake, write_json

EVENTS = {"sign-in": "user"}
WEEK = 7
DAILY = 3
KIND = "sign-in"
WHOSE = "jbus's T3 sign-in"


def _path(config: Config) -> Path:
    return config.state_dir / "sign-in.json"


def _days(expires: datetime, now: datetime, user: jsettings.Settings) -> int:
    return (user.local(expires).date() - user.local(now).date()).days


def due(expires: datetime, now: datetime, user: jsettings.Settings) -> tuple[str, str] | None:
    """The mark a pass at `now` is in and its line, or None where it is in none."""
    stamp = user.stamp(expires)
    if now >= expires:
        return "passed", f"{KIND}: {WHOSE} expired {stamp}, no days left: run jbus t3 login"
    days = _days(expires, now, user)
    if days > WEEK:
        return None
    mark = f"day {days}" if days <= DAILY else "week"
    left = "1 day left" if days == 1 else f"{days} days left"
    return mark, f"{KIND}: {WHOSE} expires {stamp}, {left}: run jbus t3 login"


def remind(config: Config, now: datetime) -> None:
    """Queue what the reminder owes at `now`, in the first project's box, and keep the expiry."""
    expires = t3.expiry(config.token_path)
    if expires is None or not config.projects:
        return
    box = wake.Box(config.state(config.projects[0]), config.projects[0], config.webhook)
    seen = read_json(_path(config), {}).get("expires")
    stamp = expires.isoformat()
    if seen and datetime.fromisoformat(seen) < expires:
        line = f"{KIND}: {WHOSE} was renewed, and now expires {config.user.stamp(expires)}"
        box.send("", KIND, line, key=f"{KIND}||renewed {stamp}", machine=True)
    if seen != stamp:
        write_json(_path(config), {"expires": stamp})
    found = due(expires, now, config.user)
    if found:
        mark, line = found
        box.send("", KIND, line, key=f"{KIND}||{stamp} {mark}", machine=True)


def plan(config: Config) -> str:
    """What `jbus status` says of the reminder: where it goes and on which days."""
    expires = t3.expiry(config.token_path)
    if expires is None:
        return "none: no sign-in is stored"
    last = config.user.local(expires).date()
    first, daily = (str(last - timedelta(days=days)) for days in (WEEK, DAILY))
    return (
        f"{KIND} to the top-level webhook on {first}, each day from {daily}, "
        f"and when it runs out at {config.user.stamp(expires)}"
    )
