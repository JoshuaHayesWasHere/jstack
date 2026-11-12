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
            "JGAUGE_LOCKS_DIR": str(home / ".local" / "state" / "locks"),
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
        "test-slot-waiters.lock",
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
            "JGAUGE_LOCKS_DIR": str(home / ".local" / "state" / "locks"),
            "TEST_SLOTS": "3",
            "PATH": f"{home.parent / 'stub'}:{room.BIN}:{os.environ['PATH']}",
            "T": str(assembled() / "templates"),
        },
    )


def test_with_every_slot_taken_the_blocks_register_the_thread_and_end_76(tmp_path, monkeypatch):
    """When every slot is taken, the blocks end 76. A targeted run in the short lane registers
    nothing and says to run it again now; the check, in the full lane, registers the thread in
    the file, and jbus wakes the thread later because the file lists it. The lanes are the 4
    full and 3 short slots that a machine with 24 processors and 62 GiB gets, whatever
    `TEST_SLOTS` the machine sets."""
    monkeypatch.delenv("TEST_SLOTS", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    monkeypatch.setenv("JGAUGE_SHORT_WAIT_SECONDS", "0")
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
        assert ran.returncode == 76
        assert "run the same command again now, in this turn" in ran.stdout
        assert not (locks / "test-slot-waiters.json").exists()
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
                "JGAUGE_LOCKS_DIR": str(home / ".local" / "state" / "locks"),
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


def lanes(stub, locks, log, exits=None, takes=None, junit=None):
    """A `make` on the path that records its arguments, and which lane's slot was held while it
    ran: `short` when any slot of the short lane was, `full` when any of the full lane's were. It
    asks with `TAKEN`, by Python's fcntl, since macOS has no `flock` command. It ends with the
    code of the first of `exits` whose shell pattern matches what it records, and 0 by default.
    With `takes`, each run moves the clock of `clocked` on by that many seconds and records the
    wait for a short slot it was given, in `waits` beside the clock. It records a run with the
    `JUNIT=<file>` it was given left out, and with `junit`, a `(seconds, failing)` pair, writes
    pytest's report there first: each file of `TESTS` one test of its seconds, 1 by default,
    failed where `failing` names it."""
    ends = "".join(
        f"{pattern.replace(' ', chr(92) + ' ')}) exit {code} ;; "
        for pattern, code in (exits or {}).items()
    )
    taken = stub / "taken.py"
    taken.write_text(TAKEN)
    held = f"{shlex.quote(sys.executable)} {shlex.quote(str(taken))}"
    report = ""
    if junit is not None:
        (stub / "junit.json").write_text(json.dumps(list(junit)))
        (stub / "junit.py").write_text(REPORT)
        report = (
            f"for one; do case $one in JUNIT=*) {shlex.quote(sys.executable)} "
            f'{stub / "junit.py"} {stub / "junit.json"} "$@" ;; esac; done\n'
        )
    (stub / "make").write_text(
        "#!/bin/sh\nshort=free\nfull=free\n"
        + report
        + f'for one in {locks}/test-slot-short.*.lock; do [ -e "$one" ] && {held} "$one" '
        "&& short=held; done\n"
        f'for one in {locks}/test-slot.*.lock; do [ -e "$one" ] && {held} "$one" '
        "&& full=held; done\n"
        'said="$(printf %s "$*" | sed "s/ JUNIT=[^ ]*//") short=$short full=$full"\n'
        f'echo "$said" >> {log}\n'
        + (
            f'echo "${{JGAUGE_SHORT_WAIT_SECONDS-unset}}" >> {stub / "waits"}\n'
            f"echo $(($(cat {stub / 'clock'}) + {takes})) > {stub / 'clock'}\n"
            if takes
            else ""
        )
        + f'case "$said" in {ends}esac\n'
    )
    (stub / "make").chmod(0o755)
    if takes:
        clocked(stub)


REPORT = """import json, sys

seconds, failing = json.load(open(sys.argv[1]))
words = dict(one.split("=", 1) for one in sys.argv[2:] if "=" in one)
cases = []
for one in words.get("TESTS", "").split():
    dotted = one.removesuffix(".py").replace("/", ".")
    bad = '<failure message="it failed"/>' if one in failing else ""
    cases.append(
        f'<testcase classname="{dotted}" name="test_it" time="{seconds.get(one, 1)}">{bad}</testcase>'
    )
with open(words["JUNIT"], "w") as report:
    report.write('<testsuites><testsuite name="pytest">' + "".join(cases) + "</testsuite></testsuites>")
"""


def clocked(stub):
    """A `date` on the path whose `+%s` is the clock in `stub/clock`, which only the `make` of
    `lanes` moves, so a step takes the time the test says and no more."""
    (stub / "clock").write_text("1000\n")
    (stub / "date").write_text(
        f'#!/bin/sh\n[ "$*" = +%s ] && exec cat {stub / "clock"}\nexec /bin/date "$@"\n'
    )
    (stub / "date").chmod(0o755)


def selected(tmp_path, repo, on="origin/main", exits=None, takes=None, junit=None):
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
    lanes(stub, locks, log, exits, takes, junit)
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


def touching(*files, cross=(), names=()):
    """A selector that prints `files` for `--part touched`, `cross` for `--part cross` and
    `names`, a step a line, for `--part names`, and fails on any other ask."""
    parts = {"touched": list(files), "cross": list(cross), "names": list(names)}
    return (
        f"import sys\nparts = {parts!r}\n"
        "assert sys.argv[1] == '--part' and sys.argv[2] in parts, sys.argv\n"
        "print('\\n'.join(parts[sys.argv[2]]))\n"
    )


def lint(base, lane="short=held full=free"):
    return f"check-fast BASE={base} PYTEST=: PART=touched {lane}"


def alone(test, base, lane="short=held full=free"):
    return f"test TESTS={test} BASE={base} {lane}"


def a_brief(tmp_path):
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    brief = tasks / "a-task.md"
    brief.write_text("# a-task: a task\n\n## Result\n")
    return brief


def cloned(tmp_path):
    """A clone of this checkout, with `origin/main` at its head."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(repo)], check=True)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def guarded(repo, base, touched=()):
    """The guard tests the real selector names for the branch: the cross-cutting tests of its
    selection, wherever they live, less the `touched` ones."""
    printed = subprocess.run(
        [sys.executable, "scripts/select_tests.py", "--part", "cross", base, "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [one for one in printed if one not in touched]


def named(repo, base):
    """The steps of the names part the real selector prints for the branch, each a list of its
    files: the tests the pull request's check selects because they read a file the branch edits."""
    printed = subprocess.run(
        [sys.executable, "scripts/select_tests.py", "--part", "names", base, "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [line.split() for line in printed]


def test_a_change_runs_the_lint_each_touched_test_and_each_test_that_reads_it_in_the_short_lane(
    tmp_path,
):
    """In jstack, the desk's check is the lint, the test files the change touches, the repo's
    guard tests and the tests that read the change, each step its own call of the short lane,
    and never the selection: CI's check is the check of record and runs the rest. The real
    selector names the touched tests: a test file the branch edits. The guard tests are the
    cross-cutting tests of the selection, and not the catch-all. The crew tests that read the
    edited doc run last, a few files a step, as #1691's check would have run
    test_status_line_readers.py at the desk."""
    repo = cloned(tmp_path)
    with (repo / "features" / "crew" / "the-checks.md").open("a") as page:
        page.write("\nA line the test adds.\n")
    mine = "features/crew/tests/test_crew_label.py"
    with (repo / mine).open("a") as test:
        test.write("\n# A line the test adds.\n")
    git(repo, "commit", "-qam", "a change to the crew feature")
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    guards = guarded(repo, base)
    steps = named(repo, base)
    reads = [one for step in steps for one in step]
    assert "features/repo-guards/tests/test_new_lines_run.py" in guards
    assert "features/crew/tests/test_crew_checks.py" in reads
    assert not set(reads) & {mine, *guards}
    assert said[0] == (
        f"touched: 1 test files, then {len(guards)} cross-cutting guard tests, "
        "then 0 test files CI failed on, each alone in the short lane after the lint, "
        f"then {len(reads)} test files that read the change in {len(steps)} steps; "
        "CI's check runs the rest of the selection"
    ), said
    assert re.fullmatch(r"lint: exit 0 in \d+ s, short lane", said[1]), said
    assert re.fullmatch(rf"{mine}: exit 0 in \d+ s, short lane", said[2]), said
    assert re.fullmatch(rf"{','.join(steps[-1])}: exit 0 in \d+ s, short lane", said[-1]), said
    assert ran == [
        lint(base),
        alone(mine, base),
        *(alone(one, base) for one in guards),
        *(alone(" ".join(step), base) for step in steps),
    ]
    assert code == 0
    head = git(repo, "rev-parse", "HEAD")
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


def test_a_step_of_the_tests_that_read_the_change_runs_its_files_at_once_after_the_others(
    tmp_path,
):
    """Each line the names part prints is one step, after the guards and the files CI failed on:
    one `make test` of all its files in the short lane. A failed step fails the check, and a run
    again at the same head runs only that step."""
    g = "features/repo-guards/tests/test_g.py"
    steps = ("tests/test_m.py tests/test_n.py", "tests/test_o.py")
    repo = stubbed(tmp_path, touching("tests/test_a.py", cross=(g,), names=steps))
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, exits={"*test_o.py*": 1})
    head = git(repo, "rev-parse", "HEAD")
    assert said[0].endswith(
        "then 3 test files that read the change in 2 steps; "
        "CI's check runs the rest of the selection"
    ), said
    assert ran == [
        lint(base),
        alone("tests/test_a.py", base),
        alone(g, base),
        alone("tests/test_m.py tests/test_n.py", base),
        alone("tests/test_o.py", base),
    ]
    assert re.search(
        r"^tests/test_m.py,tests/test_n.py: exit 0 in \d+ s, short lane$", "\n".join(said), re.M
    ), said
    assert code == 1
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 1 at {head}\n"
    )
    said, code, ran, base = selected(tmp_path, repo)
    assert (ran, code) == ([alone("tests/test_o.py", base)], 0)


def test_a_step_the_short_lane_stops_runs_again_alone_in_a_full_slot_and_passes(tmp_path):
    """Josh, 2026-11-05: the check must not time out. A test file the short lane stops at its
    limit, as a loaded machine makes it, ends 124 there: that is no verdict, so the block runs
    that file again alone in a full slot, which has no limit, and its verdict there is the
    step's. The other steps stay in the short lane."""
    repo = stubbed(tmp_path, touching("tests/test_slow.py", "tests/test_quick.py"))
    brief = a_brief(tmp_path)
    slow = "*test_slow.py BASE=* short=held*"
    said, code, ran, base = selected(tmp_path, repo, exits={slow: 124})
    head = git(repo, "rev-parse", "HEAD")
    assert ran == [
        lint(base),
        alone("tests/test_slow.py", base),
        alone("tests/test_slow.py", base, "short=free full=held"),
        alone("tests/test_quick.py", base),
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
            {"*test_slow.py BASE=* short=held*": 124, "*test_slow.py*": 1},
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
    assert ran == [lint(base), alone("tests/test_a.py", base), alone("tests/test_b.py", base)]
    said, code, ran, base = selected(tmp_path, repo)
    assert code == 0
    assert ran == [alone("tests/test_b.py", base), alone("tests/test_c.py", base)]
    assert "lint: passed at this head already" in said
    (repo / "page.md").write_text("A new head.\n")
    git(repo, "commit", "-qam", "a new head")
    said, code, ran, base = selected(tmp_path, repo)
    assert [one.split()[0] for one in ran] == ["check-fast", "test", "test", "test"]


def test_a_step_that_passed_over_work_the_head_lacks_is_not_kept_and_writes_no_checked_line(
    tmp_path,
):
    """CrewProof.tla's trace CheckStart MovedToBackground Edit CheckStep Undo CheckStep AllRan
    CheckEnd: the call goes to the background, the crew edits while a step runs, the step passes
    over the edit, the crew drops it, and the block must not keep that step as passed at the head
    or write `Checked: ... exit 0` for files the head never had."""
    repo = stubbed(tmp_path, touching("tests/test_a.py", "tests/test_b.py"))
    brief = a_brief(tmp_path)
    stub, edit = tmp_path / "stub", repo / "edit.txt"
    stub.mkdir()
    room.uv(stub)
    lanes(stub, tmp_path / "home" / ".local" / "state" / "locks", tmp_path / "make.log")
    (stub / "make").rename(stub / "make.real")
    (stub / "make").write_text(
        "#!/bin/sh\n"
        f'case "$*" in *test_a.py*) echo an edit > {edit} ;; *test_b.py*) rm -f {edit} ;; esac\n'
        f'exec {stub / "make.real"} "$@"\n'
    )
    (stub / "make").chmod(0o755)
    said, code, _ = checked(tmp_path, "echo the full lane")
    steps = (repo / ".git" / "crew-check-steps").read_text().splitlines()
    assert re.search(r"^tests/test_a.py: exit 0 in \d+ s, short lane$", "\n".join(said), re.M), said
    assert "passed lint" in steps
    assert "passed tests/test_a.py" not in steps
    head = git(repo, "rev-parse", "HEAD")
    moved = f"tests/test_a.py: passed over work that {head} does not have, so it is not kept"
    assert said[-1] == moved, said
    assert not [one for one in said if one.startswith("running:")], said
    assert code == 76, said
    assert "Checked:" not in brief.read_text()


def test_the_guard_tests_run_after_the_touched_ones_and_a_failed_one_fails_the_check(tmp_path):
    """After the touched tests the block runs each cross-cutting test the selector names, alone.
    A guard the change touches runs once, as a touched test. A failed guard is the check's exit,
    as a failed touched test is, and a run again at the same head runs only the steps that did
    not pass."""
    g, h = "features/repo-guards/tests/test_g.py", "features/repo-guards/tests/test_h.py"
    selector = touching("tests/test_a.py", h, cross=(g, h))
    repo = stubbed(tmp_path, selector)
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, exits={"*test_g.py*": 1})
    head = git(repo, "rev-parse", "HEAD")
    assert said[0].startswith("touched: 2 test files, then 1 cross-cutting guard tests"), said
    assert ran == [lint(base), alone("tests/test_a.py", base), alone(h, base), alone(g, base)]
    assert re.search(rf"^{g}: exit 1 in \d+ s, short lane$", "\n".join(said), re.M), said
    assert code == 1
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 1 at {head}\n"
    )
    said, code, ran, base = selected(tmp_path, repo)
    assert (ran, code) == ([alone(g, base)], 0)
    assert f"{h}: passed at this head already" in said
    assert ready.short_on_checked(brief.read_text(), head) == ""


