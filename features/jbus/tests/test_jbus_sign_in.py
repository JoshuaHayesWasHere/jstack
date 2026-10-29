"""jbus reminds the user that its sign-in to T3 Code runs out (`jbus.signin`). The reminder is one
open alert of the machine's, `sign-in`: it opens on the first pass 7 days out or fewer, says the
days left each day from 3 days out, and says when the sign-in has run out. Each new line is told
once. The machine's alert goes to the desk and the infra home, and to no other project's home.

Every test runs the real pass against the faked T3 Code server of `test_jbus_kitchen`,
with a fake clock that gives each pass its time. Nothing reaches the network.
"""

import json
from datetime import UTC, datetime

import pytest

import jbus
from jbus import poll, record
from test_jbus_kitchen import NOW, TOKEN

EXPIRES = datetime(2026, 10, 20, 21, 8, tzinfo=UTC)
RENEWED = datetime(2026, 11, 19, 22, 8, tzinfo=UTC)
STAMP = "2026-10-20 17:08 ET"
TOP = "sign-in to the desk and the home of infra"


def expiring(kitchen, at):
    """Store the token as `jbus t3 login` stores it, running out at `at`."""
    stored = {
        "server": kitchen.t3.url,
        "token": {"access_token": TOKEN, "expires_in": int((at - NOW).total_seconds())},
        "obtained_at": NOW.timestamp(),
    }
    kitchen.write(kitchen.config_dir / "t3.json", json.dumps(stored))


@pytest.fixture
def infra(kitchen):
    """Set up the infra project beside demo, and what its home thread takes."""
    side = kitchen.second("infra")
    expiring(kitchen, EXPIRES)
    return side.wakes


def said(wakes):
    return [line for line in wakes.said if "sign-in" in line]


def at_et(day, hour=9):
    """Return a time on a day of October 2026, at `hour` in the user's zone, ET, which is four
    hours behind UTC."""
    return datetime(2026, 10, day, hour + 4, 0, tzinfo=UTC)


def left(days):
    return f"sign-in: jbus's T3 sign-in expires {STAMP}, {days}: run jbus t3 login"


WEEK = left("at most a week left")
EXPIRED = f"sign-in: jbus's T3 sign-in expired {STAMP}, no days left: run jbus t3 login"


def test_the_countdown_says_a_week_out_then_each_of_the_last_days_and_the_end(kitchen, infra):
    """The test runs a pass at 9:00 and one at 15:00 ET on each day, from 8 days out to a day
    after the end."""
    told = []
    for day in range(12, 22):
        for hour in (9, 15):
            kitchen.poll(at_et(day, hour))
            told.append((day, hour, said(infra)))
            infra.listed.clear()
        if day == 20:
            kitchen.poll(at_et(20, 18))
            told.append((20, 18, said(infra)))
            infra.listed.clear()
    nothing = []
    assert told == [
        (12, 9, nothing),
        (12, 15, nothing),
        (13, 9, [WEEK]),
        (13, 15, nothing),
        (14, 9, nothing),
        (14, 15, nothing),
        (15, 9, nothing),
        (15, 15, nothing),
        (16, 9, nothing),
        (16, 15, nothing),
        (17, 9, [left("3 days left")]),
        (17, 15, nothing),
        (18, 9, [left("2 days left")]),
        (18, 15, nothing),
        (19, 9, [left("1 day left")]),
        (19, 15, nothing),
        (20, 9, [left("0 days left")]),
        (20, 15, nothing),
        (20, 18, [EXPIRED]),
        (21, 9, nothing),
        (21, 15, nothing),
    ]


def test_it_goes_to_the_desk_and_the_infra_home_and_no_other(kitchen, infra):
    kitchen.poll(at_et(13))
    assert said(infra) == [WEEK]
    assert said(kitchen.wakes) == []
    assert kitchen.log("notify") == [f"jbus | {WEEK}"]


def test_it_is_in_the_event_log_of_the_infra_project(kitchen, infra):
    kitchen.poll(at_et(13))
    assert kitchen.lines("alert") == []
    code, printed = kitchen.main("--project", "infra", "events")
    assert code == 0
    assert [json.loads(line)["line"] for line in printed.splitlines()].count(WEEK) == 1


def test_with_no_infra_project_it_goes_to_the_desk_alone(kitchen):
    expiring(kitchen, EXPIRES)
    kitchen.poll(at_et(13))
    assert said(kitchen.wakes) == []
    assert kitchen.log("notify") == [f"jbus | {WEEK}"]


def test_a_first_pass_inside_the_last_days_says_that_day_and_not_the_week(kitchen, infra):
    kitchen.poll(at_et(18))
    assert said(infra) == [left("2 days left")]


def test_a_renewal_ends_the_alert_and_the_countdown_starts_over(kitchen, infra):
    kitchen.poll(at_et(17))
    assert said(infra) == [left("3 days left")]
    infra.listed.clear()
    expiring(kitchen, RENEWED)
    kitchen.poll(at_et(17, 15))
    kitchen.poll(at_et(18))
    assert said(infra) == [] and kitchen.status()["streaks"] == {}
    kitchen.poll(datetime(2026, 11, 11, 13, 0, tzinfo=UTC))
    assert said(infra) == []
    kitchen.poll(datetime(2026, 11, 12, 14, 0, tzinfo=UTC))
    assert said(infra) == [
        "sign-in: jbus's T3 sign-in expires 2026-11-19 17:08 ET, at most a week left: "
        "run jbus t3 login"
    ]


def test_more_than_a_week_out_nothing_is_said(kitchen, infra):
    kitchen.poll(at_et(12))
    assert said(infra) == [] and kitchen.log("notify") == []


def test_with_no_sign_in_stored_nothing_is_said(kitchen, infra):
    (kitchen.config_dir / "t3.json").unlink()
    poll.poll(jbus.load(), at_et(13), lambda _: None)
    assert said(infra) == [] and not [line for line in kitchen.log("notify") if "sign-in" in line]


def test_status_names_the_reminder_and_keeps_the_sign_in_line(kitchen, infra):
    kitchen.poll(at_et(12))
    status = kitchen.status()
    assert status["sign_in_reminder"] == (
        f"{TOP} on 2026-10-13, each day from 2026-10-17, and when it runs out at {STAMP}"
    )
    assert status["projects"]["demo"]["sign_in"] == ""
    kitchen.poll(at_et(17))
    assert kitchen.status()["projects"]["demo"]["sign_in"] == (
        "T3 sign-in expires 2026-10-20 ET, run jbus t3 login"
    )


def test_status_with_no_sign_in_says_so(kitchen):
    (kitchen.config_dir / "t3.json").unlink()
    config = jbus.load()
    assert record.status(config, NOW)["sign_in_reminder"] == "none: no sign-in is stored"


@pytest.mark.parametrize(
    ("day", "hour", "ahead"),
    [
        (
            15,
            9,
            f"{TOP} each day from 2026-10-17, and when it runs out at {STAMP}",
        ),
        (
            18,
            9,
            f"{TOP} each day to 2026-10-20, and when it runs out at {STAMP}",
        ),
        (20, 18, f"{TOP}: it ran out at {STAMP}, run jbus t3 login"),
    ],
)
def test_status_names_only_the_days_still_ahead(kitchen, infra, day, hour, ahead):
    kitchen.poll(at_et(day, hour))
    assert kitchen.status()["sign_in_reminder"] == ahead
