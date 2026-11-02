"""With a pool of two, a capped first instance leaves no work behind, in a pass with no one acting.
On 2026-11-02 the bus stopped for over an hour with claudeAgent free, and the home moved 13 threads
by hand with `t3_thread_configure`. The tests run the real pass against the kitchen's fakes, with
the cap in the ledger (`jroles.ledger`) as the usage hooks write it. A pool with every instance
capped holds the bus: its home is told once with the reset, and `jbus status` shows it."""

import json
import os
from datetime import timedelta

import pytest

import jbus
from jbus import digest, dispatch
from jroles import ledger
from jroles.cli import main as jroles
from test_jbus_capped_sends import ended, sent
from test_jbus_failover import PRIME, configures, failed_on
from test_jbus_github import failed, pull
from test_jbus_kitchen import NOW, SELECTION, approved, sends
from test_jbus_leftover import home
from test_jbus_resume import THREAD, crew

POOL = f"claudeAgent,{PRIME}"
RESETS = NOW + timedelta(minutes=40)
LATER = NOW + timedelta(minutes=90)
SESSION = "You've hit your session limit · resets 11pm (America/New_York)"
MOVE = {"threadId": THREAD, "modelSelection": {**SELECTION, "instanceId": PRIME}}


@pytest.fixture(autouse=True)
def pools(jstack_config, kitchen):
    """Every role that launches is on a pool of two. The kitchen's plan runs on the real clock and
    these tests on the replayed one, so they start with no plan."""
    kitchen.machine(plan=None)
    (jstack_config.parent / "roles").write_text(
        f"crew: claudeAgent claude-sonnet-5-5 {POOL}\n"
        f"home: claudeAgent claude-opus-5-5 {POOL}\n"
        f"review: claudeAgent claude-sonnet-5-5 {POOL} effort=high\n"
    )


def cap(*instances, resets=RESETS):
    """Write each instance's five-hour window full until `resets`."""
    for instance in instances:
        ledger.file_of(instance).write_text(f"five_hour 100 {int(resets.timestamp())}\n")


def test_a_running_thread_that_ends_on_the_cap_goes_on_on_the_second_instance(kitchen):
    thread = crew(kitchen)
    thread["status"] = "running"
    cap("claudeAgent")
    kitchen.poll(NOW)
    assert configures(kitchen) == []
    failed_on(thread, SESSION)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert configures(kitchen) == [MOVE]
    (carry,) = sends(kitchen)
    assert carry["clientRequestId"] == f"failover|{THREAD}|run-1"
    assert f"now on {PRIME}" in carry["message"]


def test_a_message_to_a_thread_on_the_capped_instance_moves_it_and_goes(kitchen):
    """The journal's `is capped until ..., so its ... message waits for the reset`: with room in
    the pool, nothing waits."""
    ended(kitchen)
    kitchen.set("open.json", [pull(kitchen, [failed()])])
    cap("claudeAgent")
    said = kitchen.poll(NOW)
    assert not [line for line in said if "waits for the reset" in line], said
    (moved,) = configures(kitchen)
    assert moved["modelSelection"]["instanceId"] == PRIME
    (key,) = sent(kitchen, "failed")
    assert key.startswith("failed|")
    (line,) = [one for one in said if one.startswith("rollover alpha: ")]
    assert line.endswith(
        f"claudeAgent to {PRIME}: claudeAgent is capped until {RESETS.isoformat()}"
    )


def test_a_thread_with_a_turn_running_is_not_moved_under_it(kitchen):
    """A configure mid-turn moves nothing that runs: the turn ends on the limit, and failover
    moves the thread then."""
    ended(kitchen)
    (thread,) = [one for one in kitchen.t3.threads if one["title"] == "crew: alpha"]
    thread["status"] = "running"
    kitchen.set("open.json", [pull(kitchen, [failed()])])
    cap("claudeAgent")
    kitchen.poll(NOW)
    assert configures(kitchen) == [] and sent(kitchen, "failed") == []


def test_a_message_with_the_whole_pool_capped_still_waits_and_moves_nothing(kitchen):
    ended(kitchen)
    kitchen.set("open.json", [pull(kitchen, [failed()])])
    cap("claudeAgent", PRIME)
    said = kitchen.poll(NOW)
    assert configures(kitchen) == [] and sent(kitchen, "failed") == []
    assert [line for line in said if "its failed message waits for the reset" in line]


