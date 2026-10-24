"""`pass.json` says when the last pass started and ended, and what it saw of each open row.

A pass writes it when it starts and again when it ends, so a pass that hangs or dies is one with a
start and no end. Every test runs the real pass or the real command against the faked T3 Code
server, `gh` and `jmerge` of `test_jbus_kitchen`. Nothing reaches the network.
"""

import fcntl
import json
import os
import signal
import stat
import sys
import time
from datetime import datetime, timedelta

import pytest

import daemons
import jbus
from jbus import record
from test_jbus_kitchen import NOW, complete

STARTED = "2026-10-12T15:00:00Z"
ROLLUP = [
    {
        "name": "lint",
        "status": "COMPLETED",
        "conclusion": "SUCCESS",
        "startedAt": "2026-10-12T14:50:00Z",
        "completedAt": "2026-10-12T14:51:00Z",
    },
    {
        "name": "check",
        "status": "IN_PROGRESS",
        "conclusion": "",
        "startedAt": "2026-10-12T14:55:00Z",
        "completedAt": "0001-01-01T00:00:00Z",
    },
]
ROWS = {
    "alpha": {
        "threads": 1,
        "thread_status": "running",
        "thread_updated": "2026-10-12T14:58:00Z",
        "live": "moving",
        "gone": False,
        "checks": "pending",
        "check": {
            "name": "check",
            "state": "pending",
            "started": "2026-10-12T14:55:00Z",
            "completed": None,
        },
    },
    "beta": {
        "threads": 0,
        "thread_status": None,
        "thread_updated": None,
        "live": None,
        "gone": False,
        "checks": "",
        "check": None,
    },
}
ALPHA = {
    "id": "mcp:thread-1",
    "title": "crew: alpha",
    "role": "crew",
    "slug": "alpha",
    "status": "running",
    "createdAt": "2026-10-12T14:55:00Z",
    "updatedAt": "2026-10-12T14:58:00Z",
    "items": None,
    "wrote": "2026-10-12T14:58:00Z",
    "live": "moving",
    "silent": 2,
    "run": None,
    "run_started": None,
    "queued": 0,
    "pending": 0,
    "page": False,
}
WHOLE = {
    "started": STARTED,
    "ended": "2026-10-12T15:00:19Z",
    "seconds": 19.0,
    "projects": {"demo": {"seen": STARTED, "rows": ROWS, "threads": [ALPHA]}},
    "silent": {},
}


def took(kitchen, *seconds):
    """Make each pass that follows take the next figure of `seconds`, as `record.clock` measures
    it."""
    ticks = iter([at for long in seconds for at in (100.0, 100.0 + long)])
    kitchen.monkeypatch.setattr(record, "clock", lambda: next(ticks))


def written(kitchen):
    return json.loads((kitchen.state_dir / "pass.json").read_text())


def three_rows(kitchen):
    """Make three rows: one with a thread and an open pull request, one with neither, and one
    merged."""
    for slug in ("alpha", "beta", "gamma"):
        text = complete(slug)
        assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=2))
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "statusCheckRollup": ROLLUP}])
    kitchen.set("merged.json", [kitchen.merged("gamma", 6, "d" * 40)])


def test_a_pass_writes_its_start_its_end_its_seconds_and_what_it_saw_of_each_open_row(kitchen):
    three_rows(kitchen)
    took(kitchen, 19)
    kitchen.poll()
    assert written(kitchen) == WHOLE
    assert stat.S_IMODE((kitchen.state_dir / "pass.json").stat().st_mode) == 0o600


def test_jbus_status_prints_the_record_beside_the_status_file(kitchen):
    three_rows(kitchen)
    took(kitchen, 19)
    kitchen.poll()
    code, said = kitchen.main("status")
    assert (code, json.loads(said)) == (0, {**kitchen.status(), "pass": WHOLE})


def test_a_pass_stopped_halfway_leaves_a_start_with_no_end(kitchen):
    """The pass is the real command, and the test kills it while its `jmerge` runs."""
    three_rows(kitchen)
    took(kitchen, 19)
    kitchen.poll()
    kitchen.set("jmerge-sleep", "60")
    ran = len(kitchen.log("jmerge"))
    before = datetime.now().astimezone()
    stopped = daemons.start([sys.executable, "-m", "jbus", "poll"])
    try:
        until = time.monotonic() + 60
        while len(kitchen.log("jmerge")) == ran and time.monotonic() < until:
            time.sleep(0.05)
        assert len(kitchen.log("jmerge")) == ran + 1
    finally:
        os.killpg(stopped.pid, signal.SIGKILL)
        stopped.wait()
    half = written(kitchen)
    assert (half["ended"], half["seconds"]) == (None, None)
    assert before - timedelta(seconds=1) <= datetime.fromisoformat(half["started"])
    assert half["projects"] == WHOLE["projects"]
    code, said = kitchen.main("status")
    assert (code, json.loads(said)["pass"]) == (0, half)


