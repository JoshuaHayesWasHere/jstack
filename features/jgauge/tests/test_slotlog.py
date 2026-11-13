"""The slot log's writer and report, in this process: the log keeps 30 days, a log that cannot
be written stops no run, and the report reads only what is a row. `test_slot.py` drives
`jgauge test-slot` itself and reads its rows back."""

import contextlib
import errno
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jgauge import slotlog
from test_room import BIN

NOON = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def rows(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_the_log_keeps_the_last_29_days_once_its_first_row_is_over_30_days_old(tmp_path):
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()
    now = datetime.now(UTC)
    old = {"at": (now - timedelta(days=31)).isoformat(), "event": "take", "id": "old"}
    kept = {"at": (now - timedelta(days=20)).isoformat(), "event": "take", "id": "kept"}
    log.write_text("".join(json.dumps(one) + "\n" for one in (old, kept)) + "not a row\n")

    taken = slotlog.take(log, "full", 3, 4, "mcp:t", ["make", "check"], 1.23456)
    slotlog.release(taken, 2)

    *before, take, release = rows(log)
    assert before == [kept]
    assert (take["event"], take["lane"], take["slot"], take["slots"]) == ("take", "full", 3, 4)
    assert (take["thread"], take["command"], take["waited"]) == ("mcp:t", ["make", "check"], 1.235)
    assert (take["pid"], take["cwd"]) == (os.getpid(), os.getcwd())
    skipped = ("at", "event", "waited", "repo")
    shared = {key: value for key, value in take.items() if key not in skipped}
    assert release == {
        **shared,
        "at": release["at"],
        "event": "release",
        "code": 2,
        "hold": release["hold"],
        "cpu_user": release["cpu_user"],
        "cpu_system": release["cpu_system"],
        "left": 0,
    }
    assert 0 <= release["hold"] < 5


def test_a_run_from_a_directory_since_removed_runs_and_logs_an_empty_cwd(tmp_path):
    locks, gone = tmp_path / "locks", tmp_path / "gone"
    gone.mkdir()
    env = {**os.environ, "JGAUGE_LOCKS_DIR": str(locks), "TMPFS": str(tmp_path)}
    ran = subprocess.run(
        [
            "sh",
            "-c",
            'cd "$1" && rmdir "$1" && exec "$2" test-slot -- true',
            "sh",
            gone,
            BIN / "jgauge",
        ],
        env=env,
        capture_output=True,
        text=True,
    )

    assert ran.returncode == 0, ran.stderr
    take, release = rows(slotlog.path(locks))
    assert (take["event"], take["cwd"], release["event"], release["cwd"]) == (
        "take",
        "",
        "release",
        "",
    )


def test_a_take_from_a_directory_since_removed_logs_an_empty_cwd(tmp_path, monkeypatch):
    log, gone = slotlog.path(tmp_path / "locks"), tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()

    slotlog.release(slotlog.take(log, "short", 1, 3, "", ["true"], 0), 0)

    assert [row["cwd"] for row in rows(log)] == ["", ""]


@pytest.mark.parametrize("where", ["outside a repository", "with no git to ask"])
def test_a_take_names_no_repo_outside_one_or_with_no_git_and_still_logs(
    tmp_path, monkeypatch, where
):
    log = slotlog.path(tmp_path / "locks")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    if where == "with no git to ask":
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    slotlog.release(slotlog.take(log, "short", 1, 3, "", ["true"], 0), 0)

    take, release = rows(log)
    assert (take["repo"], release["event"]) == ("", "release")


@pytest.mark.parametrize("blocked", ["parent is a file", "log is a directory"])
def test_a_log_that_cannot_be_written_stops_nothing(tmp_path, blocked):
    log = slotlog.path(tmp_path / "locks")
    if blocked == "parent is a file":
        log.parent.write_text("")
    else:
        log.mkdir(parents=True)
    slotlog.release(slotlog.take(log, "short", 1, 3, "", ["true"], 0), 0)


def stamp(minute):
    return (NOON + timedelta(minutes=minute)).isoformat()


def test_the_report_reads_only_rows_and_merges_waits_that_overlap(tmp_path, monkeypatch):
    """A take with no release whose holder lives, pid 1 here, is held to the span's end. Two
    waits that overlap, 10:01 to 10:05 and 10:03 to 10:08, are 7 minutes of waiting, and a lane
    with no holds prints nothing."""
    monkeypatch.setenv("JBUS_STATE_DIR", str(tmp_path / "jbus"))
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()
    assert slotlog.report(log, None, None, NOON.timestamp()) == []
    log.write_text("not a row\n")
    assert slotlog.report(log, None, None, NOON.timestamp()) == [f"test slots: no holds in {log}"]
    take = {"event": "take", "id": "a", "pid": 1, "lane": "full", "slot": 1, "slots": 2}
    take |= {"thread": "", "command": ["true"], "cwd": "/", "waited": 0}
    log.write_text(json.dumps({"at": stamp(0), **take}) + "\nnot a row\n")
    events = tmp_path / "jbus" / "jstack" / "events.jsonl"
    events.parent.mkdir(parents=True)
    woke = "slot-wake: woke mcp:{}, a full slot is free for `make`, after {} min"
    events.write_text(
        "\n".join(
            json.dumps(one)
            for one in (
                {"at": stamp(5), "event": "slot-wake", "line": woke.format("a", 4)},
                {"at": stamp(8), "event": "slot-wake", "line": woke.format("b", 5)},
                {"at": stamp(6), "event": "stall", "line": "stall: x"},
            )
        )
    )
    start, until = NOON.timestamp(), (NOON + timedelta(minutes=10)).timestamp()

    assert slotlog.report(log, until, None, start) == [f"test slots: the span is empty in {log}"]
    assert slotlog.report(log, start, until, until + 60)[1:] == [
        "  full: 1 holds, 0 lost; mean occupancy 1.000 of 2 slots;"
        " Little's law (takes/s x mean hold) 0.000; wait in the call p50 0.0 s, p90 0.0 s",
        "  full, while a thread waited for a slot (0.12 h, from 2 slot-wake events):"
        " mean occupancy 1.00 (50% of 2)",
    ]


def test_a_log_whose_first_line_is_not_a_row_is_appended_to_as_it_is(tmp_path):
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()
    log.write_text("not a row\n")
    slotlog.take(log, "full", 1, 4, "", ["true"], 0)
    first, take = log.read_text().splitlines()
    assert first == "not a row" and json.loads(take)["event"] == "take"


def test_the_report_sums_the_cpu_of_the_holds_released_in_the_span_by_lane_and_by_repo(
    tmp_path, monkeypatch
):
    """A release before the span counts nothing, one written before the log had the CPU is
    counted apart, and 600 CPU seconds over a 10 minute span is one core."""
    monkeypatch.setenv("JBUS_STATE_DIR", str(tmp_path / "jbus"))
    log = slotlog.path(tmp_path / "locks")
    log.parent.mkdir()

    def hold(key, lane, repo, taken, released, cpu=None):
        take = {"event": "take", "id": key, "pid": 1, "lane": lane, "slot": 1, "slots": 3}
        take |= {"thread": "", "command": ["make"], "cwd": "/", "waited": 0, "repo": repo}
        end = {"event": "release", "id": key, "code": 0}
        if cpu:
            end |= {"cpu_user": cpu[0], "cpu_system": cpu[1]}
        return [{"at": stamp(taken), **take}, {"at": stamp(released), **end}]

    log.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in [
                *hold("before", "full", "jstack", -3, -1, (999, 0)),
                *hold("a", "full", "jstack", 0, 4, (400, 50)),
                *hold("b", "short", "jstack", 1, 2, (20, 10)),
                *hold("c", "full", "cs-shelf", 2, 6, (100, 20)),
                *hold("old", "short", "", 3, 5),
            ]
        )
    )
    start, until = NOON.timestamp(), (NOON + timedelta(minutes=10)).timestamp()

    assert slotlog.report(log, start, until, until)[-5:] == [
        "  CPU of the 3 holds released in the span, user + system seconds, and the mean cores"
        " over the span: (1 more released with no CPU on record)",
        "    lane full: 570.0 s (500.0 + 70.0), 0.95 cores",
        "    lane short: 30.0 s (20.0 + 10.0), 0.05 cores",
        "    repo jstack: 480.0 s (420.0 + 60.0), 0.80 cores",
        "    repo cs-shelf: 120.0 s (100.0 + 20.0), 0.20 cores",
    ]

    log.write_text("".join(json.dumps(row) + "\n" for row in hold("old", "short", "", 3, 5)))
    assert not any("CPU" in line for line in slotlog.report(log, start, until, until))


