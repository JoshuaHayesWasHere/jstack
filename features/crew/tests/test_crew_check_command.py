"""The crew skill's "Do the task" runs the check command under a test slot and waits for it in
the turn."""

import fcntl
import json
import os
import re
import shutil
import subprocess
import time

import pytest

import test_room as room
from crew_helpers import FENCED, block, git, held_open, sections
from jbriefs import parse as briefs
from test_machine_sizes import fake_proc
from testing.paths import REPO


def checked(tmp_path, command, limit=60, heading="Do the task", then=None):
    """Run the check block of "Do the task" once in a worktree of its own, as an agent runs it,
    waiting `limit` seconds at most. It returns what the block printed, its exit code and how
    long it took. The test calls `then` once the block has printed its first line, while the
    block still waits."""
    repo, home, stub = tmp_path / "repo", tmp_path / "home", tmp_path / "stub"
    if not repo.exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "file").write_text("one\n")
        stub.mkdir(exist_ok=True)
        room.uv(stub)
    script = block(heading, "<check command>").replace("<check command>", command)
    script = script.replace("jgauge check", f"jgauge check --wait {limit}")
    script = script.replace("<thread id>", "mcp:thread-1").replace("<slug>", "a-task")
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
            "T": str(REPO / "features" / "crew" / "templates"),
            "H": str(tmp_path / "state"),
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
    fast track, under a test slot, and nothing else. A `make` on the path records each run."""
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
    """Wait for the check to end while no call to the block is running, as happens in a turn
    between two calls."""
    found = tmp_path / "repo" / ".git" / "crew-check" / "exit"
    for _ in range(600):
        if found.exists():
            return
        time.sleep(0.1)
    raise AssertionError("the check did not end")


def test_the_check_is_waited_on_in_the_turn_and_never_started_twice(tmp_path):
    """The test runs a check that takes longer than one call. Each call waits its whole limit
    and says to call again, a second call joins the check that the first started, and the
    last call gets its exit code."""
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
    """When a check ends while no call is waiting, the block reports its answer once. The next
    call runs the check again, so a failure that was a flake gets a fresh run, with nothing
    in the worktree changed."""
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
            "T": str(REPO / "features" / "crew" / "templates"),
        },
    )


def test_no_block_of_do_the_task_asks_whose_the_full_run_is(tmp_path):
    """The full run is the crewmate's, and the block that read the brief and the notes is gone.
    The two blocks that take a slot, the targeted run and the check, each run their command when
    a slot is free."""
    blocks = FENCED.findall(sections()["Do the task"])
    assert [text for text in blocks if "full run" in text.lower() or "Review:" in text] == []
    slots = [text for text in blocks if "jgauge test-slot" in text or "jgauge check" in text]
    assert len(slots) == 2
    said, code, _ = checked(tmp_path, "echo ran")
    assert (said[-2:], code) == (["ran", "done: the check exited 0"], 0)
    ran = slot_script(
        block("Do the task", "<the targeted tests>").replace("<the targeted tests>", "echo ran"),
        tmp_path / "home",
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "ran\n", "")


def test_with_every_slot_taken_the_blocks_register_the_thread_and_end_76(tmp_path, monkeypatch):
    """When every slot is taken, the blocks register the thread in the file, and the thread's
    turn ends after the blocks print their one line. jbus wakes the thread later because the
    file lists it. The lanes are the 4 full and 3 short slots that a machine with 24
    processors and 62 GiB gets, whatever `TEST_SLOTS` the machine sets."""
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
            block("Do the task", "<the targeted tests>").replace(
                "<the targeted tests>", "echo ran"
            ),
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
    script = block("Do the task", "<the targeted tests>").replace(
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
                "T": str(REPO / "features" / "crew" / "templates"),
            },
        )
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout, ran.stderr) == (3, "short\n", "")


def test_a_failed_check_on_the_pull_request_runs_the_check_block_it_names(tmp_path):
    """The `failed` answer of "The checks" names the section whose block runs the check
    command. That block holds a test slot and ends with the command's exit code."""
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


