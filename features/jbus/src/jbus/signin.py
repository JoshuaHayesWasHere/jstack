"""jbus reminds the user that its sign-in to T3 Code runs out. Once the sign-in has run out,
jbus launches nothing until `jbus t3 login` signs in again, so it tells the user beforehand,
with a `sign-in` event.

jbus counts the days left by the calendar of the user's zone, from the day of the pass to the
day the stored token runs out (`t3.expiry`). The reminder gives the expiry and the days left
each time, and comes:

- once, on the first pass `WEEK` days out or fewer;
- once a day from `DAILY` days out, the day it runs out included;
- once more, on the first pass after it has run out.

A pass gives the reminder of the mark it is in, and none for a mark it has already passed: a
first pass 2 days out gives that day's reminder and not the week's. jbus keeps the expiry it
last saw, and the marks it gave for it, in `sign-in.json` in its state. So adding, removing or
moving a project in the config repeats no mark. An expiry later than the last one seen is a
renewal. jbus says it once, with the new expiry, and the count starts over. The first expiry
jbus sees is not a renewal. When jbus cannot read the file, the expiry it finds is not one
either.

The sign-in is the machine's, so jbus gives the reminder once, not once for each project. It
queues the reminder in the box of the config's first project, as an event of the machine
(`wake.Box.send`). Such an event waits for the top-level webhook alone
(`wake.Box.machine_route`), and that project's flush posts it. `jbus events` of that project
lists it.

The `sign_in` line of each project in the status file is separate from the reminder, and
stays as it was: `expiring`, within `warn_days`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import jsettings
from jbus import Config, read_json, t3, verbs, wake, write_json

EVENTS = {"sign-in": "user"}
WEEK = 7
DAILY = 3
KIND = "sign-in"
WHOSE = "jbus's T3 sign-in"


def _path(config: Config) -> Path:
    return config.state_dir / "sign-in.json"


def _kept(config: Config) -> tuple[datetime | None, list[str]]:
    """Return the expiry last seen and the marks given for it. A file jbus cannot read as one
    counts as no expiry seen: the count starts there, and gives no renewal."""
    kept = read_json(_path(config), {})
    try:
        return datetime.fromisoformat(kept["expires"]), [str(mark) for mark in kept["said"]]
    except (KeyError, TypeError, ValueError):
        return None, []


def _days(expires: datetime, now: datetime, user: jsettings.Settings) -> int:
    return (user.local(expires).date() - user.local(now).date()).days


def due(expires: datetime, now: datetime, user: jsettings.Settings) -> tuple[str, str] | None:
    """Return the mark a pass at `now` is in and its line, or None if the pass is in none."""
    stamp = user.stamp(expires)
    if now >= expires:
        return "passed", f"{KIND}: {WHOSE} expired {stamp}, no days left: run jbus t3 login"
    days = _days(expires, now, user)
    if days > WEEK:
        return None
    mark = f"day {days}" if days <= DAILY else "week"
    left = "1 day left" if days == 1 else f"{days} days left"
    return mark, f"{KIND}: {WHOSE} expires {stamp}, {left}: run jbus t3 login"


def _box(config: Config) -> wake.Box:
    return wake.Box(config.state(config.projects[0]), config.projects[0], config.webhook)


def remind(config: Config, now: datetime) -> None:
    """Queue what the reminder owes at `now`, then keep the expiry and the marks given for it.

    jbus keeps the marks beside the expiry, not in the box, so which project is first does
    not decide what was said. A new expiry starts the marks over. jbus writes the marks after
    it queues the lines, so a pass that stops between the two gives a mark again, and never
    loses one.
    """
    expires = t3.expiry(config.token_path)
    if expires is None or not config.projects:
        return
    seen, said = _kept(config)
    owed = []
    if seen != expires:
        said = []
        if seen is not None and seen < expires:
            stamp = config.user.stamp(expires)
            owed.append(("renewed", f"{KIND}: {WHOSE} was renewed, and now expires {stamp}"))
    found = due(expires, now, config.user)
    if found and found[0] not in said:
        owed.append(found)
    if seen == expires and not owed:
        return
    box = _box(config)
    for _, line in owed:
        box.send("", KIND, line, machine=True)
    marks = [*said, *(mark for mark, _ in owed)]
    write_json(_path(config), {"expires": expires.isoformat(), "said": marks})


def plan(config: Config, now: datetime) -> str:
    """Return what `jbus status` says of the reminder: the webhook it goes to, and the days
    still ahead."""
    expires = t3.expiry(config.token_path)
    if expires is None:
        return "none: no sign-in is stored"
    if not config.projects:
        return "none: the config has no project to carry it"
    first_project = config.projects[0]
    if config.webhook[0]:
        where = "the top-level webhook"
    elif first_project.webhook_url:
        where = f"the webhook of {first_project.name}"
    else:
        return f"none: no top-level webhook, and {first_project.name} has none of its own"
    stamp = config.user.stamp(expires)
    if now >= expires:
        return f"{KIND} to {where}: it ran out at {stamp}, run jbus t3 login"
    last = config.user.local(expires).date()
    first, daily = (str(last - timedelta(days=days)) for days in (WEEK, DAILY))
    days = _days(expires, now, config.user)
    if days > WEEK:
        ahead = f"on {first}, each day from {daily}"
    elif days > DAILY:
        ahead = f"each day from {daily}"
    else:
        ahead = f"each day to {last}"
    return f"{KIND} to {where} {ahead}, and when it runs out at {stamp}"


def expiring(config: Config, now: datetime) -> str:
    """Return the line for a sign-in within `warn_days` of running out, or nothing."""
    expires = t3.expiry(config.token_path)
    if expires is None or expires - now > timedelta(days=config.warn_days):
        return ""
    user = config.user
    return f"T3 sign-in expires {user.day(expires)} {user.word(expires)}, run jbus t3 login"


CHORES = (verbs.Chore(10, "the sign-in reminder", lambda config, _, now, __: remind(config, now)),)