SPIN = "import time\nwhile time.process_time() < 0.25: pass\ntime.sleep(0.2)"
LEAVES_A_SPIN = '(setsid "$1" -c "$2" &)'


def test_a_release_counts_a_detached_child_that_burns_after_the_command_exits(tmp_path):
    """The command's shell starts a Python in a session of its own and exits at once, so no
    process the holder waits for ever reaps it. The Python then spins until it has used 0.25 s
    of CPU, and that quarter second is the take's: the release row says so, to the two clock
    ticks `/proc` loses to rounding where the machine gives the take no cgroup. It idles a moment
    before it ends, so a release that reads the CPU of what still runs sees all of it."""
    env = {**os.environ, "JGAUGE_LOCKS_DIR": str(tmp_path / "locks"), "TMPFS": str(tmp_path)}
    env.pop("JGAUGE_TEST_SLOT", None)
    ran = subprocess.run(
        [BIN / "jgauge", "test-slot", "--short", "--", "sh", "-c", LEAVES_A_SPIN, "sh"]
        + [sys.executable, SPIN],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert ran.returncode == 0, ran.stderr
    _take, release = rows(slotlog.path(tmp_path / "locks"))
    assert release["cpu_user"] + release["cpu_system"] >= 0.25 - 2 / os.sysconf("SC_CLK_TCK")


def test_with_no_cgroup_a_release_counts_a_detached_child_that_carries_the_take(
    tmp_path, monkeypatch
):
    """Where the take can have no cgroup of its own, the processes that carry it in their
    environment make its CPU: the same detached spin is counted from them, to the two clock
    ticks `/proc` loses to rounding."""
    monkeypatch.setattr(slotlog, "CGROUPS", tmp_path / "no cgroups")
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "short", 1, 3, "", ["sh"], 0)
    subprocess.run(["sh", "-c", LEAVES_A_SPIN, "sh", sys.executable, SPIN], check=True)
    slotlog.release(taken, 0)

    _take, release = rows(log)
    assert release["cpu_user"] + release["cpu_system"] >= 0.25 - 2 / os.sysconf("SC_CLK_TCK")


