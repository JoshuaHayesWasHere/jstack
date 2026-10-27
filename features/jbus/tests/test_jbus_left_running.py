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
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import pytest

from jbriefs import parse as briefs
from jbus import mirror, queue, strays
from test_jbus_kitchen import NOW, RESULT, Kitchen
from test_jbus_queue import add

NO_ENVIRONMENT = pytest.mark.skipif(
    not strays.ROOT.is_dir(),
    reason="with no /proc, as on macOS, strays reads no environment, since ps -E showed none for"
    " the user's own processes on the macOS job: a temporary folder ties no process to a task",
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def orphan(cwd, *command, env=None):
    """Start `command` in `cwd` from a shell that exits at once, as a crew's shell does at the
    end of its turn, so the process's parent is a reaper: 1, or the user's `systemd --user`
    under a unit of it. Return its pid."""
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
        if (ppid := parent(pid)) is not None and strays.reaper(ppid):
            return pid
        time.sleep(0.02)
    raise AssertionError(f"{pid} was not handed to a reaper, so it is no orphan of this machine")


def parent(pid):
    """The process's parent, as `ps` says, which reads it on Linux and on macOS alike."""
    said = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True)
    return int(said.stdout) if said.stdout.strip().isdecimal() else None


def alive(pid):
    """Whether the process runs: a zombie that its reaper has not reaped yet has stopped."""
    said = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return said.stdout.strip()[:1] not in ("", "Z")


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


@pytest.fixture(params=["tmp", "slot"])
def temp(request, kitchen, monkeypatch):
    """A folder a crew's session made in a temporary root that the test names, not the TMPDIR
    it runs with: one under /tmp, or one under a slot's own folder of a `JGAUGE_LOCKS_DIR` the
    test sets, as `jgauge test-slot` gives a command in TMPDIR. That one is outside /tmp and
    /var/tmp, so the slot counts by itself, with or without a slot round the test: in /dev/shm,
    or where there is none, as on macOS, in the system's own temporary folder (/var/folders)."""
    where = "/tmp"
    if request.param == "slot":
        where = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
        if any(strays.under(where, one) for one in strays.TEMP):
            pytest.skip(f"no folder outside /tmp and /var/tmp for the slot's root: {where}")
    root = Path(tempfile.mkdtemp(dir=where))
    made = root / "c"
    if request.param == "slot":
        monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(root / "locks"))
        made = root / "locks" / "test-slot-short.0.tmp" / "c"
    made.mkdir(parents=True)
    yield made
    shutil.rmtree(root, ignore_errors=True)


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
    stray += [orphan(tree, "yes"), orphan(tree, "cat", "/dev/zero")]
    said = kitchen.poll()
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [f"left running crew alpha: stopped 2: yes in {tree}, cat /dev/zero in {tree}"]
    last = brief.read_text().splitlines()[-1]
    assert last.startswith("Left running: 2 stopped by jbus ")
    assert last.endswith(f": yes in {tree}, cat /dev/zero in {tree}")
    assert briefs.line(mirror.last_result(brief.read_text()), "Left:") == "none"
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
    if os.path.isdir("/proc"):
        assert os.readlink(f"/proc/{stray[0]}/cwd").endswith(" (deleted)")
    kitchen.poll()
    assert not alive(stray[0])


@pytest.mark.skipif(
    sys.platform == "darwin", reason="macOS's ps shows no process's environment, so no session"
)
@pytest.mark.parametrize("removed", [False, True])
def test_a_temporary_folder_the_crews_session_made_counts(kitchen, tmp_path, stray, temp, removed):
    tree, _ = ended_crew(kitchen, tmp_path)
    stray.append(orphan(temp, "yes", env=session_of(tmp_path, tree)))
    if removed:
        shutil.rmtree(temp)
        assert os.readlink(f"/proc/{stray[0]}/cwd").endswith(" (deleted)")
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


def test_a_process_of_a_crew_still_in_its_turn_is_left_and_stopped_once_the_turn_ended(
    kitchen, tmp_path, stray
):
    tree, thread = ended_crew(kitchen, tmp_path)
    stray += [orphan(tree, "yes"), orphan(tree, "sleep", "300")]
    thread["status"] = "running"
    kitchen.poll()
    assert all(alive(pid) for pid in stray)
    thread["status"] = "completed"
    kitchen.poll()
    assert [alive(pid) for pid in stray] == [False, False]


