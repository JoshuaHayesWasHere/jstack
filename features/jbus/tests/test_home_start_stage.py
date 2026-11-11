"""The start of a home jbus launches (`jbus.children.launch`): a start whose run ended with no
`home-id` written is launched again on the next pass, a second start that failed on one cause waits
for it to clear, and the home's entry in `relaunches.json` says why it has no `home-id` yet until it
starts. #1392 launched again a catch-all whose start wrote no `home-id`; #1410 folded its test into
`test_a_start_that_failed_is_launched_again_on_the_next_pass` and added the others here."""

import json
from datetime import timedelta

import pytest

from jbus import children
from jroles import inventory
from test_children import P, homes, minutes
from test_jbus_failover import NOT_LOGGED_IN, SESSION, failed_on, lapsed_on
from test_jbus_kitchen import NOW
from test_jbus_leftover import home
from test_jbus_owed import signed_in
from test_jbus_queue import add, brief

SESSION_AT = NOW.replace(hour=3) + timedelta(days=1)
"""When SESSION's limit, 11pm New York on the kitchen's day, resets."""


@pytest.fixture
def started(kitchen):
    """A project whose home has started: a root `plan.md` and the root's thread."""
    home(kitchen)
    (kitchen.home / "plan.md").write_text("# plan\n")
    return kitchen


def launched(kitchen):
    """The thread of the last launch of the catch-all's home, as T3 Code lists it."""
    title = homes(kitchen)[-1]["title"]
    return [one for one in kitchen.t3.threads if one["title"] == title][-1]


def failed_at_once(kitchen, at, texts=(NOT_LOGGED_IN,)):
    """End the last launch's run within a second of its start, on `texts`, as a start on a
    signed-out instance ends."""
    thread = launched(kitchen)
    lapsed_on(thread, texts, run=f"run-{len(homes(kitchen))}", at=at)
    kitchen.t3.at_work.discard(thread["threadId"])
    return thread


def entry(kitchen, name="uncategorized"):
    """The home's entry in `relaunches.json`: its last launch and the stage of its start."""
    return json.loads((kitchen.state / "relaunches.json").read_text())[name]


def says(kitchen, name="uncategorized"):
    """What the sidebar shows of the home's start, from `relaunches.json`."""
    return entry(kitchen, name).get("says")


def test_a_launch_whose_reply_is_lost_is_at_intent_and_its_reply_moves_it_to_launched(started):
    """A launch is written before T3 Code is asked for its thread, so a reply that is lost
    leaves the start at `intent`, with no thread; the next launch's reply names its thread."""
    kitchen = started
    kitchen.t3.lose = "after"
    kitchen.poll(NOW)
    assert entry(kitchen)["stage"] == "intent"
    assert "thread" not in entry(kitchen)
    kitchen.t3.lose = None
    kitchen.poll(minutes(P + 10))
    assert entry(kitchen)["stage"] == "launched"
    assert entry(kitchen)["thread"] == launched(kitchen)["threadId"]


@pytest.mark.parametrize(
    ("texts", "cause"),
    [((NOT_LOGGED_IN,), "not signed in"), ((), "it ended with no home-id")],
)
def test_a_start_that_failed_is_launched_again_on_the_next_pass(started, texts, cause):
    """A launch whose run ended, failed or idle with no `home-id` written, is over: the next
    pass launches the home again, with no wait for `PATIENCE`, and the sidebar names why the
    last start failed instead of showing it as starting. `relaunches.json` keeps when the failed
    start was launched, though the relaunch writes over the entry's own launch time."""
    kitchen = started
    kitchen.poll(NOW)
    thread = failed_at_once(kitchen, minutes(0), texts)
    if not texts:
        thread["status"] = "completed"
    kitchen.poll(minutes(1))
    assert len(homes(kitchen)) == 2
    assert says(kitchen) == f"start failed: {cause}"
    last = entry(kitchen)
    assert last["stage"] == "launched"
    assert last["failed"]["thread"] == thread["threadId"]
    assert last["failed"]["launched"] == NOW.isoformat()
    assert last["at"] == minutes(1).isoformat()
    assert not (kitchen.home / "uncategorized" / "home-id").exists()


def test_a_start_still_running_is_not_launched_again_inside_its_patience(started):
    """A launch whose run is still starting or running, or that T3 Code does not list yet, may
    still write its `home-id`: it is not launched again until `PATIENCE` is up."""
    kitchen = started
    kitchen.poll(NOW)
    for n in (1, 10, P - 1):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 1
    assert entry(kitchen)["stage"] == "launched"
    kitchen.t3.threads.remove(launched(kitchen))
    kitchen.poll(minutes(P - 1))
    assert len(homes(kitchen)) == 1
    kitchen.poll(minutes(P + 1))
    assert len(homes(kitchen)) == 2
    assert says(kitchen) is None


