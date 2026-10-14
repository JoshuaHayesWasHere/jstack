import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILLS = REPO / "skills"
ROOM = REPO / "src" / "jgauge" / "room.sh"
BIN = Path(sys.executable).parent
KB_PER_GB = 1048576
IDLE = {"load": "0.42", "cores": "12", "memory": 19 * KB_PER_GB, "pressure": "0.00"}
HOUR = 3600
WINDOWS = {"five_hour": "five-hour", "seven_day": "weekly"}
FRESH = {"five_hour": ("12.5", 2 * HOUR), "seven_day": ("40", 90 * HOUR)}
EMPTY = (1048576, 12)
NEITHER = "five-hour and weekly limits are not known: {} does not give them"


def check():
    """The check before a launch: `room.sh`, the one copy, which `jgauge room` runs."""
    return ROOM.read_text()


def limits(windows):
    """The file the status line writes: a window a line, its name, percent used and reset time."""
    now = int(time.time())
    return "".join(f"{name} {used} {now + left}\n" for name, (used, left) in windows.items())


def table(slots, used):
    """What `df -Pi` prints for a filesystem with that many file slots and that many used."""
    return (
        "Filesystem      Inodes  IUsed   IFree IUse% Mounted on\n"
        f"tmpfs {slots} {used} {slots - used} {used * 100 // slots if slots else '-'}% /made/up\n"
    )


def machine(where, load, cores, memory, pressure, plan=FRESH, slots=EMPTY):
    """A machine made of files, as `room` reads one, and the environment that points it there."""
    proc, stub, tmp = where / "proc", where / "stub", where / "stub" / "tmp"
    (proc / "pressure").mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "df").unlink(missing_ok=True)
    if slots is not None:
        (tmp / "df").write_text(slots if isinstance(slots, str) else table(*slots))
    (stub / "df").write_text(
        '#!/bin/sh\n[ "$#" = 2 ] && [ "$1" = -Pi ] || exit 64\n'
        'echo "$2" > "$(dirname "$0")/asked"\ncat "$2/df"\n'
    )
    (stub / "df").chmod(0o755)
    (proc / "loadavg").write_text(f"{load} 1.10 0.90 2/2647 4039610\n")
    (proc / "meminfo").write_text(
        f"MemTotal:       31975012 kB\nMemFree:          812340 kB\nMemAvailable:   {memory} kB\n"
    )
    (proc / "pressure" / "memory").write_text(
        f"some avg10=0.00 avg60={pressure} avg300=0.00 total=58137000\n"
        "full avg10=0.00 avg60=77.00 avg300=0.00 total=27343911\n"
    )
    (stub / "nproc").write_text(f"#!/bin/sh\necho {cores}\n")
    (stub / "nproc").chmod(0o755)
    (where / "limits").unlink(missing_ok=True)
    if plan is not None:
        (where / "limits").write_text(plan if isinstance(plan, str) else limits(plan))
    return {
        **os.environ,
        "PROC": str(proc),
        "LIMITS": str(where / "limits"),
        "TMPFS": str(tmp),
        "PATH": f"{stub}:{BIN}:{os.environ['PATH']}",
    }


def uv(stub):
    """A `uv` that runs the command after `run --project <path>` as it is, from PATH."""
    (stub / "uv").write_text(
        '#!/bin/sh\n[ "$1 $2" = "run --project" ] || exit 64\nshift 3\nexec "$@"\n'
    )
    (stub / "uv").chmod(0o755)


def ran(env, script=None):
    """What `jgauge room` says on that machine, or a changed copy of its file run as it is."""
    command = ["sh", "-c", script] if script else [str(BIN / "jgauge"), "room"]
    return subprocess.run(command, env=env, capture_output=True, text=True, check=True)


def says(env, script=None):
    (line,) = ran(env, script).stdout.splitlines()
    return line


def test_an_idle_machine_has_room(tmp_path):
    assert says(machine(tmp_path, **IDLE)) == "go"


