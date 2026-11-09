"""A thread that finds every full slot taken registers as a waiter in the slot queue's file,
and says so in one line, instead of waiting in the call. A short call waits in the call, in the
order the calls came, and registers nothing. The tests run as `test_slot.py` does: the real
`jgauge test-slot`, against lock files in a temporary home that each test makes."""

import fcntl
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from jgauge import slot, waiters
from test_machine_sizes import fake_proc
from test_room import BIN

THREAD = "mcp:thread-9"
NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A temporary home for one test, with lock files that the test can hold. The machine has
    24 processors and 62 GiB, so it has 3 short slots. The home has no limits file."""
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    home = tmp_path / "home"
    return SimpleNamespace(home=home, locks=home / ".local" / "state" / "locks")


def hold_full(machine):
    held = []
    machine.locks.mkdir(parents=True, exist_ok=True)
    for n in (1, 2):
        fd = os.open(machine.locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    return held


def _split(args):
    at = args.index("--") if "--" in args else len(args)
    return args[:at], args[at : at + 1], args[at + 1 :]


def started(machine, *args, thread=THREAD, wait="0"):
    """`jgauge test-slot` with these arguments started, with the thread's option placed before
    the `--`. A short call waits `wait` seconds in the call, none unless a test says."""
    head, dashes, command = (list(part) for part in _split(args))
    return subprocess.Popen(
        [
            str(BIN / "jgauge"),
            "test-slot",
            *head,
            *(["--thread", thread] if thread else []),
            *dashes,
            *command,
        ],
        env={**os.environ, "HOME": str(machine.home), slot.WAIT_FOR: wait},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def ended(run, timeout=20):
    out, err = run.communicate(timeout=timeout)
    return SimpleNamespace(returncode=run.returncode, stdout=out, stderr=err)


def jgauge(machine, *args, thread=THREAD, wait="0"):
    return ended(started(machine, *args, thread=thread, wait=wait))


def hold_short(machine):
    held = []
    machine.locks.mkdir(parents=True, exist_ok=True)
    for n in range(1, slot.short().slots + 1):
        fd = os.open(machine.locks / f"test-slot-short.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    return held


def _in_line(machine, count):
    """Wait until `count` callers wait in the short lane's line."""
    line = machine.locks / slot.LINE
    for _ in range(100):
        if line.is_dir() and len([one for one in line.iterdir() if one.name[0] != "."]) == count:
            return
        time.sleep(0.05)
    raise AssertionError(f"{count} callers never waited in the line")


def _gone(path):
    for _ in range(100):
        if not path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{path.name} never went")


def test_with_every_short_slot_taken_a_thread_waits_in_the_call_and_takes_the_first_freed(
    machine,
):
    held = hold_short(machine)
    line = machine.locks / slot.LINE
    line.mkdir()
    later = os.open(line / ("9" * 20 + ".1"), os.O_RDWR | os.O_CREAT)
    fcntl.flock(later, fcntl.LOCK_EX)
    try:
        run = started(machine, "--short", "--", "echo", "ran", wait="15")
        _in_line(machine, 2)
        time.sleep(0.5)
        assert run.poll() is None
        os.close(held.pop())
        ran = ended(run)
    finally:
        os.close(later)
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout) == (0, "ran\n")
    assert waiters.read(machine.locks) == []


def test_a_freed_short_slot_goes_to_the_caller_that_came_first(machine):
    """A caller that came before holds its place in the line, and a later one leaves a freed
    slot to it until it goes. A place no caller holds any more is passed over."""
    held = hold_short(machine)
    line = machine.locks / slot.LINE
    line.mkdir()
    (line / f"{0:020d}.1").touch()
    older = os.open(line / f"{1:020d}.2", os.O_RDWR | os.O_CREAT)
    fcntl.flock(older, fcntl.LOCK_EX)
    try:
        run = started(machine, "--short", "--", "echo", "ran", wait="15")
        _gone(line / f"{0:020d}.1")
        assert len(list(line.iterdir())) == 2
        os.close(held.pop())
        time.sleep(1)
        assert run.poll() is None
        (line / f"{1:020d}.2").unlink()
        os.close(older)
        ran = ended(run)
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout) == (0, "ran\n")
    assert sorted(line.iterdir()) == []


def test_a_short_call_waits_past_the_old_wait_and_takes_a_freed_slot_with_no_waiter_on_file(
    machine,
):
    """A short-lane waiter an older jgauge left on file holds nothing: the call waits in the
    line past the 1 s the old tests waited, takes the first slot freed, and its thread is never
    registered, so jbus starts no turn to hand it one."""
    waiters.register(machine.locks, "mcp:old", "short", slot.short().slots, ["echo", "a"], NOW)
    held = hold_short(machine)
    try:
        run = started(machine, "--short", "--", "echo", "ran", wait="15")
        _in_line(machine, 1)
        time.sleep(1.5)
        assert run.poll() is None
        os.close(held.pop())
        ran = ended(run)
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout) == (0, "ran\n")
    assert THREAD not in [one.thread for one in waiters.read(machine.locks)]


