"""The crew skill's "Do the task" runs the check command under a test slot and waits for it in
the turn."""

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time

import pytest

import test_room as room
from crew_helpers import block, git, held_open, sections
from jbriefs import parse as briefs
from jmerge import ready
from test_machine_sizes import fake_proc
from test_portable_shell import bsd_tools
from testing.layouts import assembled
from testing.paths import REPO

TAKEN = """import fcntl, sys

with open(sys.argv[1], "a") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
sys.exit(1)
"""


def checked(tmp_path, command, limit=60, heading="Do the task", then=None, tools=None):
    """Run the check block of "Do the task" once in a worktree of its own, as an agent runs it,
    waiting `limit` seconds at most. It returns what the block printed, its exit code and how
    long it took. The test calls `then` once the block has printed its first line, while the
    block still waits. `tools` is the PATH the block finds its tools on, the machine's own by
    default."""
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
            "PATH": f"{stub}:{room.BIN}:{tools or os.environ['PATH']}",
            "T": str(assembled() / "templates"),
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
    assert sorted(path.name for path in locks.iterdir()) == [
        "test-slot-holders.json",
        "test-slot-holders.lock",
        "test-slot.1.lock",
    ]


def test_the_one_check_is_the_command_fresh_check_names_and_never_a_full_make_check(tmp_path):
    """The block runs what the repo's fresh-check names, `make check-fast BASE=origin/main` with
    the slot it takes left off, under a test slot, and nothing else. A `make` on the path records
    each run."""
    check = "jgauge test-slot -- make check-fast BASE=origin/main\n"
    command = briefs.check_command(check)
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
    assert "`$H/fresh-check`" in step
    assert not re.search(r"make check(?![-\w])", step)


def test_the_check_starts_and_ends_on_the_tools_of_macos(tmp_path):
    """macOS has no `setsid` and refuses GNU's flags. With only such tools on PATH, the block
    still starts the check on its own and waits on it to the end."""
    tools = bsd_tools(tmp_path / "bsd")
    said, code, _ = checked(tmp_path, "echo all passed", tools=tools)
    assert (said[0].split(":")[0], said[-2:], code) == (
        "started",
        ["all passed", "done: the check exited 0"],
        0,
    )


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
            "T": str(assembled() / "templates"),
        },
    )


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
    assert [one["command"] for one in waiting] == [["jgauge", "check"]], (
        "jbus's wake names what the thread runs again: the check block's `jgauge check`, and"
        " not the run file the check removed when it found no slot"
    )


def test_a_targeted_run_takes_the_short_lane_and_never_waits_on_a_full_suite(tmp_path):
    """The command asks whether its short slot is held with `TAKEN`, by Python's fcntl, which a
    Mac has too: util-linux's `flock` command is Linux only."""
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
    taken = tmp_path / "taken.py"
    taken.write_text(TAKEN)
    took = f"{sys.executable} {taken} {locks}/test-slot-short.1.lock && echo short; exit 3"
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
                "T": str(assembled() / "templates"),
            },
        )
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout, ran.stderr) == (3, "short\n", "")


def test_a_failed_check_on_the_pull_request_runs_the_check_block_it_names(tmp_path):
    """The `failed` answer of "The checks" names the section whose block runs the check
    command. That block holds a test slot and ends with the command's exit code."""
    (answer,) = re.findall(
        r"^- `failed`: a check ran and failed\..*(?:\n  .*)*",
        sections()["Stay on the pull request"],
        re.M,
    )
    (named,) = re.findall(r'the block of "([^"]+)" that runs it', answer)
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    held = f"! flock -n {locks}/test-slot.1.lock true && echo held; exit 3"
    said, code, _ = checked(tmp_path, held, heading=named)
    assert (said[-2:], code) == (["held", "done: the check exited 3"], 3)


