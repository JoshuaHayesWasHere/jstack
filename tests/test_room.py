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


def put(path, text, mode=0o644):
    """Write the file whole: beside itself first, then renamed into place, so a reader or an
    exec of it sees the old file or the new one, never one half written or open for writing.
    A file that already says that is left as it is."""
    if path.exists() and path.read_text() == text:
        return
    part = path.with_name(f".{path.name}.part")
    part.write_text(text)
    part.chmod(mode)
    part.replace(path)


def machine(where, load, cores, memory, pressure, plan=FRESH, slots=EMPTY, cpu="0.00"):
    """A machine made of files, as `room` reads one, and the environment that points it there.
    It can be written anew while `room` reads it."""
    proc, stub, tmp = where / "proc", where / "stub", where / "stub" / "tmp"
    (proc / "pressure").mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    if slots is None:
        (tmp / "df").unlink(missing_ok=True)
    else:
        put(tmp / "df", slots if isinstance(slots, str) else table(*slots))
    put(
        stub / "df",
        '#!/bin/sh\n[ "$#" = 2 ] && [ "$1" = -Pi ] || exit 64\n'
        'echo "$2" > "$(dirname "$0")/asked"\ncat "$2/df"\n',
        0o755,
    )
    put(proc / "loadavg", f"{load} 1.10 0.90 2/2647 4039610\n")
    put(
        proc / "meminfo",
        f"MemTotal:       31975012 kB\nMemFree:          812340 kB\nMemAvailable:   {memory} kB\n",
    )
    put(
        proc / "pressure" / "memory",
        f"some avg10=0.00 avg60={pressure} avg300=0.00 total=58137000\n"
        "full avg10=0.00 avg60=77.00 avg300=0.00 total=27343911\n",
    )
    put(
        proc / "pressure" / "cpu",
        f"some avg10=0.00 avg60={cpu} avg300=0.00 total=1812999696\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
    )
    put(stub / "nproc", f"#!/bin/sh\necho {cores}\n", 0o755)
    if plan is None:
        (where / "limits").unlink(missing_ok=True)
    else:
        put(where / "limits", plan if isinstance(plan, str) else limits(plan))
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


def test_yelenas_busiest_load_with_little_cpu_pressure_goes(tmp_path):
    """Load 29 on 24 cores with CPU pressure at 8, as yelena ran on 2026-10-19: busy, and
    nothing waiting long for a core."""
    busy = {**IDLE, "load": "29.00", "cores": "24", "cpu": "8.00"}
    assert says(machine(tmp_path, **busy)) == "go"


@pytest.mark.parametrize(
    ("reading", "value", "said"),
    [
        ("load", "24.00", "wait: load 24.00 is at or over 200% of 12 cores"),
        ("load", "24.01", "wait: load 24.01 is at or over 200% of 12 cores"),
        ("load", "99.00", "wait: load 99.00 is at or over 200% of 12 cores"),
        ("cores", "4", None),
        ("cpu", "40.00", "wait: CPU pressure 40.00 is at or over 40"),
        ("cpu", "71.30", "wait: CPU pressure 71.30 is at or over 40"),
        ("memory", 6 * KB_PER_GB - 1, "wait: 6.0 GB of memory available, under 6"),
        ("memory", 2 * KB_PER_GB, "wait: 2.0 GB of memory available, under 6"),
        ("pressure", "10.00", "wait: memory pressure 10.00 is at or over 10"),
        ("pressure", "54.31", "wait: memory pressure 54.31 is at or over 10"),
    ],
)
def test_a_reading_past_its_threshold_waits_and_says_which(tmp_path, reading, value, said):
    idle = {**IDLE, "load": "8.50"}
    assert says(machine(tmp_path, **idle)) == "go"
    assert says(machine(tmp_path, **{**idle, reading: value})) == (
        said or "wait: load 8.50 is at or over 200% of 4 cores"
    )