def test_a_file_ci_failed_on_is_a_step_until_it_passes(tmp_path):
    """A test file CI failed on, kept by the block of "The failed files", runs after the guards,
    alone, though the change only reached it. It stays kept while it fails, and while it passes
    on a worktree with work not committed, and leaves the kept list once it passes at a committed
    head. A kept name that is not in the worktree runs nothing, and one a step already runs runs
    once."""
    g = "features/repo-guards/tests/test_g.py"
    repo = stubbed(tmp_path, touching("tests/test_a.py", cross=(g,)))
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ci.py").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the test CI failed on")
    kept = repo / ".git" / "crew-failed-files"
    kept.write_text("tests/test_a.py\ntests/test_ci.py\ntests/test_gone.py\n")
    brief = a_brief(tmp_path)
    head = git(repo, "rev-parse", "HEAD")

    said, code, ran, base = selected(tmp_path, repo, exits={"*test_ci.py*": 1})
    assert said[0].startswith(
        "touched: 1 test files, then 1 cross-cutting guard tests, then 1 test files CI failed on,"
    ), said
    assert ran == [
        lint(base),
        alone("tests/test_a.py", base),
        alone(g, base),
        alone("tests/test_ci.py", base),
    ]
    assert code == 1
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 1 at {head}\n"
    )
    assert kept.read_text() == "tests/test_ci.py\ntests/test_gone.py\n"

    (repo / "scratch.txt").write_text("work not committed\n")
    said, code, ran, base = selected(tmp_path, repo)
    assert (ran[-1], code) == (alone("tests/test_ci.py", base), 0)
    assert kept.read_text() == "tests/test_ci.py\ntests/test_gone.py\n"
    (repo / "scratch.txt").unlink()

    said, code, ran, base = selected(tmp_path, repo)
    assert (ran, code) == ([alone("tests/test_ci.py", base)], 0)
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )
    assert kept.read_text() == "tests/test_gone.py\n"