def lanes(stub, locks, log, exits=None):
    """A `make` on the path that records its arguments, and which lane's slot was held while it
    ran: `short` when any slot of the short lane was, `full` when any of the full lane's were. It
    asks with `TAKEN`, by Python's fcntl, since macOS has no `flock` command. It ends with the
    code of the first of `exits` whose shell pattern matches what it records, and 0 by default."""
    ends = "".join(
        f"{pattern.replace(' ', chr(92) + ' ')}) exit {code} ;; "
        for pattern, code in (exits or {}).items()
    )
    taken = stub / "taken.py"
    taken.write_text(TAKEN)
    held = f"{shlex.quote(sys.executable)} {shlex.quote(str(taken))}"
    (stub / "make").write_text(
        "#!/bin/sh\nshort=free\nfull=free\n"
        f'for one in {locks}/test-slot-short.*.lock; do [ -e "$one" ] && {held} "$one" '
        "&& short=held; done\n"
        f'for one in {locks}/test-slot.*.lock; do [ -e "$one" ] && {held} "$one" '
        "&& full=held; done\n"
        'said="$* short=$short full=$full"\n'
        f'echo "$said" >> {log}\n'
        f'case "$said" in {ends}esac\n'
    )
    (stub / "make").chmod(0o755)


def selected(tmp_path, repo, on="origin/main", exits=None):
    """Run the check block once in `repo`, a worktree whose `origin/main` the test has set, with
    a `make` that records each run. It returns what the block printed, its exit code, the runs of
    `make` and the commit the branch left `origin/main` at."""
    stub, locks, log = (
        tmp_path / "stub",
        tmp_path / "home" / ".local" / "state" / "locks",
        tmp_path / "make.log",
    )
    stub.mkdir(exist_ok=True)
    room.uv(stub)
    lanes(stub, locks, log, exits)
    said, code, _ = checked(tmp_path, "echo the full lane")
    base = subprocess.run(
        ["git", "merge-base", on, "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    ran = log.read_text().splitlines() if log.exists() else []
    log.unlink(missing_ok=True)
    return said, code, ran, base


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


def touching(*files):
    """A selector that prints `files` for `--part touched`, and fails on any other ask."""
    return "import sys\nassert sys.argv[1:3] == ['--part', 'touched'], sys.argv\n" + "".join(
        f"print({one!r})\n" for one in files
    )


def lint(base, lane="short=held full=free"):
    return f"check-fast BASE={base} PYTEST=: PART=touched {lane}"


def alone(test, lane="short=held full=free"):
    return f"test TESTS={test} {lane}"


def a_brief(tmp_path):
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    brief = tasks / "a-task.md"
    brief.write_text("# a-task: a task\n\n## Result\n")
    return brief


def test_a_change_runs_the_lint_and_each_touched_test_alone_in_the_short_lane(tmp_path):
    """In jstack, the desk's check is the lint and the test files the change touches, each its
    own call of the short lane, and never the selection: CI's check is the check of record and
    runs the rest. The real selector names the touched tests: a test file the branch edits, and
    not the crew tests the edited doc reaches, nor the cross-cutting tests."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(repo)], check=True)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with (repo / "features" / "crew" / "the-checks.md").open("a") as page:
        page.write("\nA line the test adds.\n")
    mine = "features/crew/tests/test_crew_label.py"
    with (repo / mine).open("a") as test:
        test.write("\n# A line the test adds.\n")
    git(repo, "commit", "-qam", "a change to the crew feature")
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    assert said[0].startswith("touched: 1 test files, each alone in the short lane"), said
    assert re.fullmatch(r"lint: exit 0 in \d+ s, short lane", said[1]), said
    assert re.fullmatch(rf"{mine}: exit 0 in \d+ s, short lane", said[2]), said
    assert (ran, code) == ([lint(base), alone(mine)], 0)
    head = git(repo, "rev-parse", "HEAD")
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


def test_a_step_the_short_lane_stops_runs_again_alone_in_a_full_slot_and_passes(tmp_path):
    """Josh, 2026-11-05: the check must not time out. A test file the short lane stops at its
    limit, as a loaded machine makes it, ends 124 there: that is no verdict, so the block runs
    that file again alone in a full slot, which has no limit, and its verdict there is the
    step's. The other steps stay in the short lane."""
    repo = stubbed(tmp_path, touching("tests/test_slow.py", "tests/test_quick.py"))
    brief = a_brief(tmp_path)
    slow = "*test_slow.py short=held*"
    said, code, ran, base = selected(tmp_path, repo, exits={slow: 124})
    head = git(repo, "rev-parse", "HEAD")
    assert ran == [
        lint(base),
        alone("tests/test_slow.py"),
        alone("tests/test_slow.py", "short=free full=held"),
        alone("tests/test_quick.py"),
    ]
    assert re.search(r"^tests/test_slow.py: exit 0 in \d+ s, full lane$", "\n".join(said), re.M)
    assert code == 0
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


@pytest.mark.parametrize(
    ("exits", "code", "last"),
    [
        pytest.param({"*test_slow.py*": 124}, 124, "test_quick", id="a 124 in the full slot too"),
        pytest.param(
            {"*test_slow.py short=held*": 124, "*test_slow.py*": 1},
            1,
            "test_slow",
            id="a fail in the full slot",
        ),
        pytest.param(
            {"*test_slow.py*": 124, "*test_quick.py*": 2}, 2, "test_quick", id="a 124 then a fail"
        ),
    ],
)
def test_a_124_is_never_a_pass_and_never_a_failure(tmp_path, exits, code, last):
    """A step that ends 124 even alone in a full slot reached no verdict: the block goes on to
    the next step and ends 124, which jmerge holds as no pass. A failure anywhere is the check's
    exit and its last step, before any 124, so a 124 never hides one and never stands for one."""
    repo = stubbed(tmp_path, touching("tests/test_slow.py", "tests/test_quick.py"))
    brief = a_brief(tmp_path)
    said, ran_code, ran, base = selected(tmp_path, repo, exits=exits)
    head = git(repo, "rev-parse", "HEAD")
    assert ran_code == code
    assert ran[-1].startswith(f"test TESTS=tests/{last}.py"), ran
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit {code} at {head}\n"
    )
    assert ready.short_on_checked(brief.read_text(), head), "jmerge holds it"


def test_a_failed_step_ends_the_check_and_a_run_again_skips_what_passed_at_the_head(tmp_path):
    """A failure is the check's exit and its last step. Run again at the same head, the block
    skips the steps that passed there, so a wait for a slot or a call cut at its time limit never
    starts the check over, and runs the rest."""
    repo = stubbed(tmp_path, touching("tests/test_a.py", "tests/test_b.py", "tests/test_c.py"))
    a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, exits={"*test_b.py*": 1})
    assert code == 1
    assert ran == [lint(base), alone("tests/test_a.py"), alone("tests/test_b.py")]
    said, code, ran, base = selected(tmp_path, repo)
    assert code == 0
    assert ran == [alone("tests/test_b.py"), alone("tests/test_c.py")]
    assert "lint: passed at this head already" in said
    (repo / "page.md").write_text("A new head.\n")
    git(repo, "commit", "-qam", "a new head")
    said, code, ran, base = selected(tmp_path, repo)
    assert [one.split()[0] for one in ran] == ["check-fast", "test", "test", "test"]