@pytest.mark.parametrize(
    ("reading", "value"),
    [
        ("load", "23.99"),
        ("cpu", "39.99"),
        ("memory", 6 * KB_PER_GB),
        ("pressure", "9.99"),
    ],
)
def test_a_reading_just_inside_its_threshold_goes(tmp_path, reading, value):
    assert says(machine(tmp_path, **{**IDLE, reading: value})) == "go"


@pytest.mark.parametrize("cores", ["4", "12", "20"])
def test_a_load_at_its_threshold_waits_on_any_core_count(tmp_path, cores):
    at = f"{int(cores) * 2:.2f}"
    assert says(machine(tmp_path, **{**IDLE, "cores": cores, "load": at})) == (
        f"wait: load {at} is at or over 200% of {cores} cores"
    )


def test_a_threshold_changed_in_the_block_is_the_one_the_reason_gives(tmp_path):
    assert check().count("MEMORY=6\n") == 1
    changed = check().replace("MEMORY=6\n", "MEMORY=6.5\n")
    env = machine(tmp_path, **{**IDLE, "memory": int(6.2 * KB_PER_GB)})
    assert says(env) == "go"
    assert says(env, changed) == "wait: 6.2 GB of memory available, under 6.5"


def test_the_first_reading_with_no_room_is_the_one_named(tmp_path):
    full = {"load": "30.00", "cores": "12", "memory": KB_PER_GB, "pressure": "54.31", "cpu": "90"}
    assert says(machine(tmp_path, **full)).startswith("wait: load ")
    assert says(machine(tmp_path, **{**full, "load": "0.42"})).startswith("wait: CPU pressure ")
    assert says(machine(tmp_path, **{**full, "load": "0.42", "cpu": "1"})).startswith(
        "wait: 1.0 GB "
    )


@pytest.mark.parametrize("gone", ["loadavg", "pressure/cpu", "meminfo", "pressure/memory"])
def test_a_file_that_cannot_be_read_waits(tmp_path, gone):
    env = machine(tmp_path, **IDLE)
    (tmp_path / "proc" / gone).unlink()
    assert says(env).startswith("wait: ")


@pytest.mark.parametrize("file", ["loadavg", "pressure/cpu", "meminfo", "pressure/memory"])
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
        ("100", "100% used, at or over 100%"),
        ("100.0", "100.0% used, at or over 100%"),
        ("101", "101% used, at or over 100%"),
    ],
)
def test_a_window_at_or_past_the_cushion_waits_and_says_which_and_when(
    tmp_path, window, used, said
):
    left = FRESH[window][1]
    assert says(machine(tmp_path, **IDLE, plan={**FRESH, window: ("99.99", left)})) == "go"
    line = says(machine(tmp_path, **IDLE, plan={**FRESH, window: (used, left + 59)}))
    resets = {2 * HOUR: "2 h 0 min", 90 * HOUR: "3 d 18 h 0 min"}[left]
    assert line == f"wait: the {WINDOWS[window]} limit is {said}, and resets in {resets}"


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("left", [0, -1, -4 * HOUR])
def test_a_window_past_its_reset_is_not_known_and_is_said(tmp_path, window, left):
    spent = {**FRESH, window: ("100", 60)}
    assert says(machine(tmp_path, **IDLE, plan=spent)).startswith(f"wait: the {WINDOWS[window]} ")
    env = machine(tmp_path, **IDLE, plan={**spent, window: ("100", left)})
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
    plan = {"five_hour": ("99", -HOUR), "seven_day": ("100", 30 * HOUR + 59)}
    half = ran(machine(tmp_path, **IDLE, plan=plan))
    assert half.stdout == (
        "wait: the weekly limit is 100% used, at or over 100%, and resets in 1 d 6 h 0 min\n"
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
    env = machine(tmp_path, **IDLE, plan=limits({"seven_day": ("100", 30 * HOUR + 59)}))
    half = ran(env)
    assert half.stdout == (
        "wait: the weekly limit is 100% used, at or over 100%, and resets in 1 d 6 h 0 min\n"
    )
    assert half.stderr == ""


def test_the_cushion_changed_in_the_block_is_the_one_the_reason_gives(tmp_path):
    assert check().count("CUSHION=100\n") == 1
    changed = check().replace("CUSHION=100\n", "CUSHION=70\n")
    env = machine(tmp_path, **IDLE, plan={**FRESH, "five_hour": ("72", 20 * 60 + 59)})
    assert says(env) == "go"
    assert says(env, changed) == (
        "wait: the five-hour limit is 72% used, at or over 70%, and resets in 0 h 20 min"
    )


def test_the_machine_is_named_before_the_plan_and_five_hours_before_the_week(tmp_path):
    spent = {"five_hour": ("100", HOUR), "seven_day": ("100", HOUR)}
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
        limits({**FRESH, "seven_day": ("100", 5 * HOUR + 59)})
    )
    env = {**machine(tmp_path, **IDLE), "HOME": str(home)}
    del env["LIMITS"]
    assert re.fullmatch(r"wait: the weekly limit is 100% used, .* resets in 5 h 0 min", says(env))


