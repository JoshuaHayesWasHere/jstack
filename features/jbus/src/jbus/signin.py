"""jbus reminds the user that jbus's sign-in to T3 Code is running out. Once the sign-in has
run out, jbus launches nothing until `jbus t3 login` signs in again. So jbus warns the user
beforehand, with an open alert of the machine's (`jbus.alert`).

jbus counts the days left by the calendar of the user's zone, from the day of the pass to the
day the stored token runs out (`jsettings.t3.expiry`). The alert gives the expiry and the days
left. It opens on the first pass `WEEK` days out or fewer, says the days left again each day from
`DAILY` days out, the day it runs out included, and says it ran out on the first pass after that.
Each change of what it says is a new line of the one alert, `sign-in`, so its home hears it once.
A sign-in renewed beyond `WEEK` days ends the alert.

The sign-in is the machine's, so the alert's owner is the machine: it goes to the desk and the
infra home (`jbus.Config.owner`), and is checked once a pass, in a chore of the pass.

The `sign_in` line of each project in the status file is separate from the alert, and stays as it
was: `expiring`, within `warn_days`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import jsettings
from jbus import Config, alert, verbs
from jsettings import t3

WEEK = 7
DAILY = 3
KIND = "sign-in"
WHOSE = "jbus's T3 sign-in"


def _days(expires: datetime, now: datetime, user: jsettings.Settings) -> int:
    return (user.local(expires).date() - user.local(now).date()).days


def due(expires: datetime, now: datetime, user: jsettings.Settings) -> str | None:
    """Return the alert's line for a pass at `now`, or None while none is due. From `DAILY` days
    out the line names the days left, so it changes each day; before then it says a week."""
    stamp = user.stamp(expires)
    if now >= expires:
        return f"{KIND}: {WHOSE} expired {stamp}, no days left: run jbus t3 login"
    days = _days(expires, now, user)
    if days > WEEK:
        return None
    left = "at most a week left" if days > DAILY else f"{days} day{'' if days == 1 else 's'} left"
    return f"{KIND}: {WHOSE} expires {stamp}, {left}: run jbus t3 login"


def remind(config: Config, now: datetime) -> None:
    """Open the sign-in alert with the line due at `now`, or end it when none is due."""
    expires = t3.expiry(config.token_path)
    if expires is None:
        return
    line = due(expires, now, config.user)
    if line is None:
        alert.retire(config.state_dir, KIND)
    else:
        alert.raise_(config, KIND, line, now=now)


def plan(config: Config, now: datetime) -> str:
    """Return what `jbus status` says of the reminder: who receives it, and the days still
    ahead."""
    expires = t3.expiry(config.token_path)
    if expires is None:
        return "none: no sign-in is stored"
    infra = config.owner(alert.MACHINE)
    where = f"the desk and the home of {infra.name}" if infra else "the desk"
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