@pytest.mark.parametrize(
    ("reading", "value", "said"),
    [
        ("load", "10.20", "wait: load 10.20 is at or over 85% of 12 cores"),
        ("load", "10.21", "wait: load 10.21 is at or over 85% of 12 cores"),
        ("load", "30.00", "wait: load 30.00 is at or over 85% of 12 cores"),
        ("cores", "4", None),
        ("memory", 6 * KB_PER_GB - 1, "wait: 6.0 GB of memory available, under 6"),
        ("memory", 2 * KB_PER_GB, "wait: 2.0 GB of memory available, under 6"),
        ("pressure", "10.00", "wait: memory pressure 10.00 is at or over 10"),
        ("pressure", "54.31", "wait: memory pressure 54.31 is at or over 10"),
    ],
)
def test_a_reading_past_its_threshold_waits_and_says_which(tmp_path, reading, value, said):
    idle = {**IDLE, "load": "3.50"}
    assert says(machine(tmp_path, **idle)) == "go"
    assert says(machine(tmp_path, **{**idle, reading: value})) == (
        said or "wait: load 3.50 is at or over 85% of 4 cores"
    )


@pytest.mark.parametrize(
    ("reading", "value"),
    [("load", "10.19"), ("memory", 6 * KB_PER_GB), ("pressure", "9.99")],
)
def test_a_reading_just_inside_its_threshold_goes(tmp_path, reading, value):
    assert says(machine(tmp_path, **{**IDLE, reading: value})) == "go"


@pytest.mark.parametrize("cores", ["4", "12", "20"])
def test_a_load_at_its_threshold_waits_on_any_core_count(tmp_path, cores):
    at = f"{int(cores) * 0.85:.2f}"
    assert says(machine(tmp_path, **{**IDLE, "cores": cores, "load": at})) == (
        f"wait: load {at} is at or over 85% of {cores} cores"
    )


def test_a_threshold_changed_in_the_block_is_the_one_the_reason_gives(tmp_path):
    assert check().count("MEMORY=6\n") == 1
    changed = check().replace("MEMORY=6\n", "MEMORY=6.5\n")
    env = machine(tmp_path, **{**IDLE, "memory": int(6.2 * KB_PER_GB)})
    assert says(env) == "go"
    assert says(env, changed) == "wait: 6.2 GB of memory available, under 6.5"


def test_the_first_reading_with_no_room_is_the_one_named(tmp_path):
    full = {"load": "30.00", "cores": "12", "memory": KB_PER_GB, "pressure": "54.31"}
    assert says(machine(tmp_path, **full)).startswith("wait: load ")
    assert says(machine(tmp_path, **{**full, "load": "0.42"})).startswith("wait: 1.0 GB ")


@pytest.mark.parametrize("gone", ["loadavg", "meminfo", "pressure/memory"])
def test_a_file_that_cannot_be_read_waits(tmp_path, gone):
    env = machine(tmp_path, **IDLE)
    (tmp_path / "proc" / gone).unlink()
    assert says(env).startswith("wait: ")


@pytest.mark.parametrize("file", ["loadavg", "meminfo", "pressure/memory"])
def test_a_file_with_no_reading_in_it_waits(tmp_path, file):
    env = machine(tmp_path, **IDLE)
    (tmp_path / "proc" / file).write_text("nothing here\n")
    assert says(env).startswith("wait: ")


def test_a_core_count_that_cannot_be_read_waits(tmp_path):
    env = machine(tmp_path, **IDLE)
    (tmp_path / "stub" / "nproc").write_text("#!/bin/sh\nexit 1\n")
    assert says(env).startswith("wait: ")


@pytest.mark.parametrize(
    ("slots", "said"),
    [
        ((1000, 1000), "wait: {} has 1000 of 1000 file slots used, over 85%"),
        ((1000, 851), "wait: {} has 851 of 1000 file slots used, over 85%"),
        ((1048576, 891290), "wait: {} has 891290 of 1048576 file slots used, over 85%"),
        ((1000, 850), "go"),
        (EMPTY, "go"),
        ((0, 0), "go"),
        (None, "wait: the file slots of {} could not be read"),
        ("nothing here\n", "wait: the file slots of {} could not be read"),
        (
            table(1000, 1000).splitlines(keepends=True)[0],
            "wait: the file slots of {} could not be read",
        ),
    ],
)
def test_a_temporary_filesystem_short_of_file_slots_waits_and_says_how_many(tmp_path, slots, said):
    env = machine(tmp_path, **IDLE, slots=slots)
    assert says(env) == said.format(env["TMPFS"])


