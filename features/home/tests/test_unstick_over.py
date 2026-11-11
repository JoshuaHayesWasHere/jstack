"""unstick's script reads whether a row is over from jbus's one `over` (`jbus.work.over`), and
names no final status of its own: a fourth copy of that rule could drift from the one jbus keeps.
Each test writes a project's state, runs the script, and reads which rows it counts as open.
"""

import json
import os
import subprocess
import sys

from jbus import queue, work
from test_unstick import NOW, SCRIPT, project, unstick

SWAPPED = """
import runpy, sys
from jbus import work
over = set(sys.argv.pop(1).split(","))
work.over = lambda row: row.get("status") in over
sys.argv[0] = sys.argv.pop(1)
runpy.run_path(sys.argv[0], run_name="__main__")
"""
"""Run unstick with `jbus.work.over` saying a row is over when its status is in the first
argument's list, so a script that decides it by a list of its own shows it."""


def opened(tmp_path, over=None):
    """The slugs unstick reports as open, each row's slug its status, under `over` when named."""
    project(tmp_path / "state", [(status, status, "working", 5, {}) for status in queue.STATUSES])
    if over is None:
        said = unstick(tmp_path, "--json", "--all")
    else:
        locks = tmp_path / "locks"
        locks.mkdir(exist_ok=True)
        (locks / "test-slot-waiters.json").write_text("[]")
        env = os.environ | {"JBUS_STATE_DIR": str(tmp_path / "state")}
        env["JGAUGE_LOCKS_DIR"] = str(locks)
        argv = [",".join(over), str(SCRIPT), "--now", NOW.isoformat(), "--json", "--all"]
        run = [sys.executable, "-c", SWAPPED, *argv]
        said = subprocess.run(run, capture_output=True, text=True, env=env, check=True).stdout
    return sorted(one["slug"] for one in json.loads(said))


def test_a_row_is_left_out_exactly_when_jbus_says_it_is_over(tmp_path):
    assert opened(tmp_path) == sorted(s for s in queue.STATUSES if not work.over({"status": s}))


def test_unstick_counts_a_row_open_by_over_and_by_no_list_of_its_own(tmp_path):
    over = ("failed", "left")

    assert opened(tmp_path, over) == sorted(s for s in queue.STATUSES if s not in over)