def test_with_every_short_slot_taken_the_check_waits_and_writes_no_checked_line(
    tmp_path, monkeypatch
):
    """A step that finds no short slot registers the thread as a waiter and ends the block 76,
    with no `Checked:` line: a wait is no verdict either."""
    monkeypatch.delenv("TEST_SLOTS", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    stubbed(tmp_path, touching("tests/test_a.py"))
    brief = a_brief(tmp_path)
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for n in (1, 2, 3):
        fd = os.open(locks / f"test-slot-short.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    try:
        stub, log = tmp_path / "stub", tmp_path / "make.log"
        stub.mkdir()
        room.uv(stub)
        lanes(stub, locks, log)
        said, code, _ = checked(tmp_path, "echo the full lane")
    finally:
        for fd in held:
            os.close(fd)
    assert code == 76
    assert not log.exists()
    assert "mcp:thread-1 is registered as a waiter" in "\n".join(said)
    assert brief.read_text() == "# a-task: a task\n\n## Result\n"


def test_a_change_that_touches_no_test_runs_only_the_lint(tmp_path):
    """A change no test file of which it touches, a doc only, still gets the lint, in the short
    lane, and its line is the same `PART=touched`, never `PYTEST=:`."""
    repo = stubbed(tmp_path, touching())
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    head = git(repo, "rev-parse", "HEAD")
    assert said[0].startswith("touched: 0 test files"), said
    assert (ran, code) == ([lint(base)], 0)
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


def test_a_selector_that_fails_is_no_check_and_ends_the_block_1(tmp_path):
    repo = stubbed(tmp_path, "import sys; sys.exit('the selector broke')")
    said, code, ran, _ = selected(tmp_path, repo)
    assert (said, code, ran) == (
        ["no check: scripts/select_tests.py could not name the touched tests"],
        1,
        [],
    )


def test_a_stacked_link_selects_only_its_own_change_from_the_branch_it_is_stacked_on(tmp_path):
    """A link stacked on another pull request's branch is checked from where it left that
    branch, as its pull request is based on it, and not from `origin/main`, which would take the
    change of every link under it too. jbus's `Stacked on:` line names that branch."""
    repo = stubbed(tmp_path, touching())
    git(repo, "update-ref", "refs/remotes/origin/below", "HEAD")
    (repo / "mine.md").write_text("This link's own page.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "this link")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo, on="origin/below")
    assert base == git(repo, "rev-parse", "HEAD~1")
    assert (ran, code) == ([lint(base)], 0)


def test_a_link_whose_base_branch_is_gone_selects_from_origin_main(tmp_path):
    """A link's base branch is deleted once it merges, before jbus rewrites the brief's
    `Stacked on:` line, and the link is then checked from `origin/main`, which holds it."""
    repo = stubbed(tmp_path, touching())
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo)
    assert (ran, code) == ([lint(base)], 0)


def test_the_check_block_runs_jstacks_jgauge_from_a_worktree_whose_venv_has_an_older_one(tmp_path):
    """The check block runs `jgauge` by a project path under `$T`. A crew's worktree based on an
    older main has a `.venv` whose `jgauge` has no `check`, and uv takes a virtual environment
    from the working directory when the project path holds no project. The block run from such
    a worktree, with `T` in an installed layout, still gets jstack's own `jgauge`."""
    work = tmp_path / "worktree"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    }
    subprocess.run(["uv", "venv", "-q", str(work / ".venv")], check=True, env=env)
    old = work / ".venv" / "bin" / "jgauge"
    old.write_text("#!/bin/sh\necho \"jgauge: invalid choice: 'check'\" >&2\nexit 2\n")
    old.chmod(0o755)
    (prefix,) = set(
        re.findall(
            r'(uv run --project "[^"]*") jgauge check', block("Do the task", "<check command>")
        )
    )
    ran = subprocess.run(
        ["sh", "-c", f"{prefix} jgauge check --help"],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        env={**env, "T": str(assembled() / "templates")},
    )
    assert (ran.returncode, ran.stdout.splitlines()[:1]) == (
        0,
        ["usage: jgauge check [-h] [--thread ID] [--wait SECONDS]"],
    ), ran.stderr


@pytest.mark.parametrize(
    ("brief", "dirty", "written"),
    [
        pytest.param("# a-task: a task\n\n## Result\nStatus: done\n", False, True, id="a Result"),
        pytest.param("# a-task: a task\n", False, True, id="no Result yet"),
        pytest.param("# a-task: a task\n\n## Result\n", True, False, id="uncommitted work"),
    ],
)
def test_the_block_adds_the_checked_line_for_a_check_of_a_committed_head(
    tmp_path, brief, dirty, written
):
    """The block writes the `Checked:` line `jmerge` reads, for a check that ran to its end on the
    head as it is committed, and on no other, from the first head on: a brief with no Result yet
    gets it too, so the first head's check is on record."""
    repo = stubbed(tmp_path, touching())
    if dirty:
        (repo / "page.md").write_text("An edit not committed.\n")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text(brief)
    said, code, ran, base = selected(tmp_path, repo)
    head = git(repo, "rev-parse", "HEAD")
    line = f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    assert code == 0 and len(ran) == 1
    assert (tasks / "a-task.md").read_text() == brief + (line if written else "")


def test_the_block_names_the_exit_of_jgauge_check_on_the_checked_line(tmp_path):
    """`checked` gives every `jgauge check` of the block its `--wait`, the name on the line
    too."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "file").write_text("one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the file")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a task\n\n## Result\n")
    said, code, _ = checked(tmp_path, "exit 3")
    head = git(repo, "rev-parse", "HEAD")
    assert (said[-1], code) == ("done: the check exited 3", 3)
    named = f"\nChecked: jgauge check --wait 60 exit 3 at {head}\n"
    assert (tasks / "a-task.md").read_text().endswith(named)


def pushed(tmp_path, lines, dirty=False, brief=True):
    """Run the first-push block of "Do the task" once, in a worktree whose branch has one
    commit and whose brief ends with `lines`, each `{head}` the head. It returns what the block
    printed, its exit code, the head and the commit the branch has at the origin, or nothing."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "a-task", str(repo)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    (repo / "file").write_text("one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the task")
    head = git(repo, "rev-parse", "HEAD")
    if dirty:
        (repo / "file").write_text("an edit not committed\n")
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    if brief:
        (tasks / "a-task.md").write_text(
            "# a-task: a task\n\n## Result\n" + lines.format(head=head)
        )
    script = block("Do the task", "short_on_checked").replace("<slug>", "a-task")
    ran = subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **{k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            "T": str(assembled() / "templates"),
            "H": str(tmp_path / "state"),
        },
    )
    at = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "refs/heads/a-task"],
        cwd=origin,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return ran.stdout.splitlines(), ran.returncode, head, at