def test_a_pass_that_could_not_ask_keeps_what_the_pass_before_it_saw(kitchen):
    three_rows(kitchen)
    took(kitchen, 19, 2.5)
    kitchen.poll()
    (kitchen.config_dir / "t3.json").unlink()
    kitchen.poll(NOW + timedelta(minutes=1))
    assert written(kitchen) == {
        "started": "2026-10-12T15:01:00Z",
        "ended": "2026-10-12T15:01:02Z",
        "seconds": 2.5,
        "projects": WHOLE["projects"],
        "silent": {"demo": "T3 Code"},
    }


def test_a_pass_that_finds_the_lock_held_leaves_the_record_as_it_was(kitchen):
    took(kitchen, 19)
    kitchen.poll()
    with open(kitchen.state_dir / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert kitchen.poll(NOW + timedelta(minutes=1)) == ["busy"]
    assert written(kitchen) == {
        **WHOLE,
        "projects": {"demo": {"seen": STARTED, "rows": {}, "threads": []}},
    }


def test_a_first_pass_stopped_before_any_status_is_still_printed(kitchen):
    record.Record(jbus.load(), NOW).start()
    code, said = kitchen.main("status")
    started = {"started": STARTED, "ended": None, "seconds": None, "projects": {}, "silent": {}}
    printed = {"pass": started, "streaks": {}, "stranded": {}, "homes_off_bus": []}
    assert (code, json.loads(said)) == (0, printed)


def test_a_record_that_cannot_be_written_is_said_and_the_pass_does_all_it_did(kitchen):
    kitchen.state_dir.mkdir()
    (kitchen.state_dir / "pass.json.tmp").mkdir()
    said = kitchen.poll()
    assert [line.split(":")[0] for line in said if line.startswith("pass record")] == [
        "pass record failed",
        "pass record failed",
    ]
    assert kitchen.log("jmerge") == ["--all"]
    assert kitchen.status()["last_pass"] == "2026-10-12 11:00 ET"
    assert not (kitchen.state_dir / "pass.json").exists()


def test_two_threads_for_one_row_are_counted_and_neither_is_the_rows_thread(kitchen):
    three_rows(kitchen)
    kitchen.t3.thread("beta", "running")
    kitchen.t3.thread("beta", "waiting")
    took(kitchen, 19)
    kitchen.poll()
    assert written(kitchen)["projects"]["demo"]["rows"]["beta"] == {**ROWS["beta"], "threads": 2}


AT = "2026-10-12T14:55:00Z"
NOT_SET = "0001-01-01T00:00:00Z"
DONE = {
    "name": "check",
    "status": "COMPLETED",
    "conclusion": "FAILURE",
    "startedAt": AT,
    "completedAt": "2026-10-12T14:57:00Z",
}


@pytest.mark.parametrize(
    ("rollup", "latest"),
    [
        (
            [{"context": "deploy", "state": "SUCCESS", "startedAt": AT}, DONE],
            {"name": "check", "state": "failed", "started": AT, "completed": DONE["completedAt"]},
        ),
        (
            [DONE, {"context": "deploy", "state": "SUCCESS", "startedAt": AT}],
            {"name": "deploy", "state": "passed", "started": AT, "completed": None},
        ),
        (
            [
                {"name": "lint", "status": "QUEUED", "startedAt": NOT_SET, "completedAt": NOT_SET},
                DONE,
            ],
            {"name": "lint", "state": "pending", "started": None, "completed": None},
        ),
        ([], None),
    ],
)
def test_the_latest_check_is_the_one_that_started_last_or_the_last_listed_of_equals(
    kitchen, rollup, latest
):
    three_rows(kitchen)
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "statusCheckRollup": rollup}])
    took(kitchen, 19)
    kitchen.poll()
    assert written(kitchen)["projects"]["demo"]["rows"]["alpha"]["check"] == latest


@pytest.mark.parametrize(
    "before",
    [
        [],
        {"projects": []},
        {"projects": {"gone": {"seen": STARTED, "rows": {}}, "demo": {"seen": "x", "rows": {}}}},
    ],
)
def test_a_record_that_is_not_one_or_names_a_project_the_config_dropped_is_not_carried(
    kitchen, before
):
    three_rows(kitchen)
    jbus.write_json(kitchen.state_dir / "pass.json", before)
    took(kitchen, 19)
    kitchen.poll()
    assert written(kitchen) == WHOLE


def test_a_pass_whose_end_cannot_be_written_is_said_and_keeps_its_start_with_no_end(kitchen):
    """The test blocks the write once the pass is under way, after the pass wrote its start."""
    kitchen.t3.on_list = lambda: (kitchen.state_dir / "pass.json.tmp").mkdir(exist_ok=True)
    said = kitchen.poll()
    assert [line.split(":")[0] for line in said if line.startswith("pass record")] == [
        "pass record failed"
    ]
    assert kitchen.status()["last_pass"] == "2026-10-12 11:00 ET"
    assert written(kitchen) == {
        "started": STARTED,
        "ended": None,
        "seconds": None,
        "projects": {},
        "silent": {},
    }