@pytest.mark.skipif(
    sys.platform == "darwin", reason="macOS's ps shows no process's environment, so no session"
)
def test_a_scout_stops_only_what_its_own_session_started(kitchen, tmp_path, stray, temp):
    kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=2), title="scout: alpha")
    (kitchen.home / "scouts" / "alpha.md").write_text("# alpha\n\n## Report\nFound it.\n")
    asked = "<command-message>scout</command-message>\n<command-name>/scout</command-name>\n"
    scouts = session_of(
        tmp_path, kitchen.checkout, "the-scout", f"{asked}<command-args>alpha</command-args>"
    )
    homes = session_of(tmp_path, kitchen.checkout, "the-home", "/home")
    stray += [orphan(temp, "yes", env=scouts), orphan(kitchen.checkout, "yes", env=homes)]
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


def test_a_process_the_users_systemd_adopted_is_an_orphan_and_one_under_a_live_parent_is_not(
    tmp_path, monkeypatch
):
    """Under a unit of the user's `systemd --user`, as jbus and jmerge's fresh check run, an
    orphan is handed to that manager and not to 1."""
    uid = os.getuid()

    def proc(pid, ppid, cgroup):
        where = tmp_path / str(pid)
        where.mkdir()
        (where / "stat").write_text(f"{pid} (yes) R {ppid}" + " 0" * 40 + "\n")
        (where / "cmdline").write_bytes(b"yes\0")
        (where / "environ").write_bytes(b"")
        (where / "cgroup").write_text(
            f"0::/user.slice/user-{uid}.slice/user@{uid}.service/{cgroup}\n"
        )
        (where / "cwd").symlink_to(tmp_path)

    proc(904, 1, "init.scope")
    proc(5000, 1, "app.slice/a.service")
    proc(5001, 904, "app.slice/b.service")
    proc(5002, 5000, "app.slice/a.service")
    monkeypatch.setattr(strays, "ROOT", tmp_path)
    found = {one.pid for one in strays.orphans()}
    assert {5000, 5001} <= found
    assert 5002 not in found


def test_a_process_that_ignores_term_is_killed_after_the_grace(
    kitchen, tmp_path, stray, monkeypatch
):
    monkeypatch.setattr(strays, "GRACE", 0.5)
    tree, _ = ended_crew(kitchen, tmp_path)
    stray.append(orphan(tree, "sh", "-c", "trap '' TERM; while :; do :; done"))
    kitchen.poll()
    assert not alive(stray[0])


def test_with_no_proc_to_read_as_on_a_mac_a_busy_stray_is_still_stopped(
    kitchen, tmp_path, stray, monkeypatch
):
    """macOS has no /proc, and there `ps` and `lsof` say what a process is. A missing `ROOT`
    stands in for it here. The process names its worktree, since this machine may have no `lsof`
    to give its working directory, and the gap is over a second, since Linux's `ps` gives CPU
    time in whole seconds."""
    monkeypatch.setattr(strays, "ROOT", tmp_path / "no-proc")
    monkeypatch.setattr(strays, "GAP", 1.5)
    tree, _ = ended_crew(kitchen, tmp_path)
    stray.append(orphan(tree, "yes", str(tree)))
    kitchen.poll()
    assert not alive(stray[0])


def end(kitchen, tree, how):
    """End the crew's row: its pull request merged and its thread settled, its thread ended
    with a Result, or its worktree removed with no Result written. Run the pass that derives
    the row's status, which `strays.stop` reads in the pass after, and return what it said."""
    brief = kitchen.home / "tasks" / "alpha.md"
    if how == "merged":
        brief.write_text(brief.read_text() + RESULT)
        kitchen.t3.threads[-1]["settled"] = True
        kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    elif how == "done":
        brief.write_text(brief.read_text() + RESULT)
    else:
        kitchen.git("worktree", "remove", "--force", str(tree))
    return kitchen.poll()