def test_a_short_call_at_its_ceiling_ends_76_and_says_to_run_again_now(machine):
    held = hold_short(machine)
    try:
        ran = jgauge(machine, "--short", "--", "echo", "ran", wait="1")
    finally:
        for fd in held:
            os.close(fd)
    assert ran.returncode == slot.WAITING == 76
    (line,) = ran.stdout.splitlines()
    assert "run the same command again now, in this turn" in line
    assert "end your turn" not in ran.stdout.lower() + ran.stderr.lower()
    assert waiters.read(machine.locks) == []
    assert [one.name for one in (machine.locks / slot.LINE).iterdir()] == []


def test_a_thread_asked_twice_is_one_waiter_with_one_place(machine):
    held = hold_full(machine)
    try:
        jgauge(machine, "--slots", "2", "--", "echo", "one")
        (first,) = waiters.read(machine.locks)
        jgauge(machine, "--slots", "2", "--", "echo", "two")
    finally:
        for fd in held:
            os.close(fd)
    (again,) = waiters.read(machine.locks)
    assert (again.id, again.since, again.command) == (first.id, first.since, ("echo", "two"))


def test_a_thread_that_takes_a_slot_runs_and_leaves_the_waiters(machine):
    waiters.register(machine.locks, THREAD, "full", 2, ["echo", "ran"], NOW)
    waiters.register(machine.locks, "mcp:other", "full", 2, ["true"], NOW)
    ran = jgauge(machine, "--slots", "2", "--", "echo", "ran")
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "ran\n", "")
    assert [one.thread for one in waiters.read(machine.locks)] == ["mcp:other"]


def test_the_full_lane_registers_with_its_slot_count(machine):
    held = hold_full(machine)
    try:
        ran = jgauge(machine, "--slots", "2", "--", "make", "check")
    finally:
        for fd in held:
            os.close(fd)
    assert ran.returncode == 76 and "every one of 2 slots is taken" in ran.stdout
    (one,) = waiters.read(machine.locks)
    assert (one.lane, one.slots, one.command) == ("full", 2, ("make", "check"))


def test_without_a_thread_it_waits_in_the_call_as_it_did(machine):
    ran = jgauge(machine, "--short", "--", "echo", "ran", thread="")
    assert (ran.returncode, ran.stdout) == (0, "ran\n")
    assert waiters.read(machine.locks) == []


def test_the_waiters_are_printed(machine):
    waiters.register(machine.locks, THREAD, "short", 3, ["uv", "run", "pytest", "a b"], NOW)
    ran = jgauge(machine, "--waiters", thread="")
    assert ran.stdout == f"{THREAD} short since 2026-10-12T15:00:00Z: uv run pytest 'a b'\n"


def test_free_counts_the_slots_no_one_holds_and_creates_no_lock_file(machine, monkeypatch):
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(machine.locks))
    assert slot.free(slot.short()) == slot.short().slots
    assert not machine.locks.exists() or not list(machine.locks.glob("test-slot-short.*"))
    held = hold_short(machine)
    try:
        assert slot.free(slot.short()) == 0
        os.close(held.pop())
        assert slot.free(slot.short()) == 1
    finally:
        for fd in held:
            os.close(fd)


def test_registering_after_a_wake_keeps_the_place_and_makes_a_new_wait(tmp_path):
    first = waiters.register(tmp_path, THREAD, "short", 3, ["a"], NOW)
    other = waiters.register(tmp_path, "mcp:other", "short", 3, ["b"], NOW + timedelta(minutes=1))
    waiters.woken(tmp_path, first.id, NOW + timedelta(minutes=2))
    waiters.woken(tmp_path, first.id, NOW + timedelta(minutes=3))
    (woken,) = [one for one in waiters.read(tmp_path) if one.thread == THREAD]
    assert woken.woken == "2026-10-12T15:02:00Z"
    again = waiters.register(tmp_path, THREAD, "short", 3, ["a"], NOW + timedelta(minutes=4))
    assert (again.since, again.woken) == (first.since, "") and again.id != first.id
    assert [one.thread for one in waiters.read(tmp_path)] == [THREAD, "mcp:other"]
    waiters.forget(tmp_path, {first.id})
    assert {one.id for one in waiters.read(tmp_path)} == {again.id, other.id}


def test_registering_on_another_lane_starts_a_new_place(tmp_path):
    first = waiters.register(tmp_path, THREAD, "short", 3, ["a"], NOW)
    later = NOW + timedelta(minutes=5)
    moved = waiters.register(tmp_path, THREAD, "full", 2, ["a"], later)
    assert moved.since == waiters.stamp(later) != first.since
    assert [one.lane for one in waiters.read(tmp_path)] == ["full"]


@pytest.mark.parametrize("text", ["", "not json", "{}", '[{"thread": "x"}]'])
def test_a_file_that_does_not_parse_is_an_empty_list_and_is_written_over(tmp_path, text):
    (tmp_path / waiters.NAME).write_text(text)
    assert waiters.read(tmp_path) == []
    waiters.register(tmp_path, THREAD, "short", 3, ["a"], NOW)
    assert [one.thread for one in waiters.read(tmp_path)] == [THREAD]


