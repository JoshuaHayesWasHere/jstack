"""jbus wakes a crew that ended its turn because every instance of the review pool is capped,
once the cap's end has passed. The crew stand-in runs the real `jroles review --thread`, which
finds the pool capped in the ledger and registers the wait. Like `test_jbus_slot_wake.py`, the
tests run the real pass against the fakes (Winnifred #202, #204 and #199, 2026-10-23: the
crews waited for a nudge after 04:20 UTC that never came)."""

from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jroles import ledger, waits
from jroles.cli import main as jroles
from test_jbus_kitchen import NOW, sends

INSTANCE = "claudeAgent_claude_prime"
UNTIL = NOW + timedelta(minutes=20)
SAID = f"{INSTANCE} is capped until {UNTIL.isoformat()}"


@pytest.fixture
def capped(kitchen, tmp_path, monkeypatch):
    """A role map whose review pool is one instance, capped in the ledger until UNTIL."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "config" / "jstack").mkdir(parents=True)
    line = f"review: claudeAgent claude-sonnet-5-5 {INSTANCE} effort=medium\n"
    (tmp_path / "config" / "jstack" / "roles").write_text(line)
    ledger.write(ledger.Record(INSTANCE, "five_hour", ledger.FULL, int(UNTIL.timestamp())))
    return kitchen


def crew(kitchen, capsys, status="completed", at=NOW):
    """Make a crew's thread that ran `jroles review --thread <its id>` at `at`, and ended its turn
    on what it printed. Return its id and what jroles said."""
    thread = kitchen.t3.thread("waiter", status, idle=timedelta(minutes=2))["threadId"]
    code = jroles(["review", "--thread", thread], now=at)
    out, err = capsys.readouterr()
    assert (code, out) == (75, "")
    return thread, err


def told(kitchen):
    return [given["threadId"] for given in sends(kitchen)]


def test_a_capped_pool_registers_the_crew_with_the_caps_end(capped, capsys):
    thread, err = crew(capped, capsys)
    assert err == (
        f"jroles: review waits: {SAID}\n"
        f"jroles: {thread} is registered as a waiter; jbus wakes it after {UNTIL.isoformat()}\n"
    )
    (wait,) = waits.read(waits.where())
    assert (wait.thread, wait.role, wait.until) == (thread, "review", UNTIL.isoformat())


def test_the_crew_is_woken_after_the_caps_end_and_not_before(capped, capsys):
    thread, _ = crew(capped, capsys)
    capped.poll()
    capped.poll(UNTIL - timedelta(minutes=1))
    assert sends(capped) == []
    said = capped.poll(UNTIL + timedelta(minutes=1))
    (given,) = sends(capped)
    assert given["threadId"] == thread and given["mode"] == "queue"
    assert given["clientRequestId"].startswith(f"pool-wake|{thread}|")
    assert f"jroles review --thread {thread}" in given["message"]
    assert given["message"].endswith(jbus.END_TURN)
    line = (
        f"pool-wake: woke {thread}, the review pool was capped until {UNTIL.isoformat()},"
        " after 21 min"
    )
    assert line in said and capped.lines("pool-wake") == [line]
    assert waits.read(waits.where()) == []


def test_a_crew_is_woken_once_for_each_wait(capped, capsys):
    thread, _ = crew(capped, capsys)
    for minutes in (21, 24, 27):
        capped.poll(NOW + timedelta(minutes=minutes))
    assert told(capped) == [thread]
    again = UNTIL + timedelta(minutes=40)
    ledger.write(ledger.Record(INSTANCE, "five_hour", ledger.FULL, int(again.timestamp())))
    crew_again = jroles(["review", "--thread", thread], now=NOW + timedelta(minutes=28))
    capsys.readouterr()
    assert crew_again == 75
    capped.poll(NOW + timedelta(minutes=30))
    assert told(capped) == [thread]
    capped.poll(again + timedelta(minutes=1))
    assert told(capped) == [thread, thread]
    assert len({given["clientRequestId"] for given in sends(capped)}) == 2


def test_registering_again_before_the_wake_keeps_one_wait(capped, capsys):
    thread, _ = crew(capped, capsys)
    assert jroles(["review", "--thread", thread], now=NOW + timedelta(minutes=5)) == 75
    capsys.readouterr()
    assert len(waits.read(waits.where())) == 1
    capped.poll(UNTIL + timedelta(minutes=1))
    assert told(capped) == [thread]


def test_a_crew_that_finds_headroom_leaves_the_waiters(capped, capsys):
    thread, _ = crew(capped, capsys)
    assert jroles(["review", "--thread", thread], now=UNTIL + timedelta(minutes=1)) == 0
    capsys.readouterr()
    assert waits.read(waits.where()) == []
    capped.poll(UNTIL + timedelta(minutes=2))
    assert sends(capped) == []


def test_without_a_thread_nothing_is_registered(capped, capsys):
    assert jroles(["review"], now=NOW) == 75
    assert capsys.readouterr().err == f"jroles: review waits: {SAID}\n"
    assert waits.read(waits.where()) == []


@pytest.mark.parametrize(
    "how", ["gone", "settled", "archived", "failed", "interrupted", "cancelled"]
)
def test_a_dead_crew_is_dropped_and_never_woken(capped, capsys, how):
    dead, _ = crew(capped, capsys)
    thread = next(t for t in capped.t3.threads if t["threadId"] == dead)
    if how == "gone":
        capped.t3.threads.remove(thread)
    elif how in ("settled", "archived"):
        thread[how] = True
    else:
        thread["status"] = how
    capped.poll()
    assert waits.read(waits.where()) == []
    capped.poll(UNTIL + timedelta(minutes=1))
    assert sends(capped) == []


def test_a_crew_whose_thread_could_not_be_checked_is_kept(capped, capsys):
    crew(capped, capsys)
    capped.t3.lose_read = True
    said = capped.poll()
    assert len(waits.read(waits.where())) == 1
    assert any("could not be checked" in line for line in said)


def test_a_lost_wake_is_tried_again_with_the_same_key(capped, capsys):
    thread, _ = crew(capped, capsys)
    capped.t3.lose_send = True
    said = capped.poll(UNTIL + timedelta(minutes=1))
    assert any("could not be told the review pool" in line for line in said)
    assert len(waits.read(waits.where())) == 1
    capped.t3.lose_send = False
    capped.poll(UNTIL + timedelta(minutes=3))
    assert told(capped) == [thread, thread]
    assert len({given["clientRequestId"] for given in sends(capped)}) == 1
    assert waits.read(waits.where()) == []


def test_no_waits_is_a_pass_that_sends_nothing(kitchen):
    kitchen.poll(datetime(2026, 10, 12, 16, 0, tzinfo=UTC))
    assert sends(kitchen) == [] and kitchen.lines("pool-wake") == []


def test_a_crew_that_waits_again_once_its_wait_is_due_has_a_new_wait_jbus_keeps(capped, capsys):
    """The crew's wake goes out, and the crew finds the pool capped again and registers before
    the pass is done with the wait it was woken for: the new wait is its own and stays."""
    thread, _ = crew(capped, capsys)
    (first,) = waits.read(waits.where())
    later = UNTIL + timedelta(minutes=40)
    again = waits.register(waits.where(), thread, "review", later, UNTIL + timedelta(minutes=1))
    assert again.id != first.id
    waits.forget(waits.where(), {first.id})
    assert [one.id for one in waits.read(waits.where())] == [again.id]


def about(said, thread):
    return [line for line in said if thread in line]


def test_a_crew_t3_code_no_longer_has_is_dropped_with_one_line(capped, capsys):
    """T3 Code says `thread_not_found`, "is no longer available", for a thread it no longer has
    (2026-10-23: jbus kept such a wait and logged it twice on every pass)."""
    thread, _ = crew(capped, capsys)
    capped.t3.threads.remove(next(t for t in capped.t3.threads if t["threadId"] == thread))
    said = capped.poll(UNTIL + timedelta(minutes=1))
    (line,) = about(said, thread)
    assert "is gone" in line and "no longer available" in line
    assert waits.read(waits.where()) == [] and sends(capped) == []
    assert about(capped.poll(UNTIL + timedelta(minutes=3)), thread) == []


def test_a_crew_t3_code_will_not_send_to_is_dropped_with_one_line(capped, capsys):
    thread, _ = crew(capped, capsys)
    capped.t3.lose_read = True
    capped.t3.forgot.add(thread)
    said = capped.poll(UNTIL + timedelta(minutes=1))
    (line,) = [line for line in about(said, thread) if "is gone" in line]
    assert "was not found" in line and not any("could not be told" in one for one in said)
    assert waits.read(waits.where()) == [] and told(capped) == [thread]
    assert about(capped.poll(UNTIL + timedelta(minutes=3)), thread) == []
    assert told(capped) == [thread]
