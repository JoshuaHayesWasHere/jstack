"""`jbus telemetry` keeps the gh calls of each hour past the call log's rotation.

`jsettings.proc` appends one line a call to `gh-calls.jsonl` in jbus's state directory, and at
16 MiB moves it to `gh-calls.old.jsonl` with `os.replace` and starts a new one. The test writes
the lines as it does, rotates the file the same way between two builds, runs the real command,
and reads the store with `sqlite3`.
"""

import json
import os
from pathlib import Path

import pytest

from jsettings.proc import CALLS
from test_jbus_telemetry import Machine


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def call(at, caller="jbus.tick._asked < jbus.tick._read", status=0, remaining=4000, http=None):
    line = {
        "at": at,
        "caller": caller,
        "endpoint": "/repos/o/r/pulls?secret=1",
        "status": status,
        "remaining": remaining,
        "resource": "core",
        "reset": 1794268902,
    }
    if http:
        line["http"] = http
    return line


def append(machine, *lines):
    with open(machine.state_dir / CALLS, "a") as log:
        for line in lines:
            log.write(json.dumps(line) + "\n")


def rotate(machine):
    """Move the log aside as `proc._log` does once it passes `KEPT`."""
    os.replace(machine.state_dir / CALLS, machine.state_dir / f"{Path(CALLS).stem}.old.jsonl")


def total(machine):
    with machine.store() as store:
        return store.execute("select sum(calls) from gh_hours").fetchone()[0]


def test_each_line_is_counted_once_across_a_rotation(machine):
    append(
        machine,
        call("2026-11-09T10:05:00+00:00", remaining=4100),
        call("2026-11-09T10:15:00+00:00", http="HTTP/2.0 304 Not Modified", remaining=4090),
        call("2026-11-09T10:59:59+00:00", status=1, remaining=None),
        call("2026-11-09T11:00:00+00:00", caller="jbus.watch._api < jbus.wakes.read"),
        call("2026-11-09T11:30:00+00:00", remaining=3500),
    )
    machine.build()
    append(machine, *(call(f"2026-11-09T11:4{n}:00+00:00", remaining=900 + n) for n in range(3)))
    rotate(machine)
    append(machine, *(call(f"2026-11-09T11:5{n}:00+00:00", remaining=800 + n) for n in range(2)))
    machine.build()

    assert total(machine) == 10
    with machine.store() as store:
        rows = store.execute(
            "select hour, caller, resource, calls, not_modified, failed, least from gh_hours"
            " order by hour, caller"
        ).fetchall()
    assert rows == [
        ("2026-11-09T10", "jbus.tick._asked", "core", 3, 1, 1, 4090),
        ("2026-11-09T11", "jbus.tick._asked", "core", 6, 0, 0, 800),
        ("2026-11-09T11", "jbus.watch._api", "core", 1, 0, 0, 4000),
    ]

    machine.build()
    assert total(machine) == 10


def test_a_log_of_neither_inode_is_read_from_its_start(machine):
    append(machine, call("2026-11-09T10:05:00+00:00"))
    machine.build()
    rotate(machine)
    append(machine, call("2026-11-09T10:06:00+00:00"))
    rotate(machine)
    append(machine, call("2026-11-09T10:07:00+00:00"))
    machine.build()

    assert total(machine) == 3
