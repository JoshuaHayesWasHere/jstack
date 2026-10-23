"""A crew, reviewer or scout thread can leave a process running after its turn: a `yes` in its
worktree, a server in a temporary folder it made. Its shell is gone, so the process's parent is
1, and it holds cores until somebody kills it. Like `test_jbus_resume.py`, the tests run the real
pass against the fakes, and the processes they leave are real ones."""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from datetime import timedelta

import pytest

from jbus import mirror, strays
from test_jbus_kitchen import NOW, RESULT, Kitchen
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


def ended_crew(kitchen, tmp_path, status="completed", under="trees"):
    """A row whose crew jbus launched into its worktree, and whose turn then ended."""
    tree = tmp_path / under / "alpha"
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


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(strays, "GAP", 0.3)


def session_of(tmp_path, folder, session="a-session-of-alpha", text="hello"):
    """The environment of a process that a Claude session working in `folder` started, with
    that session's transcript where Claude keeps it: the user's first message is `text`."""
    config = tmp_path / "claude"
    kept = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(folder))
    kept.mkdir(parents=True, exist_ok=True)
    entries = [
        {"type": "queue-operation"},
        {"type": "user", "message": {"role": "user", "content": text}},
        {"type": "user", "message": {"role": "user", "content": "/scout alpha"}},
    ]
    (kept / f"{session}.jsonl").write_text("".join(json.dumps(one) + "\n" for one in entries))
    return {**os.environ, "CLAUDE_CODE_SESSION_ID": session, "CLAUDE_CONFIG_DIR": str(config)}


def test_the_crew_left_is_said_in_one_journal_line_and_under_its_result(kitchen, tmp_path, stray):
    tree, _ = ended_crew(kitchen, tmp_path)
    brief = kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + RESULT)
    stray += [orphan(tree, "yes"), orphan(tree, "yes", "two")]
    said = kitchen.poll()
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [f"left running crew alpha: stopped 2: yes in {tree}, yes two in {tree}"]
    last = brief.read_text().splitlines()[-1]
    assert last.startswith("Left running: 2 stopped by jbus ")
    assert last.endswith(f": yes in {tree}, yes two in {tree}")
    assert mirror.field(mirror.last_result(brief.read_text()), "Left") == "none"
    kitchen.poll()
    assert brief.read_text().count("Left running:") == 1


def test_the_line_waits_for_a_result_and_goes_under_it_once_written(kitchen, tmp_path, stray):
    tree, _ = ended_crew(kitchen, tmp_path)
    brief = kitchen.home / "tasks" / "alpha.md"
    was = brief.read_text()
    stray.append(orphan(tree, "yes"))
    kitchen.poll()
    assert not alive(stray[0])
    assert brief.read_text() == was
    brief.write_text(was + RESULT)
    kitchen.poll()
    assert brief.read_text().splitlines()[-1].startswith("Left running: 1 stopped by jbus ")


def test_a_worktree_removed_under_a_busy_process_still_counts(
    kitchen, tmp_path, stray, monkeypatch
):
    monkeypatch.setattr(strays, "WORKTREES", tmp_path / "worktrees")
    tree, _ = ended_crew(kitchen, tmp_path, under="worktrees/demo")
    stray.append(orphan(tree, "yes"))
    kitchen.git("worktree", "remove", "--force", str(tree))
    assert os.readlink(f"/proc/{stray[0]}/cwd").endswith(" (deleted)")
    kitchen.poll()
    assert not alive(stray[0])


def test_a_temporary_folder_the_crews_session_made_counts(kitchen, tmp_path, stray):
    tree, _ = ended_crew(kitchen, tmp_path)
    made = tmp_path / "lwr" / "c"
    made.mkdir(parents=True)
    stray.append(orphan(made, "yes", env=session_of(tmp_path, tree)))
    kitchen.poll()
    assert not alive(stray[0])


def test_a_process_outside_the_crews_folders_is_never_touched(kitchen, tmp_path, stray):
    tree, _ = ended_crew(kitchen, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    other = session_of(tmp_path, tmp_path / "another-tree")
    stray += [orphan(elsewhere, "yes"), orphan(elsewhere, "yes", env=other)]
    kitchen.poll()
    assert all(alive(pid) for pid in stray)


@pytest.mark.parametrize("name", ["t3code-server", "claude", "jbus"])
def test_a_process_of_t3_code_or_jbus_in_the_worktree_is_never_touched(
    kitchen, tmp_path, stray, name
):
    tree, _ = ended_crew(kitchen, tmp_path)
    own = tmp_path / "bin" / name
    own.parent.mkdir()
    own.symlink_to(shutil.which("yes"))
    stray.append(orphan(tree, str(own)))
    kitchen.poll()
    assert alive(stray[0])


def test_a_process_with_a_live_parent_is_never_touched(kitchen, tmp_path, stray):
    tree, _ = ended_crew(kitchen, tmp_path)
    child = subprocess.Popen(["yes"], cwd=tree, stdout=subprocess.DEVNULL)
    try:
        kitchen.poll()
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


def test_a_process_of_a_crew_still_at_work_or_one_that_uses_no_cpu_is_left(
    kitchen, tmp_path, stray
):
    tree, thread = ended_crew(kitchen, tmp_path)
    stray += [orphan(tree, "yes"), orphan(tree, "sleep", "300")]
    thread["status"] = "running"
    kitchen.poll()
    assert all(alive(pid) for pid in stray)
    thread["status"] = "completed"
    kitchen.poll()
    assert [alive(pid) for pid in stray] == [False, True]


def test_a_scout_stops_only_what_its_own_session_started(kitchen, tmp_path, stray):
    kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=2), title="scout: alpha")
    (kitchen.home / "scouts" / "alpha.md").write_text("# alpha\n\n## Report\nFound it.\n")
    made = tmp_path / "f4"
    made.mkdir()
    asked = "<command-message>scout</command-message>\n<command-name>/scout</command-name>\n"
    scouts = session_of(
        tmp_path, kitchen.checkout, "the-scout", f"{asked}<command-args>alpha</command-args>"
    )
    homes = session_of(tmp_path, kitchen.checkout, "the-home", "/home")
    stray += [orphan(made, "yes", env=scouts), orphan(kitchen.checkout, "yes", env=homes)]
    stray.append(orphan(kitchen.checkout, "yes"))
    kitchen.poll()
    assert [alive(pid) for pid in stray] == [False, True, True]
    report = (kitchen.home / "scouts" / "alpha.md").read_text()
    assert report.splitlines()[-1].startswith("Left running: 1 stopped by jbus ")


def test_the_line_goes_under_the_last_result_and_not_into_a_review_after_it(
    kitchen, tmp_path, stray
):
    tree, _ = ended_crew(kitchen, tmp_path)
    brief = kitchen.home / "tasks" / "alpha.md"
    review = "\n## Review\nBy: a reviewer #1\nVerdict: clean\nHead: abc\n"
    brief.write_text(brief.read_text() + RESULT + review)
    stray.append(orphan(tree, "yes"))
    kitchen.poll()
    text = brief.read_text()
    assert text.endswith(review)
    assert "Left running: 1 stopped by jbus " in mirror.last_result(text)


def test_a_process_that_ignores_term_is_killed_after_the_grace(
    kitchen, tmp_path, stray, monkeypatch
):
    monkeypatch.setattr(strays, "GRACE", 0.5)
    tree, _ = ended_crew(kitchen, tmp_path)
    stray.append(orphan(tree, "sh", "-c", "trap '' TERM; while :; do :; done"))
    kitchen.poll()
    assert not alive(stray[0])