def waited(env, limit, every="0.05"):
    """What `jgauge room --wait` printed and how it exited, looking that often."""
    command = [str(BIN / "jgauge"), "room", "--wait", limit, "--every", every]
    ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    return ran.stdout.splitlines(), ran.returncode


def test_a_machine_rewritten_while_its_stubs_run_is_never_seen_half_written(tmp_path):
    """A wait looks while a timer writes the machine anew, as the tests below do."""
    machine(tmp_path, **IDLE)
    stub, stop, seen = tmp_path / "stub", threading.Event(), []

    def look():
        while not stop.is_set():
            try:
                df = subprocess.run(
                    [str(stub / "df"), "-Pi", str(stub / "tmp")], capture_output=True, text=True
                )
                seen.append(len(df.stdout.splitlines()) == 2 or df.stdout)
            except OSError as error:
                seen.append(error)

    lookers = [threading.Thread(target=look) for _ in range(4)]
    for one in lookers:
        one.start()
    errors, end, n = [], time.monotonic() + 1, 0
    try:
        while time.monotonic() < end:
            n += 1
            try:
                machine(tmp_path, **{**IDLE, "load": f"{n % 20}.00"}, slots=(1048576, n))
            except OSError as error:
                errors.append(error)
    finally:
        stop.set()
        for one in lookers:
            one.join()
    assert errors == [] and seen and set(seen) == {True}


def test_a_machine_written_again_the_same_leaves_its_stubs_as_they_were(tmp_path):
    machine(tmp_path, **IDLE)
    names = ("stub/df", "stub/nproc", "stub/tmp/df", "proc/loadavg", "limits")
    before = {name: (tmp_path / name).stat() for name in names}
    machine(tmp_path, **IDLE)
    after = {name: (tmp_path / name).stat() for name in names}
    assert {name: (one.st_ino, one.st_mtime_ns) for name, one in after.items()} == {
        name: (one.st_ino, one.st_mtime_ns) for name, one in before.items()
    }


def test_a_wait_for_room_ends_in_go_once_the_machine_has_room(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "24.00"})
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
    env = machine(tmp_path, **{**IDLE, "load": "24.00"})
    started = time.monotonic()
    assert waited(env, "0.5") == (["wait: load 24.00 is at or over 200% of 12 cores"], 75)
    assert 0.5 <= time.monotonic() - started < 10


def test_the_reason_a_wait_ends_with_is_the_one_of_its_last_look(tmp_path):
    env = machine(tmp_path, **{**IDLE, "load": "24.00"})
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
    env = machine(tmp_path, **{**IDLE, "load": "24.00"}, plan=None)
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
    busy = machine(tmp_path, **{**IDLE, "load": "24.00"})
    assert waited(busy, "5", every=every) == ([], 2)


