import fcntl
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import daemons
from jgauge import slot
from test_machine_sizes import fake_proc
from test_room import BIN

RUNS_UNTIL_RELEASED = (
    'touch "$D/started.$1"; n=0; '
    'until [ -e "$D/release.$1" ] || [ ! -d "$D" ] || [ "$n" -gt 3000 ]; '
    "do sleep 0.02; n=$((n + 1)); done"
)


@pytest.fixture
def slots(tmp_path):
    """Run `jgauge test-slot` on a machine of its own, whose lock files a test can hold: 24
    processors and 62 GiB, so 4 full slots and 3 short ones, and no limits file."""
    home, state = tmp_path / "home", tmp_path / "state"
    locks = home / ".local" / "state" / "locks"
    state.mkdir()
    proc = fake_proc(tmp_path / "proc", 24, 62)
    env = {**os.environ, "HOME": str(home), "D": str(state), "PROC": str(proc)}
    for name in ("TEST_SLOTS", "XDG_CONFIG_HOME", "JGAUGE_TEST_SLOT"):
        env.pop(name, None)
    going, taken = [], []

    def start(*args, command=None, name=None, **more):
        command = command or ["sh", "-c", RUNS_UNTIL_RELEASED, "sh", name]
        ran = daemons.start(
            [str(BIN / "jgauge"), "test-slot", *args, "--", *command],
            env={**env, **more},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        going.append(ran)
        return ran

    def waits(until):
        deadline = time.monotonic() + 5
        while not until() and time.monotonic() < deadline:
            time.sleep(0.02)
        return until()

    def started():
        return sorted(path.suffix[1:] for path in state.glob("started.*"))

    def release(name):
        (state / f"release.{name}").touch()

    def hold(*numbers):
        """Take those slots as another holder would. The slots stay taken until the test
        calls `free`."""
        locks.mkdir(parents=True, exist_ok=True)
        for n in numbers:
            fd = os.open(locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            taken.append(fd)

    def free():
        while taken:
            os.close(taken.pop())

    start.waits, start.started, start.release = waits, started, release
    start.hold, start.free, start.locks, start.state = hold, free, locks, state
    yield start
    free()
    for name in "abc":
        release(name)
    for ran in going:
        if ran.poll() is None:
            ran.kill()
        ran.communicate()


def test_with_two_slots_the_third_command_starts_only_after_one_ends(slots):
    ran = {name: slots("--slots", "2", name=name) for name in "abc"}
    assert slots.waits(lambda: len(slots.started()) == 2)
    time.sleep(2.5 * slot.LOOK_EVERY_SECONDS)
    first, second = slots.started()
    (third,) = set("abc") - {first, second}
    assert ran[third].poll() is None

    slots.release(first)
    assert ran[first].wait(timeout=5) == 0
    assert slots.waits(lambda: slots.started() == ["a", "b", "c"])
    slots.release(second)
    slots.release(third)
    assert ran[third].communicate(timeout=5) == ("", "test-slot: waiting for one of 2 slots\n")
    assert ran[second].communicate(timeout=5) == ("", "")
    assert ran[third].returncode == 0


def test_the_exit_code_and_the_output_are_the_commands_own(slots):
    ran = slots(command=["sh", "-c", "echo out; echo err >&2; exit 7"])
    assert ran.communicate(timeout=5) == ("out\n", "err\n")
    assert ran.returncode == 7


def test_the_command_is_told_the_lane_of_the_slot_it_holds(slots):
    """A command learns from JGAUGE_TEST_SLOT that it holds a slot, so a run it starts, a TLC
    model check in a suite, takes no second one and cannot wait on its own."""
    says = ["sh", "-c", 'echo "$JGAUGE_TEST_SLOT"']
    assert slots("--slots", "1", command=says).communicate(timeout=5) == ("full\n", "")
    assert slots("--short", command=says).communicate(timeout=5) == ("short\n", "")


def test_a_command_ended_by_a_signal_ends_as_a_shell_would_say(slots):
    ran = slots(command=["sh", "-c", "kill -TERM $$"])
    assert ran.wait(timeout=5) == 128 + signal.SIGTERM


def test_a_command_that_is_not_there_says_so_and_holds_no_slot(slots):
    ran = slots("--slots", "1", command=["no-such-command-here"])
    out, err = ran.communicate(timeout=5)
    assert (ran.returncode, out) == (127, "")
    assert err.startswith("test-slot: no-such-command-here: ")
    assert slots("--slots", "1", command=["true"]).wait(timeout=5) == 0


def test_a_holder_killed_with_sigkill_frees_its_slot(slots):
    holder = slots("--slots", "1", name="a")
    assert slots.waits(lambda: slots.started() == ["a"])
    holder.send_signal(signal.SIGKILL)
    assert holder.wait(timeout=5) == -signal.SIGKILL
    after = slots("--slots", "1", command=["echo", "ran"])
    assert after.communicate(timeout=5) == ("ran\n", "")


def test_what_a_command_leaves_running_holds_no_slot(slots):
    left = f"({RUNS_UNTIL_RELEASED}) > /dev/null 2>&1 &"
    assert slots("--slots", "1", command=["sh", "-c", left, "sh", "a"]).wait(timeout=5) == 0
    assert slots.waits(lambda: slots.started() == ["a"])
    after = slots("--slots", "1", command=["echo", "ran"])
    assert after.communicate(timeout=5) == ("ran\n", "")


def test_a_command_left_running_ends_when_its_directory_goes(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    left = daemons.start(
        ["sh", "-c", RUNS_UNTIL_RELEASED, "sh", "a"], env={**os.environ, "D": str(state)}
    )
    try:
        deadline = time.monotonic() + 5
        while not (state / "started.a").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        shutil.rmtree(state)
        assert left.wait(timeout=5) == 0
    finally:
        left.kill()


def test_an_interrupt_is_the_commands_to_take_and_the_holder_waits_for_it_to_end(slots):
    holder = slots("--slots", "1", name="a")
    assert slots.waits(lambda: slots.started() == ["a"])
    holder.send_signal(signal.SIGINT)
    time.sleep(0.3)
    assert holder.poll() is None
    slots.release("a")
    assert holder.wait(timeout=5) == 0


def test_a_holder_told_to_stop_stops_its_command_too(slots):
    holder = slots(
        "--slots",
        "1",
        command=["sh", "-c", f'trap "exit 9" TERM; {RUNS_UNTIL_RELEASED}', "sh", "a"],
    )
    assert slots.waits(lambda: slots.started() == ["a"])
    holder.terminate()
    assert holder.wait(timeout=5) == 9


@pytest.mark.parametrize(
    ("args", "env", "held", "count"),
    [
        ([], {}, (1, 2, 3, 4), 4),
        ([], {"TEST_SLOTS": "3"}, (1, 2, 3), 3),
        (["--slots", "1"], {"TEST_SLOTS": "3"}, (1,), 1),
    ],
)
def test_the_number_of_slots_is_the_flag_then_the_variable_then_the_machine(
    slots, args, env, held, count
):
    slots.hold(*held)
    ran = slots(*args, command=["echo", "ran"], **env)
    assert ran.stderr.readline() == f"test-slot: waiting for one of {count} slots\n"
    assert ran.poll() is None
    slots.free()
    assert ran.communicate(timeout=5) == ("ran\n", "")
    assert ran.returncode == 0


@pytest.mark.parametrize(
    ("args", "env", "held", "takes"),
    [
        ([], {}, (1,), 2),
        ([], {"TEST_SLOTS": "4"}, (1, 2, 3), 4),
        (["--slots", "2"], {"TEST_SLOTS": "1"}, (1,), 2),
        ([], {}, (), 1),
    ],
)
def test_a_command_takes_the_first_slot_that_is_free(slots, args, env, held, takes):
    slots.hold(*held)
    ran = slots(*args, command=["echo", "ran"], **env)
    assert ran.communicate(timeout=5) == ("ran\n", "")
    assert sorted(path.name for path in slots.locks.iterdir()) == [
        f"test-slot.{n}.lock" for n in range(1, takes + 1)
    ]


@pytest.mark.parametrize(
    ("args", "env"),
    [(["--slots", "0"], {}), ([], {"TEST_SLOTS": "many"}), ([], {"TEST_SLOTS": "0"})],
)
def test_a_number_of_slots_that_is_no_number_runs_nothing(slots, args, env):
    ran = slots(*args, command=["echo", "ran"], **env)
    out, err = ran.communicate(timeout=5)
    assert (ran.returncode, out) == (2, "")
    assert "slots" in err.lower()


def test_with_every_full_slot_held_a_short_job_runs_at_once(slots):
    slots.hold(1, 2, 3)
    ran = slots("--short", command=["echo", "ran"])
    assert ran.communicate(timeout=5) == ("ran\n", "")
    assert ran.returncode == 0
    assert sorted(path.name for path in slots.locks.iterdir()) == [
        "test-slot-short.1.lock",
        "test-slot.1.lock",
        "test-slot.2.lock",
        "test-slot.3.lock",
    ]


def test_the_short_lane_waits_only_on_its_own_slots(slots):
    holders = [slots("--short", name=name) for name in "abc"]
    assert slots.waits(lambda: slots.started() == ["a", "b", "c"])
    ran = slots("--short", command=["echo", "ran"])
    assert ran.stderr.readline() == "test-slot: waiting for one of 3 short slots\n"
    assert slots("--slots", "1", command=["echo", "full"]).communicate(timeout=5) == ("full\n", "")
    slots.release("a")
    assert holders[0].wait(timeout=5) == 0
    assert ran.communicate(timeout=5) == ("ran\n", "")


def test_a_short_job_past_its_limit_is_stopped_and_says_so(slots, tmp_path):
    limited = (
        "import sys; from jgauge import cli, slot; slot.SHORT_LIMIT_SECONDS = 0.5;"
        " sys.exit(cli.main(sys.argv[1:]))"
    )
    env = {**os.environ, "HOME": str(tmp_path / "home"), "D": str(tmp_path)}
    began = time.monotonic()
    ran = subprocess.run(
        [sys.executable, "-c", limited, "test-slot", "--short", "--"]
        + ["sh", "-c", RUNS_UNTIL_RELEASED, "sh", "a"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert time.monotonic() - began < 5
    assert (tmp_path / "started.a").exists()
    assert (ran.returncode, ran.stdout) == (slot.TIMED_OUT, "")
    assert ran.stderr == "test-slot: stopped sh at 0.5 s, the short lane's limit\n"


def test_a_full_suite_does_not_enter_the_short_lane(slots):
    slots.hold(1, 2, 3, 4)
    ran = slots(name="a")
    assert ran.stderr.readline() == "test-slot: waiting for one of 4 slots\n"
    time.sleep(2.5 * slot.LOOK_EVERY_SECONDS)
    assert (ran.poll(), slots.started()) == (None, [])
    assert not list(slots.locks.glob("test-slot-short.*"))
    slots.free()
    assert slots.waits(lambda: slots.started() == ["a"])
    slots.release("a")
    assert ran.wait(timeout=5) == 0


def test_short_and_a_number_of_slots_together_run_nothing(slots):
    ran = slots("--short", "--slots", "2", command=["echo", "ran"])
    out, err = ran.communicate(timeout=5)
    assert (ran.returncode, out) == (2, "")
    assert "--short" in err


def test_a_short_job_stopped_at_its_limit_takes_what_it_started_with_it(tmp_path):
    limited = (
        "import sys; from jgauge import cli, slot; slot.SHORT_LIMIT_SECONDS = 0.5;"
        " slot.STOP_GRACE_SECONDS = 0.5; sys.exit(cli.main(sys.argv[1:]))"
    )
    started = 'sh -c "trap \\"\\" TERM; echo \\$\\$ > \\"$D/pid\\"; exec sleep 30" & wait'
    env = {**os.environ, "HOME": str(tmp_path / "home"), "D": str(tmp_path)}
    ran = subprocess.run(
        [sys.executable, "-c", limited, "test-slot", "--short", "--", "sh", "-c", started],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert ran.returncode == slot.TIMED_OUT
    left = int((tmp_path / "pid").read_text())
    deadline = time.monotonic() + 5
    while Path(f"/proc/{left}").exists() and time.monotonic() < deadline:
        if Path(f"/proc/{left}/stat").read_text().split()[2] == "Z":
            break
        time.sleep(0.02)
    gone = not Path(f"/proc/{left}").exists() or (
        Path(f"/proc/{left}/stat").read_text().split()[2] == "Z"
    )
    assert gone, f"process {left}, started by the short job, still runs after the stop"


def test_a_short_holder_told_to_stop_stops_what_its_command_started(slots):
    started = f"sh -c 'echo $$ > \"$D/pid\"; {RUNS_UNTIL_RELEASED}' sh a & wait"
    holder = slots("--short", command=["sh", "-c", started])
    assert slots.waits(lambda: slots.started() == ["a"])
    holder.terminate()
    holder.wait(timeout=5)
    pid = int((slots.state / "pid").read_text())
    assert slots.waits(lambda: not Path(f"/proc/{pid}").exists())