def test_two_starts_that_failed_on_one_cause_wait_for_it_to_clear(started):
    """A second start that fails on the cause the first failed on is not launched again each
    pass: the home waits for that cause to clear, here for its instance to be signed in again,
    says so once in the digest, and the sidebar says what it waits for."""
    kitchen = started
    signed_in(NOW - timedelta(hours=1))
    kitchen.poll(NOW)
    failed_at_once(kitchen, minutes(0))
    kitchen.poll(minutes(1))
    failed_at_once(kitchen, minutes(1))
    for n in (2, 3, 10, 2 * P):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 2
    assert says(kitchen) == (
        "start failed: not signed in: waits for claudeAgent to be signed in again"
    )
    assert entry(kitchen)["stage"] == "failed"
    (line,) = [e["line"] for e in kitchen.events(children.START)]
    assert "failed twice in a row: not signed in" in line
    signed_in(minutes(2 * P + 1))
    kitchen.poll(minutes(2 * P + 2))
    assert len(homes(kitchen)) == 3
    assert says(kitchen) == "start failed: not signed in"
    assert entry(kitchen)["stage"] == "launched"


def test_a_start_that_failed_and_is_unread_is_launched_again_and_its_start_clears_the_failure(
    started,
):
    """A failed start whose run T3 Code cannot read is still over: the next pass says so and
    launches the home again. Once that launch writes the home's `home-id`, the sidebar no
    longer says a start failed."""
    kitchen = started
    kitchen.poll(NOW)
    failed_at_once(kitchen, minutes(0))
    kitchen.t3.lose_read = True
    said = kitchen.poll(minutes(1))
    kitchen.t3.lose_read = False
    assert any("could not be read" in one for one in said)
    assert len(homes(kitchen)) == 2
    assert says(kitchen) == "start failed: its run failed"
    (kitchen.home / "uncategorized" / "home-id").write_text(launched(kitchen)["threadId"] + "\n")
    kitchen.poll(minutes(2))
    assert says(kitchen) is None
    assert entry(kitchen)["stage"] == "started"
    assert "failed" not in entry(kitchen)
    assert len(homes(kitchen)) == 2


def test_two_starts_that_failed_on_a_usage_limit_wait_for_its_reset(started):
    """A second start in a row that fails on a usage limit makes the home wait for the limit's
    reset, not for `PATIENCE`, and the sidebar names the limit and its reset."""
    kitchen = started
    kitchen.poll(NOW)
    for n in (0, 1):
        failed_on(launched(kitchen), SESSION, run=f"run-{n + 1}", at=minutes(n))
        kitchen.t3.at_work.discard(launched(kitchen)["threadId"])
        kitchen.poll(minutes(n + 1))
    for n in (2, 2 * P, 11 * 60):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 2
    assert says(kitchen) == f"start failed: five_hour limit: waits for {SESSION_AT.isoformat()}"
    assert entry(kitchen)["stage"] == "failed"
    kitchen.poll(SESSION_AT + timedelta(minutes=1))
    assert len(homes(kitchen)) == 3


def test_two_starts_that_failed_signed_out_wait_out_patience_when_no_instance_is_known(started):
    """Where T3 Code's settings cannot be read, jbus cannot see the instance signed in again:
    a home whose second start failed signed out waits `PATIENCE` from that failure instead."""
    kitchen = started
    inventory.path().parent.mkdir(parents=True, exist_ok=True)
    inventory.path().write_text("not json")
    kitchen.poll(NOW)
    failed_at_once(kitchen, minutes(0))
    kitchen.poll(minutes(1))
    failed_at_once(kitchen, minutes(1))
    for n in (2, P):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 2
    assert entry(kitchen)["stage"] == "failed"
    kitchen.poll(minutes(P + 2))
    assert len(homes(kitchen)) == 3


def test_a_scoped_home_that_starts_after_a_failed_start_holds_no_failure(kitchen):
    """A stall launches the scoped home `sc` again, and that start fails. Its next stall launches
    it once more, past the failure, and that start writes its `home-id`: the entry is `started`
    and keeps neither the failure nor the words the sidebar showed of it. The fake T3 Code stamps
    a nudged thread with the wall clock, so the home thread's quiet is put back for the second
    spell."""
    home(kitchen)
    found = home(kitchen, "sc", idle=timedelta(hours=6))
    quiet = found["updatedAt"]
    add(kitchen, "sc-alpha", text=brief("sc-alpha").replace("Home: uncategorized", "Home: sc"))
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    for n in range(10, 3 * P + 1, 10):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 1
    failed_at_once(kitchen, minutes(3 * P))
    crew["updatedAt"] = minutes(3 * P + 5).isoformat().replace("+00:00", "Z")
    crew["items"] = 99
    found["updatedAt"] = quiet
    for n in range(3 * P + 10, 6 * P + 11, 10):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 2
    assert says(kitchen, "sc") == "start failed: not signed in"
    (kitchen.home / "sc" / "home-id").write_text(launched(kitchen)["threadId"] + "\n")
    kitchen.poll(minutes(6 * P + 20))
    held = entry(kitchen, "sc")
    assert "failed" not in held and "says" not in held
    assert held["stage"] == "started"