def test_a_room_asked_with_no_wait_answers_at_once_and_exits_0_as_before(tmp_path):
    busy = machine(tmp_path, **{**IDLE, "load": "24.00"})
    ran = subprocess.run([str(BIN / "jgauge"), "room"], env=busy, capture_output=True, text=True)
    assert (ran.stdout, ran.returncode) == ("wait: load 24.00 is at or over 200% of 12 cores\n", 0)


STALE = 21 * 60


def tmpfs(where, slots):
    """A machine whose `$TMPFS` is made of files: `df` counts every entry under it as a used
    slot, out of `slots`, so what is removed from it is freed at once."""
    env = machine(where, **IDLE, slots=None)
    put(
        where / "stub" / "df",
        '#!/bin/sh\n[ "$#" = 2 ] && [ "$1" = -Pi ] || exit 64\n'
        f'used=$(find "$2" -mindepth 1 | wc -l)\n'
        f'echo "Filesystem Inodes IUsed IFree IUse% Mounted on"\n'
        f'echo "tmpfs {slots} $used $(({slots} - used)) - $2"\n',
        0o755,
    )
    return env, Path(env["TMPFS"])


def runs(tmp, user, numbers, files=10, age=STALE):
    """Runs of pytest left under `pytest-of-<user>`, each with `files` files, `age` seconds old."""
    made = []
    for number in numbers:
        run = tmp / f"pytest-of-{user}" / f"pytest-{number}"
        (run / "test_it0").mkdir(parents=True)
        for n in range(files):
            (run / "test_it0" / f"f{n}").write_text("")
        made.append(run)
    for path in [*made, *{run.parent for run in made}]:
        os.utime(path, (time.time() - age,) * 2)
    return made


def test_a_full_tmp_of_stale_pytest_runs_is_cleared_and_then_goes(tmp_path):
    env, tmp = tmpfs(tmp_path, 60)
    runs(tmp, "joshua", [1, 2, 3])
    runs(tmp, "other", [7])
    (tmp / "keep").mkdir()
    (tmp / "keep" / "data").write_text("")
    cleared = ran(env)
    assert cleared.stdout == "go\n"
    assert cleared.stderr == (
        f"room: removed 4 stale pytest directories under {tmp}, freeing 48 file slots\n"
    )
    assert sorted(path.relative_to(tmp).as_posix() for path in tmp.rglob("*")) == [
        "keep",
        "keep/data",
        "pytest-of-joshua",
        "pytest-of-other",
    ]


@pytest.mark.parametrize("how", ["cwd", "fd"])
def test_a_pytest_run_a_live_process_holds_is_never_removed(tmp_path, how):
    env, tmp = tmpfs(tmp_path, 99)
    held, *stale = runs(tmp, "joshua", [1, 2, 3, 4, 5, 6, 7])
    inside = held / "test_it0"
    with open(inside / "f0") as open_file:
        live = subprocess.Popen(
            ["sleep", "60"],
            cwd=inside if how == "cwd" else tmp_path,
            stdin=open_file if how == "fd" else subprocess.DEVNULL,
        )
    try:
        (tmp_path / "proc" / str(live.pid)).symlink_to(f"/proc/{live.pid}")
        alone = ran(env)
    finally:
        live.kill()
        live.wait()
    assert alone.stdout == "go\n"
    assert alone.stderr.startswith("room: removed 6 stale pytest directories under ")
    assert held.is_dir() and len(list(inside.iterdir())) == 10
    assert not any(path.exists() for path in stale)


