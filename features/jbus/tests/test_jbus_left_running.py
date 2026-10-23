"""A crew, reviewer or scout thread can leave a process running after its turn: a `yes` in its
worktree, a server in a temporary folder it made. Its shell is gone, so the process's parent is
1, and it holds cores until somebody kills it. Like `test_jbus_resume.py`, the tests run the real
pass against the fakes, and the processes they leave are real ones."""

import os
import signal
import subprocess
import time
from datetime import timedelta

import pytest

from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def orphan(cwd, *command, env=None):
    """Start `command` in `cwd` from a shell that exits at once, as a crew's shell does at the
    end of its turn, so the process's parent is 1. Return its pid."""
    started = subprocess.run(
        ["sh", "-c", 'cd "$1" || exit; shift; "$@" > /dev/null 2>&1 < /dev/null & echo $!', "sh"]
        + [str(cwd), *command],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    pid = int(started.stdout)
    for _ in range(50):
        if parent(pid) == 1:
            return pid
        time.sleep(0.02)
    raise AssertionError(f"{pid} was not handed to pid 1, so it is no orphan of this machine")


def parent(pid):
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return int(stat.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return None


def alive(pid):
    """Whether the process runs: a zombie that pid 1 has not reaped yet has stopped."""
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


@pytest.fixture
def stray():
    """The pids a test started, each killed at the end whatever the test did."""
    started = []
    yield started
    for pid in started:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def ended_crew(kitchen, tmp_path, status="completed"):
    """A row whose crew jbus launched into its worktree, and whose turn then ended."""
    tree = tmp_path / "trees" / "alpha"
    add(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(minutes=3))
    kitchen.git("worktree", "add", "-q", "-b", "alpha", str(tree))
    thread = kitchen.t3.threads[-1]
    thread.update({"status": status, "updatedAt": thread["createdAt"]})
    kitchen.t3.at_work.discard(thread["threadId"])
    return tree, thread


def test_a_busy_process_a_crew_left_in_its_worktree_is_stopped_once_its_turn_ended(
    kitchen, tmp_path, stray
):
    tree, _ = ended_crew(kitchen, tmp_path)
    stray.append(orphan(tree, "yes"))
    assert alive(stray[0])
    kitchen.poll()
    assert not alive(stray[0])