def test_the_file_slots_are_those_of_tmp_unless_told_otherwise(tmp_path):
    env = machine(tmp_path, **IDLE)
    del env["TMPFS"]
    ran(env)
    assert (tmp_path / "stub" / "asked").read_text() == "/tmp\n"


def test_the_file_slots_are_read_from_the_df_of_the_machine_it_runs_on(tmp_path):
    env = {**machine(tmp_path, **IDLE), "TMPFS": str(tmp_path)}
    (tmp_path / "stub" / "df").unlink()
    assert re.fullmatch(rf"go|wait: {tmp_path} has \d+ of \d+ file slots used, over 85%", says(env))


def test_the_share_of_file_slots_changed_in_the_block_is_the_one_the_reason_gives(tmp_path):
    assert check().count("SLOTS=85\n") == 1
    changed = check().replace("SLOTS=85\n", "SLOTS=50\n")
    env = machine(tmp_path, **IDLE, slots=(1000, 501))
    assert says(env) == "go"
    assert says(env, changed) == f"wait: {env['TMPFS']} has 501 of 1000 file slots used, over 50%"


def test_the_file_slots_are_named_after_the_memory_and_before_the_plan(tmp_path):
    spent = {"five_hour": ("95", HOUR), "seven_day": ("95", HOUR)}
    full = {"plan": spent, "slots": (1000, 1000)}
    assert says(machine(tmp_path, **{**IDLE, "pressure": "54.31"}, **full)).startswith(
        "wait: memory pressure "
    )
    assert says(machine(tmp_path, **IDLE, **full)).endswith(" file slots used, over 85%")


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize(
    ("used", "said"),
    [
        ("85", "85% used, at or over 85%"),
        ("85.01", "85.01% used, at or over 85%"),
        ("100", "100% used, at or over 85%"),
    ],
)
def test_a_window_at_or_past_the_cushion_waits_and_says_which_and_when(
    tmp_path, window, used, said
):
    left = FRESH[window][1]
    assert says(machine(tmp_path, **IDLE, plan={**FRESH, window: ("84.99", left)})) == "go"
    line = says(machine(tmp_path, **IDLE, plan={**FRESH, window: (used, left + 59)}))
    resets = {2 * HOUR: "2 h 0 min", 90 * HOUR: "3 d 18 h 0 min"}[left]
    assert line == f"wait: the {WINDOWS[window]} limit is {said}, and resets in {resets}"


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("left", [0, -1, -4 * HOUR])
def test_a_window_past_its_reset_is_not_known_and_is_said(tmp_path, window, left):
    spent = {**FRESH, window: ("99", 60)}
    assert says(machine(tmp_path, **IDLE, plan=spent)).startswith(f"wait: the {WINDOWS[window]} ")
    env = machine(tmp_path, **IDLE, plan={**spent, window: ("99", left)})
    stale = ran(env)
    assert stale.stdout == "go\n"
    assert stale.stderr == (
        f"note: the plan's {WINDOWS[window]} limit is not known: "
        f"{env['LIMITS']} is past its reset\n"
    )


def test_two_windows_past_their_resets_are_named_in_one_note(tmp_path):
    env = machine(tmp_path, **IDLE, plan={"five_hour": ("99", -HOUR), "seven_day": ("12", -60)})
    stale = ran(env)
    assert stale.stdout == "go\n"
    assert stale.stderr == (
        "note: the plan's five-hour and weekly limits are not known: "
        f"{env['LIMITS']} is past their resets\n"
    )


@pytest.mark.parametrize(
    ("plan", "reasons"),
    [
        (
            {"five_hour": ("99", -HOUR)},
            "is past the five-hour limit's reset and does not give the weekly limit",
        ),
        (
            {"seven_day": ("99", -HOUR)},
            "does not give the five-hour limit and is past the weekly limit's reset",
        ),
    ],
)
def test_a_window_past_its_reset_beside_a_missing_one_gives_both_reasons(tmp_path, plan, reasons):
    env = machine(tmp_path, **IDLE, plan=plan)
    blind = ran(env)
    assert blind.stdout == "go\n"
    assert blind.stderr == (
        f"note: the plan's five-hour and weekly limits are not known: {env['LIMITS']} {reasons}\n"
    )