def test_a_pytest_run_whose_lock_names_a_live_process_is_never_removed(tmp_path):
    env, tmp = tmpfs(tmp_path, 99)
    live_run, dead_run, *stale = runs(tmp, "joshua", [1, 2, 3, 4, 5, 6, 7])
    gone = subprocess.Popen(["true"])
    gone.wait()
    live = subprocess.Popen(["sleep", "60"], cwd=tmp_path)
    try:
        (tmp_path / "proc" / str(live.pid)).symlink_to(f"/proc/{live.pid}")
        for run, pid in [(live_run, live.pid), (dead_run, gone.pid)]:
            (run / ".lock").write_text(str(pid))
            os.utime(run, (time.time() - STALE,) * 2)
        alone = ran(env)
    finally:
        live.kill()
        live.wait()
    assert alone.stdout == "go\n"
    assert alone.stderr.startswith("room: removed 6 stale pytest directories under ")
    assert live_run.is_dir() and len(list((live_run / "test_it0").iterdir())) == 10
    assert not dead_run.exists() and not any(path.exists() for path in stale)


def test_held_or_fresh_pytest_runs_still_wait_and_nothing_is_removed(tmp_path):
    env, tmp = tmpfs(tmp_path, 50)
    fresh = runs(tmp, "joshua", [1, 2, 3], age=60)
    (held,) = runs(tmp, "joshua", [4])
    before = sorted(tmp.rglob("*"))
    live = subprocess.Popen(["sleep", "60"], cwd=held)
    try:
        (tmp_path / "proc" / str(live.pid)).symlink_to(f"/proc/{live.pid}")
        full = ran(env)
    finally:
        live.kill()
        live.wait()
    assert full.stdout == f"wait: {tmp} has 49 of 50 file slots used, over 85%\n"
    assert full.stderr == ""
    assert sorted(tmp.rglob("*")) == before and all(path.is_dir() for path in fresh)


def test_a_tmp_with_room_is_not_cleared(tmp_path):
    env, tmp = tmpfs(tmp_path, 1000)
    made = runs(tmp, "joshua", [1, 2, 3])
    room = ran(env)
    assert (room.stdout, room.stderr) == ("go\n", "")
    assert all(path.is_dir() for path in made)


def test_nothing_but_pytest_runs_under_pytest_of_is_removed_from_a_full_tmp(tmp_path):
    env, tmp = tmpfs(tmp_path, 11)
    for name in ["pytest-1", "scratch-1", "pytest-of-joshua-not"]:
        (tmp / name / "inside").mkdir(parents=True)
    (tmp / "pytest-of-joshua" / "notes" / "pytest-3").mkdir(parents=True)
    (tmp / "pytest-of-joshua" / "pytest-9").write_text("a file, not a run")
    (tmp / "pytest-of-joshua" / "pytest-current").symlink_to(tmp / "pytest-2")
    for path in tmp.rglob("*"):
        os.utime(path, (time.time() - STALE,) * 2, follow_symlinks=False)
    before = sorted(tmp.rglob("*"))
    full = ran(env)
    assert full.stdout.startswith("wait: ") and full.stderr == ""
    assert sorted(tmp.rglob("*")) == before


def test_no_skill_holds_a_copy_of_the_check(tmp_path):
    held = [path for path in SKILLS.rglob("*") if path.is_file() and "CUSHION=" in path.read_text()]
    assert held == []
    used_up = {**FRESH, "five_hour": ("100", HOUR + 59)}
    assert says(machine(tmp_path, **IDLE, plan=used_up)).startswith(
        "wait: the five-hour limit is 100% used, at or over 100%,"
    )


def light(env, *more):
    """What `jgauge room --light` printed and how it exited: the check a review asks."""
    command = [str(BIN / "jgauge"), "room", "--light", *more]
    ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    return ran.stdout.splitlines(), ran.returncode


@pytest.mark.parametrize(
    ("load", "cores"), [("24.00", "12"), ("48.00", "24"), ("60.00", "24"), ("99.00", "4")]
)
def test_a_light_look_goes_at_a_load_that_holds_a_launch(tmp_path, load, cores):
    env = machine(tmp_path, **{**IDLE, "load": load, "cores": cores})
    assert says(env).startswith(f"wait: load {load} is at or over 200% of {cores} cores")
    assert light(env) == (["go"], 0)
    started = time.monotonic()
    assert light(env, "--wait", "15") == (["go"], 0)
    assert time.monotonic() - started < 5


