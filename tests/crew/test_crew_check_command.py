"""The crew skill's "Do the task": the check command under a test slot, waited on in the turn."""

import fcntl
import json
import os
import re
import subprocess
import time

import test_room as room
from crew.helpers import FENCED, SKILL, block, held_open, sections
from jbriefs import parse as briefs
from test_machine_sizes import fake_proc


def checked(tmp_path, command, limit=60, heading="Do the task", then=None):
    """The check block of "Do the task" run once in a worktree of its own, as an agent runs
    it, waiting `limit` seconds at most: what it printed, its exit code and how long it took.
    `then` is called once the block has printed its first line, while it still waits."""
    repo, home, stub = tmp_path / "repo", tmp_path / "home", tmp_path / "stub"
    if not repo.exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "file").write_text("one\n")
        stub.mkdir(exist_ok=True)
        room.uv(stub)
    script = block(heading, "<check command>").replace("<check command>", command)
    script = script.replace("limit=540", f"limit={limit}").replace("<thread id>", "mcp:thread-1")
    began = time.monotonic()
    ran = subprocess.Popen(
        ["sh", "-c", script],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "TEST_SLOTS": "3",
            "PATH": f"{stub}:{room.BIN}:{os.environ['PATH']}",
            "T": str(SKILL.parent.parent.parent / "templates"),
        },
    )
    first = ran.stdout.readline()
    if then:
        then()
    rest, _ = ran.communicate()
    return (first + rest).splitlines(), ran.returncode, time.monotonic() - began


def test_the_full_run_of_the_check_command_holds_a_test_slot_and_ends_with_its_exit_code(
    tmp_path,
):
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    held = f"! flock -n {locks}/test-slot.1.lock true && echo held; exit 3"
    said, code, _ = checked(tmp_path, held)
    assert (said[0].split(":")[0], said[-2:], code) == (
        "started",
        ["held", "done: the check exited 3"],
        3,
    )
    assert [path.name for path in locks.iterdir()] == ["test-slot.1.lock"]


def test_the_one_check_is_the_command_the_notes_name_and_never_a_full_make_check(tmp_path):
    """The block runs what the repo's notes name, `make check-fast BASE=origin/main` on the
    fast track, under a test slot, and nothing else: a `make` on the path records each run."""
    notes = "- Check command: `make check-fast BASE=origin/main`, while the fast track holds.\n"
    command = briefs.check_command(notes)
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    ran = tmp_path / "make.log"
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "make").write_text(
        f"#!/bin/sh\nheld=free\n! flock -n {locks}/test-slot.1.lock true && held=held\n"
        f'echo "$* $held" >> {ran}\n'
    )
    (stub / "make").chmod(0o755)
    said, code, _ = checked(tmp_path, command)
    assert (said[-1], code) == ("done: the check exited 0", 0)
    assert ran.read_text().splitlines() == ["check-fast BASE=origin/main held"]
    step = sections()["Do the task"]
    assert "(`notes.md` names it)" in step
    assert not re.search(r"make check(?![-\w])", step)


def ended(tmp_path):
    """Wait, as a turn between two calls would, for the check to end with nobody calling."""
    found = tmp_path / "repo" / ".git" / "crew-check" / "exit"
    for _ in range(600):
        if found.exists():
            return
        time.sleep(0.1)
    raise AssertionError("the check did not end")


def test_the_check_is_waited_on_in_the_turn_and_never_started_twice(tmp_path):
    """A check longer than one call: each call waits its whole limit and says to call again,
    a second call joins the check the first started, and the last one has its exit code."""
    runs, go = tmp_path / "runs", tmp_path / "go"
    command = f"echo ran >> {runs}; {held_open(go)}; echo all passed"

    said, code, took = checked(tmp_path, command, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    assert "never end your turn while it runs" in said[-1]
    assert took >= 1

    said, code, took = checked(tmp_path, command, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0]) == ("joined", "running")
    assert took >= 1

    go.touch()
    said, code, took = checked(tmp_path, command, limit=30)
    assert (said[-2:], code) == (["all passed", "done: the check exited 0"], 0)
    assert took < 30
    assert runs.read_text() == "ran\n"


def test_a_check_that_ended_between_calls_is_told_once_and_then_runs_afresh(tmp_path):
    """The answer of a check that ended with no call waiting is given once: a failure that
    was a flake is run again by calling again, with nothing in the worktree changed."""
    runs = tmp_path / "runs"
    command = f"echo ran >> {runs}; sleep 1; [ $(wc -l < {runs}) -gt 1 ]"

    said, code, _ = checked(tmp_path, command, limit=0)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    ended(tmp_path)

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("checked", "done: the check exited 1", 1)
    assert runs.read_text() == "ran\n"

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("started", "done: the check exited 0", 0)
    assert runs.read_text() == "ran\nran\n"


