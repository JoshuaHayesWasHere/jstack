"""A hold nobody works on wakes its home (fl-hold-wakes). Rows whose pull requests `jmerge` holds
on one reason for longer than `clock.HOLD_MINUTES`, with no thread at work on the cause, wake the
home that owns the rows once, and the hold is on what waits on the user until it clears or a
thread takes it up. The tests replay small made-up rows through the real pass against the
kitchen's fakes, a pass a minute."""

from datetime import timedelta

import pytest

import jbus
from jmerge import ready
from test_jbus_kitchen import NOW, sends
from test_jbus_leftover import home

ROWS = ("one", "two", "three", "four")
SHA = "abcdef123456"
REASON = ready.MAIN_RED.format(sha=SHA)
RESULT = "\n## Result\nStatus: done\nBranch: {slug}   Pull request: {url}\nLeft: none\n"


def url(number):
    return f"https://example.test/pull/{number}"


class Held:
    """Four rows ended their turns with their pull requests open, #11 to #14, and a home owns
    them. A first pass has recorded what is so, and from minute 0 `jmerge` says each one waits on
    the same reason."""

    def __init__(self, kitchen, reason=REASON):
        self.kitchen = kitchen
        self.desk = home(kitchen)
        self.crews = {}
        for number, slug in enumerate(ROWS, start=11):
            kitchen.brief(slug, RESULT.format(slug=slug, url=url(number)))
            self.crews[slug] = kitchen.t3.thread(slug, "completed", idle=timedelta(hours=2))
        opened = [kitchen.opened(slug, number) for number, slug in enumerate(ROWS, start=11)]
        kitchen.set("open.json", opened)
        kitchen.quiet()
        self.say(reason)
        self.minute = 0

    def say(self, reason):
        lines = (f"wait {n} {url(n)}: {reason}\n" for n, _ in enumerate(ROWS, start=11))
        self.kitchen.set("jmerge.txt", "".join(lines) if reason else "")

    def until(self, minute):
        """Run a pass a minute, up to and with `minute`."""
        while self.minute <= minute:
            self.kitchen.poll(NOW + timedelta(minutes=self.minute))
            self.minute += 1

    def told(self):
        return [one["message"] for one in sends(self.kitchen) if one["threadId"] == self.home_id]

    @property
    def home_id(self):
        return self.desk["threadId"]

    def needs(self):
        listed = jbus.read_json(self.kitchen.state / "waiting-on-user.json", [])
        return [one for one in listed if one["kind"] == "held"]


def test_four_rows_held_31_minutes_with_nobody_at_work_wake_their_home_once(kitchen):
    held = Held(kitchen)
    held.until(31)
    (told,) = held.told()
    assert REASON in told and "31 minutes" in told
    assert all(f"{slug} (#{n})" in told for n, slug in enumerate(ROWS, start=11))
    (need,) = held.needs()
    assert need["rows"] == list(ROWS) and REASON in need["line"]
    held.until(60)
    assert len(held.told()) == 1 and len(held.needs()) == 1


def test_the_same_at_29_minutes_wakes_nobody_and_needs_nothing(kitchen):
    held = Held(kitchen)
    held.until(29)
    assert held.told() == [] and held.needs() == []


def test_a_running_fix_row_on_the_cause_wakes_nobody(kitchen):
    held = Held(kitchen)
    kitchen.t3.thread(f"main-red-{SHA}")
    held.until(45)
    assert held.told() == [] and held.needs() == []


def test_a_running_crew_of_a_held_row_wakes_nobody(kitchen):
    held = Held(kitchen)
    crew = held.crews["two"]
    crew["status"] = "running"
    kitchen.t3.at_work.add(crew["threadId"])
    held.until(45)
    assert held.told() == [] and held.needs() == []


def test_a_wait_on_the_merge_runner_wakes_nobody(kitchen):
    held = Held(kitchen, ready.GATE_BUSY)
    held.until(45)
    assert held.told() == [] and held.needs() == []


def test_the_hold_leaves_what_waits_on_the_user_once_it_clears_or_a_thread_takes_it_up(kitchen):
    held = Held(kitchen)
    held.until(31)
    assert len(held.needs()) == 1
    held.say("")
    held.until(32)
    assert held.needs() == []
    held.say(REASON)
    held.until(33)
    kitchen.t3.thread(f"main-red-{SHA}")
    held.until(70)
    assert held.needs() == [] and len(held.told()) == 1


AHEAD = "first"
FOLLOWS = (
    ready.MERGES_AFTER.format(slug=AHEAD, open=url(10)),
    ready.STACKED_ON.format(branch=AHEAD, slug=AHEAD, default="main"),
    ready.CARRIES_AFTER.format(carried="two", number=12, slug=AHEAD, open=url(10)),
    ready.MIGRATION_REBASING.format(number=10),
)


@pytest.mark.parametrize("reason", FOLLOWS)
def test_rows_that_wait_on_a_row_ahead_wake_nobody(kitchen, reason):
    """The row ahead, in CI or held by a reason of its own, is what holds them: its own wait is
    watched, so the rows behind it are no hold of their own."""
    held = Held(kitchen, reason)
    held.until(45)
    assert held.told() == [] and held.needs() == []