TOUCHED = "Checked: make check-fast BASE=" + "c" * 40 + " PART=touched exit {exit} at {at}\n"
GUARDS = TOUCHED.replace("PART=touched", "PART=guards")


@pytest.mark.parametrize("line", [TOUCHED, GUARDS], ids=["the touched tests", "an older guards"])
def test_the_first_push_goes_out_once_the_desk_check_passed_at_the_head(tmp_path, line):
    said, code, head, at = pushed(tmp_path, line.format(exit=0, at="{head}"))
    assert (said, code, at) == ([f"pushed: a-task at {head}"], 0, head)


@pytest.mark.parametrize(
    ("lines", "why"),
    [
        pytest.param("", "its brief has no Checked: line", id="missing"),
        pytest.param(
            TOUCHED.format(exit=1, at="{head}"), "its last Checked: line ends 1 at", id="exit 1"
        ),
        pytest.param(
            TOUCHED.format(exit=124, at="{head}"),
            "its last Checked: line ends 124 at",
            id="exit 124",
        ),
        pytest.param(
            TOUCHED.format(exit=0, at="{head}") + TOUCHED.format(exit=124, at="{head}"),
            "its last Checked: line ends 124 at",
            id="a 124 after a pass",
        ),
        pytest.param(
            TOUCHED.format(exit=0, at="d" * 40), "its last Checked: line is of ", id="stale"
        ),
    ],
)
def test_the_first_push_is_refused_where_the_desk_check_did_not_pass_at_the_head(
    tmp_path, lines, why
):
    """The block asks `jmerge`'s own rule of the brief, with no other head carried, and
    pushes nothing on any exit but 0, a time limit's 124 too."""
    said, code, _, at = pushed(tmp_path, lines)
    assert code == 1 and at == ""
    assert len(said) == 1 and said[0].startswith(f"no push: {why}"), said
    assert "the crew's check block (features/crew/do-the-task.md)" in said[0]


def test_the_first_push_of_uncommitted_work_is_refused(tmp_path):
    said, code, _, at = pushed(tmp_path, TOUCHED.format(exit=0, at="{head}"), dirty=True)
    assert (said, code, at) == (["no push: commit the work first"], 1, "")


def test_the_first_push_with_no_brief_is_refused(tmp_path):
    said, code, _, at = pushed(tmp_path, "", brief=False)
    brief = tmp_path / "state" / "tasks" / "a-task.md"
    assert (said, code, at) == ([f"no push: there is no brief at {brief}"], 1, "")