def test_a_check_of_files_that_changed_while_it_ran_is_no_proof_and_runs_again(tmp_path):
    runs, go = tmp_path / "runs", tmp_path / "go"
    command = f"echo ran >> {runs}; {held_open(go)}"

    said, code, _ = checked(tmp_path, command, limit=0)
    assert said[-1].split(":")[0] == "running"
    (tmp_path / "repo" / "file").write_text("two\n")

    said, code, _ = checked(tmp_path, command, then=go.touch)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("joined", "stale", 75)
    assert "done" not in [line.split(":")[0] for line in said]

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("started", "done: the check exited 0", 0)
    assert runs.read_text() == "ran\nran\n"


def slot_script(text, home):
    return subprocess.run(
        ["sh", "-c", text.replace("<thread id>", "mcp:thread-1")],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "HOME": str(home),
            "TEST_SLOTS": "3",
            "PATH": f"{home.parent / 'stub'}:{room.BIN}:{os.environ['PATH']}",
            "T": str(SKILL.parent.parent.parent / "templates"),
        },
    )


def test_no_block_of_do_the_task_asks_whose_the_full_run_is(tmp_path):
    """The full run is the crewmate's: the block that read the brief and the notes has gone.
    The two blocks that take a slot each run their command, with a slot free."""
    blocks = FENCED.findall(sections()["Do the task"])
    assert [text for text in blocks if "full run" in text.lower() or "Review:" in text] == []
    assert len([text for text in blocks if "jgauge test-slot" in text]) == 2
    said, code, _ = checked(tmp_path, "echo ran")
    assert (said[-2:], code) == (["ran", "done: the check exited 0"], 0)
    ran = slot_script(
        block("Do the task", "test-slot --short").replace("<the targeted tests>", "echo ran"),
        tmp_path / "home",
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "ran\n", "")


def test_with_every_slot_taken_the_blocks_register_the_thread_and_end_76(tmp_path, monkeypatch):
    """The thread's turn then ends with the one line, and jbus wakes it: the file has it. The
    lanes are the 4 full and 3 short slots 24 processors and 62 GiB derive, whatever
    `TEST_SLOTS` the machine sets."""
    monkeypatch.delenv("TEST_SLOTS", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    (tmp_path / "stub").mkdir()
    room.uv(tmp_path / "stub")
    home = tmp_path / "home"
    locks = home / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for lane, count in (("test-slot", 4), ("test-slot-short", 3)):
        for n in range(1, count + 1):
            fd = os.open(locks / f"{lane}.{n}.lock", os.O_RDWR | os.O_CREAT)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(fd)
    try:
        ran = slot_script(
            block("Do the task", "test-slot --short").replace("<the targeted tests>", "echo ran"),
            home,
        )
        assert (ran.returncode, ran.stderr) == (76, "")
        assert "mcp:thread-1 is registered as a waiter" in ran.stdout
        said, code, _ = checked(tmp_path, "echo ran")
        assert (said[-1].split(":")[0], code) == ("waiting", 76)
        assert "mcp:thread-1 is registered as a waiter" in "\n".join(said)
        assert not (tmp_path / "repo" / ".git" / "crew-check").exists()
    finally:
        for fd in held:
            os.close(fd)
    waiting = json.loads((locks / "test-slot-waiters.json").read_text())
    assert [(one["thread"], one["lane"]) for one in waiting] == [("mcp:thread-1", "full")]


def test_a_targeted_run_takes_the_short_lane_and_never_waits_on_a_full_suite(tmp_path):
    home, stub = tmp_path / "home", tmp_path / "stub"
    stub.mkdir()
    room.uv(stub)
    locks = home / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for n in (1, 2, 3):
        fd = os.open(locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    took = f"! flock -n {locks}/test-slot-short.1.lock true && echo short; exit 3"
    script = block("Do the task", "test-slot --short").replace(
        "<the targeted tests>", f"sh -c '{took}'"
    )
    script = script.replace("<thread id>", "mcp:thread-1")
    try:
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{stub}:{room.BIN}:{os.environ['PATH']}",
                "T": str(SKILL.parent.parent.parent / "templates"),
            },
        )
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout, ran.stderr) == (3, "short\n", "")


def test_a_failed_check_on_the_pull_request_runs_the_check_block_it_names(tmp_path):
    """The `failed` answer of "The checks" names the section whose block runs the check
    command: that block holds a test slot and ends with the command's exit code."""
    (answer,) = [
        line
        for line in sections()["Stay on the pull request"].splitlines()
        if line.startswith("- `failed`: a check ran and failed.")
    ]
    (named,) = re.findall(r'the block of "([^"]+)" that runs it', answer)
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    held = f"! flock -n {locks}/test-slot.1.lock true && echo held; exit 3"
    said, code, _ = checked(tmp_path, held, heading=named)
    assert (said[-2:], code) == (["held", "done: the check exited 3"], 3)