@pytest.mark.parametrize("how", ["merged", "done", "removed"])
def test_an_idle_process_a_crew_left_in_its_worktree_is_stopped_once_its_row_ended(
    kitchen, tmp_path, stray, monkeypatch, how
):
    monkeypatch.setattr(strays, "WORKTREES", tmp_path / "worktrees")
    tree, _ = ended_crew(kitchen, tmp_path, under="worktrees/demo")
    stray.append(orphan(tree, "sleep", "300"))
    said = end(kitchen, tree, how) + kitchen.poll()
    assert not alive(stray[0])
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [f"left running crew alpha: stopped 1: sleep 300 in {tree}"]
    if how != "removed":
        last = (kitchen.home / "tasks" / "alpha.md").read_text().splitlines()[-1]
        assert last.startswith("Left running: 1 stopped by jbus ")


@NO_ENVIRONMENT
@pytest.mark.parametrize("how", ["merged", "done", "removed"])
def test_an_idle_process_a_crew_left_is_stopped_once_its_row_ended(
    kitchen, tmp_path, stray, monkeypatch, temp, how
):
    monkeypatch.setattr(strays, "WORKTREES", tmp_path / "worktrees")
    tree, _ = ended_crew(kitchen, tmp_path, under="worktrees/demo")
    stray.append(orphan(tree, "sleep", "300"))
    stray.append(orphan(temp, "sleep", "301", env=session_of(tmp_path, tree)))
    said = end(kitchen, tree, how) + kitchen.poll()
    assert [alive(pid) for pid in stray] == [False, False]
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [
        f"left running crew alpha: stopped 2: sleep 300 in {tree}, sleep 301 in {temp}"
    ]
    if how != "removed":
        last = (kitchen.home / "tasks" / "alpha.md").read_text().splitlines()[-1]
        assert last.startswith("Left running: 2 stopped by jbus ")


def test_an_idle_process_of_an_ended_row_whose_crew_is_at_work_again_is_left(
    kitchen, tmp_path, stray
):
    tree, thread = ended_crew(kitchen, tmp_path)
    end(kitchen, tree, "done")
    thread.update({"status": "running", "settled": False})
    stray.append(orphan(tree, "sleep", "300"))
    kitchen.poll()
    assert alive(stray[0])
    thread["status"] = "completed"
    kitchen.poll()
    kitchen.poll()
    assert not alive(stray[0])


def test_an_idle_process_with_a_live_parent_is_never_touched(kitchen, tmp_path, monkeypatch):
    tree, _, _ = at_its_pull_request(kitchen, tmp_path, monkeypatch)
    child = subprocess.Popen(["sleep", "300"], cwd=tree)
    try:
        kitchen.poll()
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


@pytest.mark.parametrize("name", ["t3code-server", "claude", "jbus"])
def test_an_idle_process_of_t3_code_or_jbus_in_a_crews_worktree_is_never_touched(
    kitchen, tmp_path, stray, monkeypatch, name
):
    tree, _, _ = at_its_pull_request(kitchen, tmp_path, monkeypatch)
    own = tmp_path / "bin" / name
    own.parent.mkdir()
    own.symlink_to(shutil.which("sleep"))
    stray.append(orphan(tree, str(own), "300"))
    kitchen.poll()
    assert alive(stray[0])


def test_the_homes_idle_processes_are_left_when_a_crews_turn_ended(
    kitchen, tmp_path, stray, monkeypatch, temp
):
    at_its_pull_request(kitchen, tmp_path, monkeypatch)
    homes = session_of(tmp_path, kitchen.checkout, "the-home", "/home")
    stray.append(orphan(kitchen.checkout, "sleep", "300", env=homes))
    stray.append(orphan(temp, "sleep", "301", env=homes))
    stray.append(orphan(kitchen.checkout, "sleep", "302"))
    kitchen.poll()
    assert all(alive(pid) for pid in stray)


def at_its_pull_request(kitchen, tmp_path, monkeypatch):
    """A crew whose turn ended with its pull request open and its Result written: its row stays
    at `pr` while the pull request waits on review, a red main or the base it merges after."""
    monkeypatch.setattr(strays, "WORKTREES", tmp_path / "worktrees")
    tree, thread = ended_crew(kitchen, tmp_path, under="worktrees/demo")
    brief = kitchen.home / "tasks" / "alpha.md"
    url = "https://example.test/pull/7"
    brief.write_text(brief.read_text() + RESULT.replace("Pull request: none", url))
    kitchen.set("open.json", [kitchen.opened("alpha", 7, state=None)])
    return tree, thread, brief


