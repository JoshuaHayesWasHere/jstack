"""A full test slot that jbus woke a waiter for stays that waiter's, whoever else asks for it: a
caller with a thread registers as a waiter, and one with no thread, such as a desk's `make check`
or `jmerge`'s guards, waits in its call. The room jbus wakes waiters for and the room a take
finds are one count (`jgauge.slot.spare`)."""

import os
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jbus import slotwait
from jgauge import slot, waiters
from test_machine_sizes import fake_proc
from test_slot_waiters import ended, hold_full, jgauge, started, wake


@pytest.fixture
def machine(tmp_path, monkeypatch):
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    home = tmp_path / "home"
    locks = home / ".local" / "state" / "locks"
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(locks))
    return SimpleNamespace(home=home, locks=locks)


def woken_waiter(machine, thread, slots):
    waiters.register(machine.locks, thread, "full", slots, ["echo", thread], datetime.now(UTC))
    wake(machine, thread)


def test_a_caller_with_no_thread_waits_while_a_woken_waiter_holds_the_free_slot(machine):
    woken_waiter(machine, "mcp:a", 1)
    other = started(machine, "--slots", "1", "--", "echo", "b", thread="")
    time.sleep(1.5)
    assert other.poll() is None, ended(other)
    first = jgauge(machine, "--slots", "1", "--", "echo", "a", thread="mcp:a")
    assert (first.returncode, first.stdout) == (0, "a\n")
    second = ended(other)
    assert (second.returncode, second.stdout) == (0, "b\n")
    assert "waiting for one of 1 slots" in second.stderr
    assert waiters.read(machine.locks) == []


@pytest.mark.parametrize(
    ("held", "claimed"),
    [(0, 0), (0, 1), (1, 0), (1, 1), (0, 2), (2, 0), (1, 2)],
)
def test_jbus_wakes_a_waiter_for_each_slot_a_take_finds_spare(machine, monkeypatch, held, claimed):
    """With `held` of two full slots taken and `claimed` woken waiters, jbus wakes as many of
    three waiters as `spare` counts, and its wakes claim every spare slot, so a take after them
    finds none."""
    lane = slot.full(2)
    fds = hold_full(machine)
    for fd in fds[held:]:
        os.close(fd)
    try:
        for n in range(claimed):
            woken_waiter(machine, f"mcp:woken-{n}", 2)
        for n in range(3):
            waiters.register(machine.locks, f"mcp:wait-{n}", "full", 2, ["echo"], datetime.now(UTC))
        now = datetime.now(UTC)
        spare = slot.spare(lane, waiters.read(machine.locks), now)
        assert spare == 2 - held - claimed
        told, resent = [], []

        def tell(run, client, one, again=False):
            (resent if again else told).append(one.thread)

        monkeypatch.setattr(slotwait, "dead", lambda run, client, one: False)
        monkeypatch.setattr(slotwait, "tell", tell)
        slotwait.wake(SimpleNamespace(now=now, say=lambda line: None), None)
        assert len(told) == max(spare, 0)
        assert sorted(resent) == [f"mcp:woken-{n}" for n in range(claimed)]
        took = slot.take(lane, "mcp:taker", ["echo"])
        assert took is None
        if took is not None:
            os.close(took[0])
    finally:
        for fd in fds[:held]:
            os.close(fd)