def a_cgroup_tree(tmp_path, monkeypatch):
    """A stand-in for `/sys/fs/cgroup` that has the holder's own cgroup, so a take makes its
    cgroup there whatever the machine's cgroups allow; returns the holder's cgroup."""
    (line,) = (slotlog.PROCS / "self" / "cgroup").read_text().splitlines()
    home = tmp_path / "cgroups" / line.removeprefix("0::/").strip("/")
    home.mkdir(parents=True)
    monkeypatch.setattr(slotlog, "CGROUPS", tmp_path / "cgroups")
    return home


def test_a_release_records_the_cgroup_s_cpu_and_the_processes_left(tmp_path, monkeypatch):
    """The release's CPU is the take's cgroup's `cpu.stat`, `left` counts the processes still in
    it after the drain, and a take clears the cgroup an earlier take left behind."""
    home = a_cgroup_tree(tmp_path, monkeypatch)
    (home / f"{slotlog.PREFIX}stale" / slotlog.PREFIX / "run").mkdir(parents=True)
    monkeypatch.setattr(slotlog, "DRAIN_SECONDS", 0.1)
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "short", 1, 3, "", ["sh"], 0)
    (own,) = home.glob(f"{slotlog.PREFIX}*")
    (own / "run" / "cgroup.procs").write_text(f"{os.getpid()}\n1\n")
    (own / "cpu.stat").write_text("usage_usec 2000000\nuser_usec 1500000\nsystem_usec 500000\n")
    slotlog.release(taken, 0)

    _take, release = rows(log)
    assert (release["cpu_user"], release["cpu_system"], release["left"]) == (1.5, 0.5, 1)
    assert own.name != f"{slotlog.PREFIX}stale"
    assert not (home / f"{slotlog.PREFIX}stale").exists()


def test_a_release_whose_cgroup_cannot_be_read_writes_its_row_with_no_cpu(tmp_path, monkeypatch):
    """A take's cgroup gone under it (here, one with no `cpu.stat` and no process list) costs
    the row its CPU, and the release still writes the row and returns, so the run keeps its exit
    code."""
    home = a_cgroup_tree(tmp_path, monkeypatch)
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "short", 1, 3, "", ["sh"], 0)
    (own,) = home.glob(f"{slotlog.PREFIX}*")
    (own / "run" / "cgroup.procs").unlink()
    slotlog.release(taken, 3)

    _take, release = rows(log)
    assert release["code"] == 3
    assert "cpu_user" not in release and "left" not in release


def test_a_take_s_cgroup_is_capped_at_its_workers_and_a_take_with_none_runs_uncapped(
    tmp_path, monkeypatch
):
    """A take of 3 workers may run 3 cores: the holder's cgroup turns the cpu controller on for
    its children, and the take's cgroup's `cpu.max` is 3 periods of CPU a period. Where the take
    can have no cgroup there is nothing to cap, and its CPU is still counted from the processes
    that carry it."""
    home = a_cgroup_tree(tmp_path, monkeypatch)
    (home / "cgroup.subtree_control").write_text("memory\n")
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "full", 1, 4, "", ["make", "check"], 0, workers=3)
    (own,) = home.glob(f"{slotlog.PREFIX}*")
    assert (own / "cpu.max").read_text().split() == ["300000", "100000"]
    assert (home / "cgroup.subtree_control").read_text() == "+cpu"
    slotlog.release(taken, 0)

    monkeypatch.setattr(slotlog, "CGROUPS", tmp_path / "no cgroups")
    taken = slotlog.take(log, "full", 1, 4, "", ["sh"], 0, workers=3)
    subprocess.run(["sh", "-c", LEAVES_A_SPIN, "sh", sys.executable, SPIN], check=True)
    slotlog.release(taken, 0)

    *_, release = rows(log)
    assert release["cpu_user"] + release["cpu_system"] >= 0.25 - 2 / os.sysconf("SC_CLK_TCK")
    assert not (tmp_path / "no cgroups").exists()


