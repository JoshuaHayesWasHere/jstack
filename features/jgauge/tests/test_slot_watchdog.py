"""The watchdog of `jgauge.children` ends a test slot's command once its holder lets go of the
pipe with no word that the command ended, and leaves it be after that word."""

import contextlib
import io
import os
import signal
import subprocess
import sys
import time

import pytest

import test_slot
from jgauge import children, slot
from test_slot import gone, live

slots = test_slot.slots

LEAVES_A_CHILD = "sleep 60 & echo $!; wait"


def started(command, **more):
    """A process running `command`, and the pid of the child it printed."""
    ran = subprocess.Popen(["sh", "-c", command], stdout=subprocess.PIPE, text=True, **more)
    return ran, int(ran.stdout.readline())


@pytest.mark.parametrize("group", [False, True])
def test_a_holder_that_lets_go_with_no_done_takes_the_command_and_its_children(group):
    watch = children.Watch(group)
    ran = subprocess.Popen(
        ["sh", "-c", LEAVES_A_CHILD],
        stdout=subprocess.PIPE,
        text=True,
        preexec_fn=watch.announce,
        process_group=0 if group else None,
    )
    child = int(ran.stdout.readline())
    os.close(watch.fd)
    watch.reap()
    assert ran.wait(timeout=5) == -signal.SIGKILL
    assert gone(child)


def test_a_holder_that_says_done_leaves_what_runs_be():
    watch = children.Watch(False)
    ran = subprocess.Popen(["sleep", "60"], preexec_fn=watch.announce)
    watch.done()
    watch.reap()
    assert ran.poll() is None
    ran.kill()
    ran.wait()


def test_a_group_member_that_left_the_tree_ends_with_the_group():
    """In the short lane the command leads a group, and a process it started and left, whose
    parent is no longer in the tree, still ends with it."""
    ran, left = started("(sleep 60 & echo $!) ; sleep 60", process_group=0)
    children.end(ran.pid, group=True)
    assert ran.wait(timeout=5) == -signal.SIGKILL
    assert gone(left)


def test_with_no_proc_the_parents_come_from_ps(monkeypatch, tmp_path):
    ran, child = started(LEAVES_A_CHILD)
    from_proc = children._parents()
    monkeypatch.setattr(children, "PROC", tmp_path / "no-proc")
    from_ps = children._parents()
    assert from_proc[child] == from_ps[child] == ran.pid
    ran.kill()
    ran.wait()
    os.kill(child, signal.SIGKILL)


@pytest.mark.parametrize(
    ("said", "ends"), [("{pid}\n", True), ("{pid}\ndone\n", False), ("", False)]
)
def test_the_watchdog_ends_the_pid_it_was_told_unless_told_done(monkeypatch, said, ends):
    ran = subprocess.Popen(["sleep", "60"])
    stdin = io.TextIOWrapper(io.BytesIO(said.format(pid=ran.pid).encode()))
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "argv", ["children", "0"])
    kept = {told: signal.getsignal(told) for told in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        children.main()
    finally:
        for told, handler in kept.items():
            signal.signal(told, handler)
    if ends:
        assert ran.wait(timeout=5) == -signal.SIGKILL
    else:
        assert ran.poll() is None
        ran.kill()
        ran.wait()


def test_a_command_announces_its_own_pid_to_the_watchdog():
    """`announce` runs in the command's process before it execs, so the pid the watchdog reads is
    the command's, even where the holder dies before Popen returns."""
    watch = children.Watch(False)
    os.close(watch.fd)
    watch.reap()
    read, watch.fd = os.pipe()
    watch.announce()
    os.close(watch.fd)
    assert os.read(read, 64) == f"{os.getpid()}\n".encode()
    os.close(read)


SLEEPS_IN_A_SESSION = """\
import os, time
os.setsid()
state = os.environ["D"]
with open(os.path.join(state, "pid.new"), "w") as out:
    out.write(str(os.getpid()))
os.rename(os.path.join(state, "pid.new"), os.path.join(state, "pid"))
time.sleep(60)
"""
"""A child in a session of its own, from Python since macOS has no `setsid` command."""

SLEEPS_IN_THE_BACKGROUND = 'sleep 60 & echo $! > "$D/pid.new"; mv "$D/pid.new" "$D/pid"; wait'


def told_sigterm(slots, lane, command, **more):
    """Run `command` under a holder of `lane`, send the holder SIGTERM once the command's child
    wrote its pid, and give back the holder's exit code and that pid."""
    holder = slots(*lane, command=["sh", "-c", command], **more)
    pid = slots.state / "pid"
    assert slots.waits(pid.exists)
    holder.send_signal(signal.SIGTERM)
    return holder.wait(timeout=10), int(pid.read_text())


def test_a_short_holder_told_sigterm_ends_a_child_in_a_session_of_its_own_with_it(slots):
    """A crew's thread that ends, or a launcher's cancel, stops a short holder with SIGTERM. A
    child in a session of its own, as Playwright starts its web server, is in no group the
    command leads, so it is gone only if the holder reaches it under the command."""
    code, left = told_sigterm(
        slots,
        ["--short"],
        '"$PY" -c "$SESSION" & wait',
        PY=sys.executable,
        SESSION=SLEEPS_IN_A_SESSION,
    )
    try:
        assert code == 128 + signal.SIGTERM
        deadline = time.monotonic() + slot.STOP_GRACE_SECONDS
        while live(left) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not live(left), f"process {left}, in a session of its own, outlived the SIGTERM"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(left, signal.SIGKILL)


def test_a_default_lane_holder_passes_a_signal_to_its_command_only(slots):
    """In the default lane the command decides what its children do on a signal, as a shell's
    command would, so the holder tells the command alone and a child of it lives on."""
    code, left = told_sigterm(slots, ["--slots", "1"], SLEEPS_IN_THE_BACKGROUND)
    try:
        assert code == 128 + signal.SIGTERM
        assert live(left), f"process {left}, the command's child, was signalled too"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(left, signal.SIGKILL)