def test_a_light_look_needs_no_load_it_cannot_read(tmp_path):
    env = machine(tmp_path, **IDLE)
    (tmp_path / "proc" / "loadavg").unlink()
    assert says(env) == "wait: the load or the core count could not be read"
    assert light(env) == (["go"], 0)


def test_a_light_look_skips_cpu_pressure_as_it_skips_the_load(tmp_path):
    env = machine(tmp_path, **{**IDLE, "cpu": "90.00"})
    assert says(env) == "wait: CPU pressure 90.00 is at or over 40"
    assert light(env) == (["go"], 0)
    (tmp_path / "proc" / "pressure" / "cpu").unlink()
    assert says(env) == "wait: the CPU pressure could not be read"
    assert light(env) == (["go"], 0)


@pytest.mark.parametrize(
    ("readings", "said"),
    [
        ({"memory": 6 * KB_PER_GB - 1}, "wait: 6.0 GB of memory available, under 6"),
        ({"pressure": "10.00"}, "wait: memory pressure 10.00 is at or over 10"),
        ({"slots": (1000, 851)}, "wait: {} has 851 of 1000 file slots used, over 85%"),
        (
            {"plan": {**FRESH, "five_hour": ("100", HOUR + 59)}},
            "wait: the five-hour limit is 100% used, at or over 100%, and resets in 1 h 0 min",
        ),
    ],
)
def test_a_light_look_still_waits_on_every_other_reading_with_the_same_reason(
    tmp_path, readings, said
):
    env = machine(tmp_path, **{**IDLE, "load": "60.00", "cores": "24", "cpu": "90", **readings})
    said = said.format(env["TMPFS"])
    assert light(env) == ([said], 0)
    assert light(env, "--wait", "0.2", "--every", "0.05") == ([said], 75)
    assert says(machine(tmp_path, **{**IDLE, **readings})) == said


def test_a_look_with_no_flag_reads_the_load_whatever_its_environment_says(tmp_path):
    env = {**machine(tmp_path, **{**IDLE, "load": "24.00"}), "SKIP_LOAD": "1"}
    assert says(env) == "wait: load 24.00 is at or over 200% of 12 cores"
    assert waited(env, "0") == (["wait: load 24.00 is at or over 200% of 12 cores"], 75)


PRIME = "claudeAgent_claude_prime"


def test_the_plan_is_read_for_the_instance_room_is_asked_about(tmp_path):
    """The ledger is a file for each instance: `jgauge room --instance <id>` reads that one's,
    and the built-in instance's is the file LIMITS names."""
    env = machine(tmp_path, **IDLE)
    Path(f"{env['LIMITS']}.{PRIME}").write_text(
        limits({**FRESH, "seven_day": ("100", 30 * HOUR + 59)})
    )
    asked = [str(BIN / "jgauge"), "room", "--instance"]
    on_prime = subprocess.run([*asked, PRIME], env=env, capture_output=True, text=True)
    assert on_prime.stdout == (
        "wait: the weekly limit is 100% used, at or over 100%, and resets in 1 d 6 h 0 min\n"
    )
    on_first = subprocess.run([*asked, "claudeAgent"], env=env, capture_output=True, text=True)
    assert (on_first.stdout, says(env)) == ("go\n", "go")
    other = subprocess.run([*asked, "codex"], env=env, capture_output=True, text=True)
    assert other.stdout == "go\n" and f"{env['LIMITS']}.codex does not give them" in other.stderr


def test_a_name_that_is_no_instance_is_a_wait(tmp_path):
    env = machine(tmp_path, **IDLE)
    for name in ("../limits", "a b"):
        assert (
            says({**env, "INSTANCE": name})
            == f"wait: {name} is not the name of a provider instance"
        )