def test_a_cross_cutting_guard_outside_repo_guards_is_a_desk_step(tmp_path):
    """A cross-cutting guard that lives in a feature, as the home tree's spec does, is a desk
    step like one under features/repo-guards/tests: dropped at the desk, it failed first in CI
    (8 of 51 failed attempts on a `make test` part, 2026-11-09). The catch-all stays CI's."""
    repo = cloned(tmp_path)
    with (repo / "features" / "crew" / "the-checks.md").open("a") as page:
        page.write("\nA line the test adds.\n")
    git(repo, "commit", "-qam", "a change to the crew feature")
    a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    assert alone("features/home/tests/test_home_tree_spec.py", base) in ran, said
    assert code == 0


NEW_LINES = "features/repo-guards/tests/test_new_lines_run.py"


def guard_make(stub):
    """A `make` on the path that runs the new-lines guard for real, with the `BASE` the block
    gives it, and passes every other step. The guard's own pytest must not see the outer run's
    workers or a CI part's recording."""
    (stub / "make").write_text(
        "#!/bin/sh\n"
        'for one; do case $one in TESTS=*|BASE=*) export "$one" ;; esac; done\n'
        f'[ "$TESTS" = {NEW_LINES} ] || exit 0\n'
        "unset $(env | sed -n 's/^\\(PYTEST_[A-Z_]*\\)=.*/\\1/p') NEW_LINES_PART NEW_LINES_PARTS "
        "NEW_LINES_TEST COVERAGE_PROCESS_START\n"
        f"exec {shlex.quote(sys.executable)} -m pytest -q -p no:cacheprovider "
        f'"$TESTS::test_every_line_this_branch_adds_to_a_feature_runs_in_a_test"\n'
    )
    (stub / "make").chmod(0o755)