def the_kernel_s_threaded_rule(monkeypatch, root):
    """The fake tree keeps the kernel's rule for a cgroup whose parent turns the cpu controller
    on for its children: it is born `domain invalid`, and once `threaded` it lists its threads
    and refuses a read of its processes (EOPNOTSUPP)."""
    made, read = Path.mkdir, Path.read_text

    def mkdir(self, *args, **kwargs):
        made(self, *args, **kwargs)
        control = self.parent / "cgroup.subtree_control"
        if self.is_relative_to(root) and control.exists() and "+cpu" in read(control):
            (self / "cgroup.type").write_text("domain invalid\n")

    def read_text(self, *args, **kwargs):
        kind = self.parent / "cgroup.type"
        if self.name == "cgroup.procs" and kind.exists() and read(kind).strip() == "threaded":
            raise OSError(errno.EOPNOTSUPP, "Operation not supported", str(self))
        return read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(Path, "read_text", read_text)


def test_a_take_under_a_cgroup_with_processes_is_threaded_and_counts_its_threads_processes(
    tmp_path, monkeypatch
):
    """Under a holder's cgroup that has processes and the cpu controller on for its children,
    the take's cgroup and its leaf are made threaded, so the holder may move in, and the release
    counts the processes left from the threads the leaf lists, a thread since gone left out."""
    home = a_cgroup_tree(tmp_path, monkeypatch)
    (home / "cgroup.subtree_control").write_text("+cpu\n")
    the_kernel_s_threaded_rule(monkeypatch, tmp_path / "cgroups")
    monkeypatch.setattr(slotlog, "DRAIN_SECONDS", 0.1)
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "short", 1, 3, "", ["sh"], 0, workers=1)
    (own,) = home.glob(f"{slotlog.PREFIX}*")
    assert (own / "cgroup.type").read_text() == "threaded"
    assert (own / "run" / "cgroup.type").read_text() == "threaded"
    assert (own / "cpu.max").read_text().split() == ["100000", "100000"]
    (own / "run" / "cgroup.threads").write_text(f"{os.getpid()}\n1\n{2**22 + 1}\n")
    (own / "cpu.stat").write_text("user_usec 700000\nsystem_usec 100000\n")
    slotlog.release(taken, 0)

    _take, release = rows(log)
    assert (release["cpu_user"], release["cpu_system"], release["left"]) == (0.7, 0.1, 1)


SPINS_FOR_A_SECOND = "import time\nend = time.monotonic() + 1\nwhile time.monotonic() < end: pass"
SPINS_TWO = 'for i in 1 2; do "$1" -c "$2" & done; wait'
OWN_QUOTA = 'cat "/sys/fs/cgroup$(sed -n "s/^0:://p" /proc/self/cgroup)/cpu.max" 2> /dev/null'


def test_a_take_of_one_worker_runs_two_spinning_processes_on_one_core(tmp_path):
    """Two processes that each spin for a second of wall time use about 2 s of CPU uncapped. In
    a take of 1 worker they share one core, so the release counts at most 1.2 s, the 0.2 for
    the two Pythons' start and the cap's first period. The command's own cgroup sets no quota,
    so a Makefile that counts its workers from its cgroup's `cpu.max` counts them as before.
    Where the cgroup tree here allows no cap (no cgroup v2 one the holder may write, or no cpu
    controller to delegate), the test skips."""
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "short", 1, 3, "", ["sh"], 0, workers=1)
    try:
        (line,) = (slotlog.PROCS / "self" / "cgroup").read_text().splitlines()
        own = Path("/sys/fs/cgroup", line.removeprefix("0::/")).parent
        cap = []
        if own.name.startswith(slotlog.PREFIX):
            with contextlib.suppress(OSError):
                cap = (own / "cpu.max").read_text().split()
        quota = subprocess.run(["sh", "-c", OWN_QUOTA], capture_output=True, text=True).stdout
        subprocess.run(
            ["sh", "-c", SPINS_TWO, "sh", sys.executable, SPINS_FOR_A_SECOND], check=True
        )
    finally:
        slotlog.release(taken, 0)

    if cap != ["100000", "100000"]:
        pytest.skip(f"the cgroup tree here allows the take no cap: {cap}")
    _take, release = rows(log)
    assert release["cpu_user"] + release["cpu_system"] <= 1.2
    assert quota.split()[:1] in ([], ["max"])