def test_a_fresh_window_past_the_cushion_waits_beside_one_past_its_reset(tmp_path):
    plan = {"five_hour": ("99", -HOUR), "seven_day": ("91.5", 30 * HOUR + 59)}
    half = ran(machine(tmp_path, **IDLE, plan=plan))
    assert half.stdout == (
        "wait: the weekly limit is 91.5% used, at or over 85%, and resets in 1 d 6 h 0 min\n"
    )
    assert half.stderr == ""


def test_a_machine_with_no_room_waits_whatever_the_reset_times(tmp_path):
    plan = {"five_hour": ("99", -HOUR), "seven_day": ("99", -HOUR)}
    full = ran(machine(tmp_path, **{**IDLE, "memory": 2 * KB_PER_GB}, plan=plan))
    assert (full.stdout, full.stderr) == ("wait: 2.0 GB of memory available, under 6\n", "")


def test_limits_under_the_cushion_go_with_nothing_more_said(tmp_path):
    under = ran(machine(tmp_path, **IDLE))
    assert (under.stdout, under.stderr) == ("go\n", "")


@pytest.mark.parametrize(
    ("plan", "unknown"),
    [
        (None, NEITHER),
        ("", NEITHER),
        ("not a limits file\n", NEITHER),
        ('{"five_hour": {"used_percentage": 99}}\n', NEITHER),
        ("five_hour 99 soon\nseven_day lots 99999999999\n", NEITHER),
        (
            limits({"seven_day": FRESH["seven_day"]}),
            "five-hour limit is not known: {} does not give it",
        ),
        (
            limits({"five_hour": FRESH["five_hour"]}),
            "weekly limit is not known: {} does not give it",
        ),
    ],
    ids=[
        "no file",
        "an empty file",
        "not a limits file",
        "the status line's JSON",
        "words for numbers",
        "the weekly window alone",
        "the five-hour window alone",
    ],
)
def test_limits_that_cannot_be_read_never_stop_a_launch_and_are_said(tmp_path, plan, unknown):
    env = machine(tmp_path, **IDLE, plan=plan)
    blind = ran(env)
    assert blind.stdout == "go\n"
    assert blind.stderr == f"note: the plan's {unknown.format(env['LIMITS'])}\n"


def test_a_limits_file_that_is_a_directory_goes_with_the_note(tmp_path):
    env = machine(tmp_path, **IDLE, plan=None)
    (tmp_path / "limits").mkdir()
    blind = ran(env)
    assert blind.stdout == "go\n" and blind.stderr.startswith("note: the plan's five-hour and ")


def test_the_one_window_a_file_gives_still_waits_past_the_cushion(tmp_path):
    env = machine(tmp_path, **IDLE, plan=limits({"seven_day": ("91.5", 30 * HOUR + 59)}))
    half = ran(env)
    assert half.stdout == (
        "wait: the weekly limit is 91.5% used, at or over 85%, and resets in 1 d 6 h 0 min\n"
    )
    assert half.stderr == ""


def test_the_cushion_changed_in_the_block_is_the_one_the_reason_gives(tmp_path):
    assert check().count("CUSHION=85\n") == 1
    changed = check().replace("CUSHION=85\n", "CUSHION=70\n")
    env = machine(tmp_path, **IDLE, plan={**FRESH, "five_hour": ("72", 20 * 60 + 59)})
    assert says(env) == "go"
    assert says(env, changed) == (
        "wait: the five-hour limit is 72% used, at or over 70%, and resets in 0 h 20 min"
    )


def test_the_machine_is_named_before_the_plan_and_five_hours_before_the_week(tmp_path):
    spent = {"five_hour": ("95", HOUR), "seven_day": ("95", HOUR)}
    assert says(machine(tmp_path, **{**IDLE, "pressure": "54.31"}, plan=spent)).startswith(
        "wait: memory pressure "
    )
    assert says(machine(tmp_path, **IDLE, plan=spent)).startswith("wait: the five-hour limit ")


def test_a_machine_with_no_room_waits_whatever_the_limits_file(tmp_path):
    full = ran(machine(tmp_path, **{**IDLE, "load": "30.00"}, plan=None))
    assert full.stdout.startswith("wait: load ") and full.stderr == ""