@pytest.mark.timeout(600)
@pytest.mark.parametrize("unrun", [True, False], ids=["a line no test runs", "clean"])
def test_a_branch_that_adds_a_line_no_test_runs_fails_the_desk_check(tmp_path, unrun):
    """The guard behind most red checks of pull requests the desk had passed: a branch that adds
    a statement to a feature's `src/` that no test runs fails the desk's check, at the step of
    the new-lines guard, before the review reads it. A branch clean of that passes it, with the
    `Checked:` line jmerge binds."""
    repo = cloned(tmp_path)
    if unrun:
        (repo / "features/jgauge/src/jgauge/never_run.py").write_text(
            '"""A module no test names."""\n\n\ndef never():\n    return 1\n'
        )
    else:
        with (repo / "features/crew/the-checks.md").open("a") as page:
            page.write("\nA line the test adds.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the branch")
    head = git(repo, "rev-parse", "HEAD")
    brief = a_brief(tmp_path)
    stub = tmp_path / "stub"
    stub.mkdir()
    room.uv(stub)
    guard_make(stub)
    said, code, _ = checked(tmp_path, "echo the full lane", limit=540)
    step = re.findall(
        rf"^{NEW_LINES}: exit (\d+) in \d+ s, (?:short|full) lane$", "\n".join(said), re.M
    )
    if unrun:
        assert (step, code) == (["1"], 1), said
        assert ready.short_on_checked(brief.read_text(), head), "jmerge holds it"
    else:
        assert (step, code) == (["0"], 0), said
        assert ready.short_on_checked(brief.read_text(), head) == ""


