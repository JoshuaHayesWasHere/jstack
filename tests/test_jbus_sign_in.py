"""The reminder that jbus's sign-in to T3 Code runs out (`jbus.signin`): a `sign-in` event for
the user on the first pass 7 days out or fewer, once a day from 3 days out, and once more
when it has run out, and once when a renewal lands. It is posted to the top-level webhook,
once for the machine, and not to a project's own.

Every test runs the real pass against the faked T3 Code server and webhooks of
`test_jbus_kitchen`, with a fake clock: each pass is given its time. Nothing reaches the
network.
"""

import json
from datetime import UTC, datetime

import pytest

import jbus
from jbus import cli
from test_jbus_kitchen import KEY, NOW, TOKEN, Webhook

EXPIRES = datetime(2026, 10, 20, 21, 8, tzinfo=UTC)
RENEWED = datetime(2026, 11, 19, 22, 8, tzinfo=UTC)
STAMP = "2026-10-20 17:08 ET"


@pytest.fixture
def top():
    fake = Webhook()
    yield fake
    fake.close()


def expiring(kitchen, at):
    """The token as `jbus t3 login` stores it, running out at `at`."""
    stored = {
        "server": kitchen.t3.url,
        "token": {"access_token": TOKEN, "expires_in": int((at - NOW).total_seconds())},
        "obtained_at": NOW.timestamp(),
    }
    kitchen.write(kitchen.config_dir / "t3.json", json.dumps(stored))


@pytest.fixture
def machine(kitchen, top):
    """Two projects, each with a webhook of its own, and a top-level one beside them."""
    side = kitchen.second("side")
    kitchen.config(webhook_url=top.url + "/wake", webhook_key=KEY)
    expiring(kitchen, EXPIRES)
    return side


def said(top):
    return [say for post in top.said for say in post if "sign-in" in say]


def at_et(day, hour=9):
    """A time on a day of October 2026, at `hour` in the user's zone, ET, four hours behind."""
    return datetime(2026, 10, day, hour + 4, 0, tzinfo=UTC)


def left(days):
    return f"sign-in: jbus's T3 sign-in expires {STAMP}, {days}: run jbus t3 login"


EXPIRED = f"sign-in: jbus's T3 sign-in expired {STAMP}, no days left: run jbus t3 login"


def test_the_countdown_says_seven_days_out_then_each_of_the_last_days_and_the_end(
    kitchen, top, machine
):
    """A pass at 9:00 and one at 15:00 ET of each day, from 8 days out to a day after the end."""
    told = []
    for day in range(12, 22):
        for hour in (9, 15):
            kitchen.poll(at_et(day, hour))
            told.append((day, hour, said(top)))
            top.said.clear()
        if day == 20:
            kitchen.poll(at_et(20, 18))
            told.append((20, 18, said(top)))
            top.said.clear()
    nothing = []
    assert told == [
        (12, 9, nothing),
        (12, 15, nothing),
        (13, 9, [left("7 days left")]),
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


def test_it_is_posted_once_for_the_machine_to_the_top_level_webhook_alone(kitchen, top, machine):
    kitchen.poll(at_et(13))
    assert said(top) == [left("7 days left")]
    assert [say for post in kitchen.webhook.said for say in post if "sign-in" in say] == []
    assert [say for post in machine.webhook.said for say in post if "sign-in" in say] == []
    (event,) = [one for post in top.posts for one in post if one["event"] == "sign-in"]
    assert event["loud"] == "user"


def test_it_is_in_the_event_log_of_the_first_project(kitchen, top, machine):
    kitchen.poll(at_et(13))
    assert kitchen.lines("sign-in") == [left("7 days left")]
    code, printed = kitchen.main("--project", "demo", "events")
    assert code == 0
    assert [json.loads(line)["line"] for line in printed.splitlines()].count(
        left("7 days left")
    ) == 1


def test_a_first_pass_inside_the_last_days_says_that_day_and_not_the_week(kitchen, top, machine):
    kitchen.poll(at_et(18))
    assert said(top) == [left("2 days left")]


def test_a_renewal_is_said_once_and_the_countdown_starts_over(kitchen, top, machine):
    kitchen.poll(at_et(17))
    assert said(top) == [left("3 days left")]
    top.said.clear()
    expiring(kitchen, RENEWED)
    kitchen.poll(at_et(17, 15))
    kitchen.poll(at_et(18))
    assert said(top) == [
        "sign-in: jbus's T3 sign-in was renewed, and now expires 2026-11-19 17:08 ET"
    ]
    top.said.clear()
    kitchen.poll(datetime(2026, 11, 11, 13, 0, tzinfo=UTC))
    assert said(top) == []
    kitchen.poll(datetime(2026, 11, 12, 14, 0, tzinfo=UTC))
    assert said(top) == [
        "sign-in: jbus's T3 sign-in expires 2026-11-19 17:08 ET, 7 days left: run jbus t3 login"
    ]


def test_the_first_expiry_jbus_sees_is_no_renewal(kitchen, top, machine):
    kitchen.poll(at_et(12))
    assert said(top) == [] and kitchen.lines("sign-in") == []


def test_with_no_top_level_webhook_it_goes_to_the_first_project_s_own(kitchen):
    kitchen.second("side")
    expiring(kitchen, EXPIRES)
    kitchen.poll(at_et(13))
    assert [say for post in kitchen.webhook.said for say in post] == [left("7 days left")]


def test_with_no_sign_in_stored_nothing_is_said(kitchen, top, machine):
    (kitchen.config_dir / "t3.json").unlink()
    cli.poll(jbus.load(), at_et(13), lambda _: None)
    assert said(top) == [] and kitchen.lines("sign-in") == []


def test_status_names_the_reminder_and_keeps_the_sign_in_line(kitchen, top, machine):
    kitchen.poll(at_et(12))
    status = kitchen.status()
    assert status["sign_in_reminder"] == (
        "sign-in to the top-level webhook on 2026-10-13, each day from 2026-10-17, "
        f"and when it runs out at {STAMP}"
    )
    assert status["projects"]["demo"]["sign_in"] == ""
    kitchen.poll(at_et(17))
    assert kitchen.status()["projects"]["demo"]["sign_in"] == (
        "T3 sign-in expires 2026-10-20 ET, run jbus t3 login"
    )


def test_status_with_no_sign_in_says_so(kitchen):
    (kitchen.config_dir / "t3.json").unlink()
    config = jbus.load()
    assert cli.status(config, NOW)["sign_in_reminder"] == "none: no sign-in is stored"