def test_the_check_reads_the_machine_it_runs_on(tmp_path):
    here = {**os.environ, "LIMITS": str(tmp_path / "none")}
    (line,) = ran(here).stdout.splitlines()
    assert line == "go" or line.startswith("wait: ")
    assert "could not be read" not in line


def test_the_check_reads_the_limits_file_of_the_account_it_runs_under(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "state" / "claude").mkdir(parents=True)
    (home / ".local" / "state" / "claude" / "limits").write_text(
        limits({**FRESH, "seven_day": ("88", 5 * HOUR + 59)})
    )
    env = {**machine(tmp_path, **IDLE), "HOME": str(home)}
    del env["LIMITS"]
    assert re.fullmatch(r"wait: the weekly limit is 88% used, .* resets in 5 h 0 min", says(env))


def waited(env, limit, every="0.05"):
    """What `jgauge room --wait` printed and how it exited, looking that often."""
    command = [str(BIN / "jgauge"), "room", "--wait", limit, "--every", every]
    ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    return ran.stdout.splitlines(), ran.returncode


def test_a_wait_for_room_ends_in_go_once_the_machine_has_room(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "11.00"})
    room = threading.Timer(0.4, machine, [tmp_path], IDLE)
    room.start()
    try:
        started = time.monotonic()
        assert waited(env, "15") == (["go"], 0)
    finally:
        room.cancel()
        room.join()
    assert 0.4 <= time.monotonic() - started < 10


def test_a_wait_for_room_that_never_comes_ends_at_its_limit_with_the_last_reason(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "11.00"})
    started = time.monotonic()
    assert waited(env, "0.5") == (["wait: load 11.00 is at or over 85% of 12 cores"], 75)
    assert 0.5 <= time.monotonic() - started < 10


def test_the_reason_a_wait_ends_with_is_the_one_of_its_last_look(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "11.00"})
    short = threading.Timer(0.3, machine, [tmp_path], {**IDLE, "memory": 2 * KB_PER_GB})
    short.start()
    try:
        assert waited(env, "1.5") == (["wait: 2.0 GB of memory available, under 6"], 75)
    finally:
        short.cancel()
        short.join()


def test_a_wait_of_no_seconds_looks_once_and_still_tells_go_from_wait(tmp_path):
    assert waited(machine(tmp_path, **IDLE), "0", every="15") == (["go"], 0)
    busy = machine(tmp_path, **{**IDLE, "pressure": "25.00"})
    assert waited(busy, "0", every="15") == (["wait: memory pressure 25.00 is at or over 10"], 75)


def test_a_wait_says_a_limit_that_is_not_known_once_whatever_the_number_of_looks(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "11.00"}, plan=None)
    room = threading.Timer(0.3, machine, [tmp_path], {**IDLE, "plan": None})
    room.start()
    try:
        command = [str(BIN / "jgauge"), "room", "--wait", "15", "--every", "0.05"]
        ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    finally:
        room.cancel()
        room.join()
    assert (ran.stdout, ran.returncode) == ("go\n", 0)
    assert ran.stderr.count("note: ") == 1


@pytest.mark.parametrize("limit", ["-1", "soon", "nan", "inf"])
def test_a_wait_that_is_not_a_number_of_seconds_is_refused_before_any_look(tmp_path, limit):
    lines, code = waited(machine(tmp_path, **IDLE), limit)
    assert (lines, code) == ([], 2)


@pytest.mark.parametrize("every", ["0", "-1", "often"])
def test_a_wait_that_would_look_with_no_pause_is_refused_before_any_look(tmp_path, every):
    busy = machine(tmp_path, **{**IDLE, "load": "11.00"})
    assert waited(busy, "5", every=every) == ([], 2)


def test_a_room_asked_with_no_wait_answers_at_once_and_exits_0_as_before(tmp_path):
    busy = machine(tmp_path, **{**IDLE, "load": "11.00"})
    ran = subprocess.run([str(BIN / "jgauge"), "room"], env=busy, capture_output=True, text=True)
    assert (ran.stdout, ran.returncode) == ("wait: load 11.00 is at or over 85% of 12 cores\n", 0)


def test_no_skill_holds_a_copy_of_the_check():
    held = [path for path in SKILLS.rglob("*") if path.is_file() and "CUSHION=" in path.read_text()]
    assert held == [] and "CUSHION=85\n" in ROOM.read_text()