def test_with_every_short_slot_taken_the_check_waits_and_writes_no_checked_line(
    tmp_path, monkeypatch
):
    """A step that finds no short slot by the lane's ceiling ends the block 76 and says to run it
    again now, with no `Checked:` line: a wait is no verdict either."""
    monkeypatch.setenv("JGAUGE_SHORT_WAIT_SECONDS", "0")
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
    assert "run the same command again now, in this turn" in "\n".join(said)
    assert not (locks / "test-slot-waiters.json").exists()
    assert brief.read_text() == "# a-task: a task\n\n## Result\n"


FOUR = ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_d.py")


def test_the_block_starts_no_step_it_cannot_end_in_its_call(tmp_path, monkeypatch):
    """A call ends at 600 s, and past it the harness moves the block to the background, where
    each step's end wakes the thread. So the block starts no step with less of its 540 s left
    than the short lane's 120 s limit: with each step taking 150 s, the third step ends at
    450 s and the fourth and fifth are not started. It says how many steps are left, ends 76 as
    a wait does, and writes no `Checked:` line, since the check as a whole reached no verdict."""
    monkeypatch.delenv("JGAUGE_SHORT_WAIT_SECONDS", raising=False)
    repo = stubbed(tmp_path, touching(*FOUR))
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, takes=150)
    assert ran == [lint(base), alone(FOUR[0], base), alone(FOUR[1], base)]
    assert (said[-1], code) == ("running: 2 steps left", 76), said
    assert brief.read_text() == "# a-task: a task\n\n## Result\n"