def test_a_thread_given_with_and_without_its_prefix_is_one_waiter_with_one_place(machine):
    held = hold_full(machine)
    try:
        jgauge(machine, "--slots", "2", "--", "make", "check", thread="thread-9")
        (first,) = waiters.read(machine.locks)
        jgauge(machine, "--slots", "2", "--", "make", "check", thread=THREAD)
    finally:
        for fd in held:
            os.close(fd)
    (one,) = waiters.read(machine.locks)
    assert (one.thread, one.id, one.since) == (THREAD, first.id, first.since)
    waiters.drop(machine.locks, "thread-9")
    assert waiters.read(machine.locks) == []


def test_records_on_disk_under_both_forms_collapse_to_the_older_on_the_next_change(tmp_path):
    def record(thread, since, id):
        made = waiters.Waiter(thread, "full", 2, ("make", "check"), since, id)
        return {**vars(made), "command": list(made.command)}

    written = [
        record("thread-9", "2026-10-12T15:00:40Z", "older"),
        record(THREAD, "2026-10-12T15:00:57Z", "newer"),
    ]
    path = tmp_path / waiters.NAME
    path.write_text(json.dumps(written))
    (one,) = waiters.read(tmp_path)
    assert (one.thread, one.id, one.since) == (THREAD, "older", "2026-10-12T15:00:40Z")
    assert json.loads(path.read_text()) == written
    waiters.register(tmp_path, "other", "full", 2, ["true"], NOW)
    on_disk = [(one["thread"], one["id"]) for one in json.loads(path.read_text())]
    assert on_disk[0] == (THREAD, "older") and len(on_disk) == 2
    assert on_disk[1][0] == "mcp:other"


def test_an_older_woken_record_and_a_later_unwoken_one_keep_the_live_wait_in_its_place(tmp_path):
    def record(thread, since, id, woken=""):
        made = waiters.Waiter(thread, "full", 2, ("make", "check"), since, id, woken)
        return {**vars(made), "command": list(made.command)}

    (tmp_path / waiters.NAME).write_text(
        json.dumps(
            [
                record("thread-9", "2026-10-12T15:00:40Z", "older", "2026-10-12T15:05:00Z"),
                record(THREAD, "2026-10-12T15:06:00Z", "later"),
            ]
        )
    )
    (one,) = waiters.read(tmp_path)
    assert (one.thread, one.id, one.since, one.woken) == (
        THREAD,
        "later",
        "2026-10-12T15:00:40Z",
        "",
    )
    waiters.woken(tmp_path, "later", NOW)
    (woken,) = waiters.read(tmp_path)
    assert (woken.id, woken.woken) == ("later", waiters.stamp(NOW))


def wake(machine, thread, ago=timedelta(0)):
    """What jbus does when it wakes a waiter: it records the wake, which claims a slot for the
    thread for `waiters.HOLDS`."""
    (wait,) = [one for one in waiters.read(machine.locks) if one.thread == thread]
    waiters.woken(machine.locks, wait.id, datetime.now(UTC) - ago)


def test_a_slot_jbus_woke_a_waiter_for_is_held_for_that_waiter(machine):
    held = hold_full(machine)
    try:
        jgauge(machine, "--slots", "1", "--", "echo", "a", thread="mcp:a")
    finally:
        for fd in held:
            os.close(fd)
    wake(machine, "mcp:a")
    second = jgauge(machine, "--slots", "1", "--", "echo", "b", thread="mcp:b")
    assert (second.returncode, second.stderr) == (slot.WAITING, "")
    assert (
        len(second.stdout.splitlines()) == 1 and "mcp:b is registered as a waiter" in second.stdout
    )
    first = jgauge(machine, "--slots", "1", "--", "echo", "a", thread="mcp:a")
    assert (first.returncode, first.stdout) == (0, "a\n")
    assert [one.thread for one in waiters.read(machine.locks)] == ["mcp:b"]


def test_a_claim_holds_only_as_many_slots_as_it_claims(machine):
    waiters.register(machine.locks, "mcp:a", "full", 2, ["echo", "a"], NOW)
    wake(machine, "mcp:a")
    second = jgauge(machine, "--slots", "2", "--", "echo", "b", thread="mcp:b")
    assert (second.returncode, second.stdout) == (0, "b\n")
    assert [one.thread for one in waiters.read(machine.locks)] == ["mcp:a"]


def test_a_claim_past_its_hold_holds_nothing(machine):
    waiters.register(machine.locks, "mcp:a", "full", 1, ["echo", "a"], NOW)
    wake(machine, "mcp:a", ago=waiters.HOLDS + timedelta(minutes=1))
    second = jgauge(machine, "--slots", "1", "--", "echo", "b", thread="mcp:b")
    assert (second.returncode, second.stdout) == (0, "b\n")


def test_a_claim_on_the_other_lane_holds_nothing_here(machine):
    waiters.register(machine.locks, "mcp:a", "short", slot.short().slots, ["echo", "a"], NOW)
    wake(machine, "mcp:a")
    second = jgauge(machine, "--slots", "1", "--", "echo", "b", thread="mcp:b")
    assert (second.returncode, second.stdout) == (0, "b\n")