def test_a_check_the_old_block_started_is_joined_and_not_started_twice(tmp_path):
    """Before `jgauge check`, the block wrote the check's files itself: the pid of the run, the
    tree it wrote with a copy of the index, and the exit code once the run ended. A thread that
    loaded the new step while a run of the old one still goes joins that run."""
    said, code, _ = checked(tmp_path, "echo first")
    assert (said[-1], code) == ("done: the check exited 0", 0)
    repo, go, runs = tmp_path / "repo", tmp_path / "go", tmp_path / "runs"
    folder = repo / ".git" / "crew-check"
    index = tmp_path / "old.index"
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    if (repo / ".git" / "index").exists():
        shutil.copyfile(repo / ".git" / "index", index)
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    tree = subprocess.run(
        ["git", "write-tree"], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout
    shutil.rmtree(folder)
    folder.mkdir()
    (folder / "tree").write_text(tree)
    (folder / "out").write_text("the old block's run\n")
    old = subprocess.Popen(
        ["sh", "-c", f'{held_open(go)}; echo 0 > "{folder}/exit"'], start_new_session=True
    )
    (folder / "pid").write_text(f"{old.pid}\n")
    said, code, _ = checked(tmp_path, f"echo new >> {runs}", then=go.touch)
    old.wait()
    assert said[0].startswith("joined: the check an earlier call started on this worktree")
    assert (said[-2:], code) == (["the old block's run", "done: the check exited 0"], 0)
    assert not runs.exists()


def lanes(stub, locks, log):
    """A `make` on the path that records its arguments, and which lane's slot was held while it
    ran: `short` when the first slot of the short lane was, `full` when any of the full lane's
    were."""
    (stub / "make").write_text(
        "#!/bin/sh\nshort=free\nfull=free\n"
        f"! flock -n {locks}/test-slot-short.1.lock true && short=held\n"
        f'for one in {locks}/test-slot.*.lock; do [ -e "$one" ] && ! flock -n "$one" true '
        "&& full=held; done\n"
        f'echo "$* short=$short full=$full" >> {log}\n'
    )
    (stub / "make").chmod(0o755)


def selected(tmp_path, repo, on="origin/main"):
    """Run the check block once in `repo`, a worktree whose `origin/main` the test has set, with
    a `make` that records each run. It returns what the block printed, its exit code, the
    runs of `make` and the commit the branch left `origin/main` at."""
    stub, locks, log = (
        tmp_path / "stub",
        tmp_path / "home" / ".local" / "state" / "locks",
        tmp_path / "make.log",
    )
    stub.mkdir()
    room.uv(stub)
    lanes(stub, locks, log)
    said, code, _ = checked(tmp_path, "echo the full lane")
    base = subprocess.run(
        ["git", "merge-base", on, "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    waiting = locks / "test-slot-waiters.json"
    assert not waiting.exists() or json.loads(waiting.read_text()) == []
    return said, code, log.read_text().splitlines() if log.exists() else [], base


def stubbed(tmp_path, selector):
    """A repo whose `scripts/select_tests.py` is `selector`, with `origin/main` at its first
    commit and a doc changed on the branch above it."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "select_tests.py").write_text(selector + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the selector")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / "page.md").write_text("A page.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a doc")
    return repo


def test_a_change_to_one_feature_runs_only_that_features_tests_in_a_short_slot(tmp_path):
    """In jstack, the check of a change is the tests `scripts/select_tests.py` selects for it,
    in the short lane, and never the whole suite under a full slot: CI's check is the gate."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(repo)], check=True)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with (repo / "features" / "crew" / "the-checks.md").open("a") as page:
        page.write("\nA line the test adds.\n")
    git(repo, "commit", "-qam", "a change to the crew feature")
    said, code, ran, base = selected(tmp_path, repo)
    chosen = subprocess.run(
        ["python3", "scripts/select_tests.py", base, "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "all" not in chosen
    assert "features/crew/tests/test_crew_checks.py" in chosen
    assert said[0] == f"selected: {len(chosen)} test files, in the short lane:"
    assert said[1 : 1 + len(chosen)] == chosen
    assert "the full lane" not in said
    assert (ran, code) == ([f"check-fast BASE={base} short=held full=free"], 0)


@pytest.mark.parametrize(
    ("selection", "first"),
    [
        ("", "selected: none, no test covers this change: lint only"),
        ("all", "selected: all, the whole suite: lint only here, and CI's check runs every test"),
    ],
)
def test_a_selection_of_no_test_or_of_every_test_runs_only_the_lint(tmp_path, selection, first):
    """A change no test covers, a doc only, still gets the lint, and a change every test covers
    gets only the lint here: `PYTEST=:` stops `make check-fast` before any test."""
    repo = stubbed(tmp_path, f"print({selection!r})")
    said, code, ran, base = selected(tmp_path, repo)
    assert (said, code) == ([first], 0)
    assert ran == [f"check-fast BASE={base} PYTEST=: short=held full=free"]


def test_a_selector_that_fails_is_no_check_and_ends_the_block_1(tmp_path):
    repo = stubbed(tmp_path, "import sys; sys.exit('the selector broke')")
    said, code, ran, _ = selected(tmp_path, repo)
    assert (said, code, ran) == (
        ["no check: scripts/select_tests.py could not select the tests"],
        1,
        [],
    )


def test_a_stacked_link_selects_only_its_own_change_from_the_branch_it_is_stacked_on(tmp_path):
    """A link stacked on another pull request's branch is checked from where it left that
    branch, as its pull request is based on it, and not from `origin/main`, which would select
    the change of every link under it too."""
    repo = stubbed(tmp_path, "print('all')")
    git(repo, "update-ref", "refs/remotes/origin/below", "HEAD")
    (repo / "mine.md").write_text("This link's own page.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "this link")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo, on="origin/below")
    assert base == git(repo, "rev-parse", "HEAD~1")
    assert (ran, code) == ([f"check-fast BASE={base} PYTEST=: short=held full=free"], 0)


def test_a_link_whose_base_branch_is_gone_selects_from_origin_main(tmp_path):
    """A link's base branch is deleted once it merges, before jbus rewrites the brief's
    `Stacked on:` line, and the link is then checked from `origin/main`, which holds it."""
    repo = stubbed(tmp_path, "print('all')")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo)
    assert (ran, code) == ([f"check-fast BASE={base} PYTEST=: short=held full=free"], 0)