def test_a_step_waits_no_longer_than_the_call_has_left(tmp_path, monkeypatch):
    """A step's wait for a short slot is the time left of the 540 s less the 120 s the step may
    then run, and never more than the lane's own ceiling of 300 s: 300 s at 0 s, 270 s at 150 s
    and 120 s at 300 s."""
    monkeypatch.delenv("JGAUGE_SHORT_WAIT_SECONDS", raising=False)
    repo = stubbed(tmp_path, touching(*FOUR))
    a_brief(tmp_path)
    selected(tmp_path, repo, takes=150)
    assert (tmp_path / "stub" / "waits").read_text().split() == ["300", "270", "120"]


def test_a_block_run_again_ends_the_steps_left(tmp_path, monkeypatch):
    """On `running:` the block is run again in the turn: at the same head it skips the steps
    that passed, runs the rest in a call of its own, and writes the `Checked:` line once the
    last has passed."""
    monkeypatch.delenv("JGAUGE_SHORT_WAIT_SECONDS", raising=False)
    repo = stubbed(tmp_path, touching(*FOUR))
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, takes=150)
    assert code == 76
    said, code, ran, base = selected(tmp_path, repo, takes=150)
    head = git(repo, "rev-parse", "HEAD")
    assert ran == [alone(FOUR[2], base), alone(FOUR[3], base)]
    assert code == 0, said
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


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


MAIN_SELECTOR = """import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
parts = {"touched": ["tests/test_a.py"], "cross": [], "names": ["tests/test_b.py"]}
if sys.argv[2] == "names":
    parts["names"][0] += " " + (ROOT / "reads.txt").read_text().strip()
print("\\n".join(parts[sys.argv[2]]))
"""


def test_a_link_whose_own_selector_is_behind_mains_names_its_tests_with_mains(tmp_path):
    """A link stacked on a branch that left main before `--part names` has a selector that
    lacks it. The block names the tests with `origin/main`'s selector, run over the link's own
    tree, so the three lists come out and the check runs to a `Checked:` line."""
    older = touching("tests/test_a.py").replace(", 'names': []", "")
    assert "names" not in older
    repo = stubbed(tmp_path, older)
    git(repo, "update-ref", "refs/remotes/origin/below", "HEAD")
    git(repo, "checkout", "-q", "-b", "main-moved")
    (repo / "scripts" / "select_tests.py").write_text(MAIN_SELECTOR)
    git(repo, "commit", "-qam", "main's selector")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-q", "-")
    (repo / "reads.txt").write_text("tests/test_c.py\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "this link")
    brief = a_brief(tmp_path)
    brief.write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo, on="origin/below")
    head = git(repo, "rev-parse", "HEAD")
    assert base == git(repo, "rev-parse", "HEAD~1")
    assert (ran, code) == (
        [
            lint(base),
            alone("tests/test_a.py", base),
            f"test TESTS=tests/test_b.py tests/test_c.py BASE={base} short=held full=free",
        ],
        0,
    ), said
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


def test_with_no_selector_on_origin_main_the_block_says_so_and_runs_the_branchs(tmp_path):
    repo = stubbed(tmp_path, touching("tests/test_a.py"))
    empty = git(repo, "hash-object", "-t", "tree", "-w", "/dev/null")
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "commit-tree", "-m", "0", empty))
    git(repo, "update-ref", "refs/remotes/origin/below", "HEAD~1")
    brief = a_brief(tmp_path)
    brief.write_text("# a-task: a link\nStacked on: below below\n")
    said, code, ran, base = selected(tmp_path, repo, on="origin/below")
    assert said[0] == (
        "origin/main has no scripts/select_tests.py: the branch's own names the tests"
    ), said
    assert (ran, code) == ([lint(base), alone("tests/test_a.py", base)], 0)


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