def test_an_idle_process_a_crew_left_in_its_worktree_is_stopped_at_its_pull_request(
    kitchen, tmp_path, stray, monkeypatch
):
    tree, _, brief = at_its_pull_request(kitchen, tmp_path, monkeypatch)
    stray.append(orphan(tree, "sleep", "300"))
    said = kitchen.poll() + kitchen.poll()
    assert {row["slug"]: row["status"] for row in queue.load(kitchen.state)} == {"alpha": "pr"}
    assert not alive(stray[0])
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [f"left running crew alpha: stopped 1: sleep 300 in {tree}"]
    assert brief.read_text().splitlines()[-1].startswith("Left running: 1 stopped by jbus ")


@NO_ENVIRONMENT
def test_an_idle_process_a_crew_left_is_stopped_once_its_turn_ended_at_its_pull_request(
    kitchen, tmp_path, stray, monkeypatch, temp
):
    tree, _, brief = at_its_pull_request(kitchen, tmp_path, monkeypatch)
    stray.append(orphan(tree, "sleep", "300"))
    stray.append(orphan(temp, "sleep", "301", env=session_of(tmp_path, tree)))
    said = kitchen.poll() + kitchen.poll()
    assert {row["slug"]: row["status"] for row in queue.load(kitchen.state)} == {"alpha": "pr"}
    assert [alive(pid) for pid in stray] == [False, False]
    lines = [one for one in said if one.startswith("left running")]
    assert lines == [
        f"left running crew alpha: stopped 2: sleep 300 in {tree}, sleep 301 in {temp}"
    ]
    assert brief.read_text().splitlines()[-1].startswith("Left running: 2 stopped by jbus ")


def test_a_check_the_crew_left_under_a_test_slot_is_left_while_it_runs(
    kitchen, tmp_path, stray, monkeypatch
):
    """The crew's check block starts its check with `setsid sh -c`, which holds a test slot
    through `jgauge test-slot` and outlives the shell that started it."""
    tree, _, _ = at_its_pull_request(kitchen, tmp_path, monkeypatch)
    env = {**os.environ, "JGAUGE_LOCKS_DIR": str(tmp_path / "locks")}
    slot = [sys.executable, "-m", "jgauge", "test-slot", "--short", "--", "sleep", "300"]
    check = orphan(tree, "sh", "-c", '"$@"; echo $? > exit', "check", *slot, env=env)
    stray.append(check)
    for _ in range(100):
        if any(strays.SLOT.search(one.name) for one in (tmp_path / "locks").glob("*")):
            break
        time.sleep(0.05)
    time.sleep(0.3)
    started = tree_of(check)
    try:
        kitchen.poll()
        assert alive(check)
    finally:
        for pid in reversed(started):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def tree_of(pid):
    """The process and every process under it, each parent before its children."""
    said = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True)
    parents = {}
    for line in said.stdout.splitlines():
        one, ppid = map(int, line.split())
        parents.setdefault(ppid, []).append(one)
    found = [pid]
    for one in found:
        found += parents.get(one, [])
    return found


def test_with_no_proc_to_read_a_slot_held_under_a_process_is_found_by_ps_and_lsof(
    tmp_path, monkeypatch
):
    """macOS has no /proc: `ps` says which process is under which and `lsof` the files each
    holds open. Both are stood in for here, since this machine may have no `lsof`; the check
    above runs them for real on the macOS job."""
    monkeypatch.setattr(strays, "ROOT", tmp_path / "no-proc")
    at = "Mon Oct 26 01:00:00 2026"
    said = {
        "ps": f"10 1 501 {at} 0:00.01 Ss sh -c check\n"
        f"11 10 501 {at} 0:00.20 S python -m jgauge test-slot\n"
        f"12 11 501 {at} 0:00.00 S sleep 300\n"
        f"20 1 501 {at} 0:00.00 S sleep 301\n",
        "lsof": "p10\nfcwd\nn/tmp/tree\n"
        "p11\nf3\nn/Users/me/.local/state/locks/test-slot-short.0.lock\n"
        "p12\np20\nf3\nn/tmp/other.lock\n",
    }
    monkeypatch.setattr(strays, "_run", lambda *argv: said[argv[0]])
    found = [strays.Proc(10, 1, 0, 0, ["sh"], ""), strays.Proc(20, 1, 0, 0, ["sleep"], "")]
    assert strays.in_slot(found) == {10}