def test_a_reviewer_launch_takes_the_second_instance(capsys):
    cap("claudeAgent")
    assert jroles(["review", "--thread", "crew-thread"], now=NOW) == 0
    out, err = capsys.readouterr()
    assert f'"instanceId": "{PRIME}"' in out
    assert f"jroles: review on {PRIME}: claudeAgent is capped until {RESETS.isoformat()}" in err


def test_a_new_row_launches_on_the_second_instance(kitchen):
    cap("claudeAgent")
    approved(kitchen, "alpha")
    kitchen.poll(NOW)
    (given,) = kitchen.t3.launches
    assert given["modelSelection"]["instanceId"] == PRIME


def test_a_launch_on_an_account_nobody_reads_counts_as_usable_and_says_so(
    kitchen, tmp_path, monkeypatch
):
    """The second instance's ledger is hours old, so nobody knows its use: the launch goes there
    all the same, since a blind account beats a stopped bus, and the events say so once a day."""
    settings = tmp_path / "t3" / "userdata" / "settings.json"
    settings.parent.mkdir(parents=True)
    instances = {
        "claudeAgent": {"driver": "claudeAgent"},
        PRIME: {"driver": "claudeAgent", "config": {"homePath": "~/.claude_prime"}},
    }
    settings.write_text(json.dumps({"providerInstances": instances}))
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
    monkeypatch.setattr(dispatch, "mirrored", lambda *_: True)
    cap("claudeAgent")
    second = ledger.file_of(PRIME)
    second.write_text("")
    hours_ago = NOW.timestamp() - 3 * 60 * 60
    os.utime(second, (hours_ago, hours_ago))
    approved(kitchen, "alpha")
    said = kitchen.poll(NOW)
    (given,) = kitchen.t3.launches
    assert given["modelSelection"]["instanceId"] == PRIME
    (line,) = [one for one in said if one.startswith(f"note demo: {PRIME}'s use is unread")]
    assert "180 min ago" in line and "counts as usable" in line
    assert line in kitchen.lines("note")


def test_with_every_instance_capped_the_home_is_told_once_with_the_reset(kitchen):
    """The home is on another provider, so it can be told while the pool is capped."""
    home(kitchen, selection={**SELECTION, "provider": "codex", "instanceId": "codex"})
    cap("claudeAgent", PRIME)
    for minutes in (0, 3, 6, 39):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (given,) = [one for one in sends(kitchen) if one["clientRequestId"].startswith("wakes|")]
    assert RESETS.isoformat() in given["message"]
    assert "capped" in given["message"]


def test_a_home_on_the_capped_pool_is_told_once_after_the_reset(kitchen):
    """A message into the cap starts a turn that ends at once, so the home hears at the reset."""
    home(kitchen)
    cap("claudeAgent", PRIME)
    kitchen.poll(NOW)
    assert not [one for one in sends(kitchen) if one["clientRequestId"].startswith("wakes|")]
    for minutes in (41, 44):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (given,) = [one for one in sends(kitchen) if one["clientRequestId"].startswith("wakes|")]
    assert RESETS.isoformat() in given["message"]


def test_a_second_hold_tells_the_home_again(kitchen):
    home(kitchen, selection={**SELECTION, "provider": "codex", "instanceId": "codex"})
    cap("claudeAgent", PRIME)
    kitchen.poll(NOW)
    after = RESETS + timedelta(hours=2)
    kitchen.poll(after)
    cap("claudeAgent", PRIME, resets=after + timedelta(minutes=30))
    kitchen.poll(after + timedelta(minutes=3))
    told = [one for one in sends(kitchen) if one["clientRequestId"].startswith("wakes|")]
    assert len(told) == 2


def test_status_shows_the_bus_held_on_the_pool_and_not_once_it_has_room(kitchen):
    kitchen.poll(NOW)
    cap("claudeAgent", PRIME)
    held = digest.status(jbus.load(), now=NOW)["held"]
    assert [one["until"] for one in held] == [RESETS.isoformat()]
    assert set(held[0]["instances"]) == {"claudeAgent", PRIME}
    assert set(held[0]["roles"]) == {"crew", "home", "review"}
    assert RESETS.isoformat() in held[0]["why"]
    cap(PRIME, resets=NOW - timedelta(hours=1))
    assert digest.status(jbus.load(), now=NOW)["held"] == []
