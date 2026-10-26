"""Start a run under a test slot, or join the one an earlier call started, and wait on it.

A thread's call ends at its time limit, and a crewmate's check or a reviewer's proof can run
longer than that. So `jgauge check` and `jgauge proof` start the run in a session of its own,
under `jgauge test-slot --thread`, and wait on it for up to `WAIT_SECONDS`. A later call joins
the run that is going, by its pid file, and gives the answer of one that ended between two calls
once. Each run keeps its files in one folder: the pid, the output, the exit code, the key it was
started for, the command, and a `told` file once its answer was given. A run whose key is not the
key of the call that reads its answer is stale.

The commands do in Python what the thread's step did in shell: the delete, the background launch
and the inner shell. Claude Code asks the user before it runs a step that holds one of those,
even in full access, so the step is one call with the command on stdin.

`jgauge check` keeps the files the crew skill's check block kept, `$G/crew-check/{pid,out,exit,
tree,told,run}`, so a check that block started is joined and not started twice. Its key is the
tree of the worktree as it is now, written with an index of its own. `jgauge proof` keeps the
pr-review block's `proof.*` files beside the prompt, and its key is a hash of the proof and of
`proof.sh`.

A run that finds every slot taken registers its thread with what the thread runs again once jbus
wakes it, `jgauge check` or `jgauge proof`: the check removes its folder then, and a run file run
by hand would hold no slot.

The run starts with `python -P`, which keeps the worktree off `sys.path`, so a module of the repo
under check that has a stdlib name is never imported in place of the stdlib's.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from jgauge import slot

WAIT_SECONDS = 540.0
LOOK_EVERY_SECONDS = 0.2
STALE = 75
WAITER = "is registered as a waiter"


@dataclass(frozen=True)
class Files:
    """The folder of one run, and the names of its files in it."""

    folder: Path
    prefix: str
    key_name: str
    command_name: str

    def path(self, name: str) -> Path:
        return self.folder / f"{self.prefix}{name}"

    @property
    def key(self) -> Path:
        return self.path(self.key_name)

    @property
    def command(self) -> Path:
        return self.path(self.command_name)

    def read(self, name: str) -> str:
        try:
            return self.path(name).read_text().strip()
        except (FileNotFoundError, UnicodeDecodeError):
            return ""

    def tell(self) -> None:
        self.path("told").touch()

    def lines(self, last: int | None = None) -> list[str]:
        try:
            said = self.path("out").read_text(errors="replace").splitlines()
        except FileNotFoundError:
            return []
        return said if last is None else said[-last:]


class Run:
    """One run's files, and the child this call started, when it started one."""

    def __init__(self, files: Files, wake: str) -> None:
        self.wake = wake
        self.files = files
        self.child: subprocess.Popen | None = None

    def alive(self) -> bool:
        if self.child is not None:
            return self.child.poll() is None
        try:
            os.kill(int(self.files.read("pid")), 0)
        except (ValueError, ProcessLookupError):
            return False
        except PermissionError:
            return True
        return True

    def running(self) -> bool:
        return (
            self.files.path("pid").is_file() and not self.files.path("exit").is_file()
        ) and self.alive()

    def ended(self) -> bool:
        return self.files.path("exit").is_file()

    def code(self) -> int:
        try:
            return int(self.files.read("exit"))
        except ValueError:
            return 1

    def start(self, key: str, command: str, short: bool, thread: str, env: dict[str, str]):
        files = self.files
        files.key.write_text(f"{key}\n")
        files.command.write_text(command)
        launch = [sys.executable, "-P", "-m", "jgauge.runner", str(files.path("exit")), thread]
        launch += ["--short"] if short else []
        launch += ["--wake", self.wake]
        with files.path("out").open("wb") as out:
            self.child = subprocess.Popen(
                [*launch, "--", "sh", str(files.command)],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                start_new_session=True,
                env=env,
            )
        files.path("pid").write_text(f"{self.child.pid}\n")

    def wait(self, limit: float) -> None:
        until = time.monotonic() + limit
        while not self.ended() and self.running():
            left = until - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(LOOK_EVERY_SECONDS, left))

    def waited_for_a_slot(self) -> bool:
        return self.code() == slot.WAITING and WAITER in "\n".join(self.files.lines())


def git(*args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, env=env
    ).stdout.strip()


def worktree_tree() -> str:
    """The tree of the worktree as it is now, untracked files included, written with a copy of
    the index so the worktree's own index is left as it is."""
    git_dir = Path(git("rev-parse", "--path-format=absolute", "--git-dir"))
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index"))
    with tempfile.TemporaryDirectory(prefix="crew-check.index.", dir=git_dir) as folder:
        own = Path(folder) / "index"
        if index.is_file():
            shutil.copyfile(index, own)
        env = {**os.environ, "GIT_INDEX_FILE": str(own)}
        git("add", "-A", env=env)
        return git("write-tree", env=env)


def say(*lines: str) -> None:
    for line in lines:
        print(line, flush=True)


def check(command: str, thread: str, limit: float) -> int:
    """The crew skill's check: start or join the check command on this worktree, under a slot
    of the full lane, and give its answer."""
    folder = Path(git("rev-parse", "--path-format=absolute", "--git-dir")) / "crew-check"
    run = Run(Files(folder, "", "tree", "run"), "jgauge check")
    tree = worktree_tree()
    if run.running():
        if run.files.read("tree") == tree:
            say(
                "joined: the check an earlier call started on this worktree still runs,"
                " so it is waited on and not started again"
            )
        else:
            say(
                "joined: a check an earlier call started still runs, on the worktree as it was"
                " then: it is waited on and not started again, and once it is done this block"
                " is run again for the worktree as it is now"
            )
    elif run.ended() and not run.files.path("told").exists() and run.files.read("tree") == tree:
        say(
            "checked: the check of this worktree as it is now ended after the last call,"
            " and this is what it said"
        )
    else:
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        run.start(tree, command, False, thread, dict(os.environ))
        say("started: the check runs on this worktree as it is now, and this call waits on it")
    run.wait(limit)
    if run.ended() and run.waited_for_a_slot():
        say(*run.files.lines())
        shutil.rmtree(folder, ignore_errors=True)
        say(
            "waiting: no test slot is free and nothing ran: end your turn now with the one line,"
            " and run this block again when jbus wakes this thread"
        )
        return slot.WAITING
    if run.ended() and run.files.read("tree") != tree:
        run.files.tell()
        say(
            f"stale: the check exited {run.files.read('exit')} on the worktree as it was when it"
            " started, which has changed since: run this block again, and it checks the"
            " worktree as it is now"
        )
        return STALE
    if run.ended():
        run.files.tell()
        say(*run.files.lines(20), f"done: the check exited {run.files.read('exit')}")
        return run.code()
    if run.running():
        last = (run.files.lines(1) or [""])[0]
        say(
            f"running: {last}. Run this block again now, in this turn, and again until it prints"
            " done: never end your turn while it runs"
        )
        return 0
    say(
        "lost: the check stopped with no exit code: run this block again,"
        " and it starts the check afresh"
    )
    return 0


def at_head(kept: str) -> bool:
    git_dir = Path(git("rev-parse", "--path-format=absolute", "--git-dir"))
    rebasing = (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir()
    return git("rev-parse", "HEAD") == kept and not rebasing


def proof(command: str, folder: Path, kept: str, thread: str, limit: float) -> int:
    """The pr-review skill's proof: start or join the proof in the short lane at the head kept
    at the start, and give its answer."""
    if not at_head(kept):
        say(
            f"unproven: this checkout is not at {kept}, or a rebase is going on in it,"
            " so the proof did not run"
        )
        return 1
    run = Run(Files(folder, "proof.", "key", "cmd"), "jgauge proof")
    script = folder / "proof.sh"
    written = script.read_bytes() if script.is_file() else b""
    key = hashlib.sha256(command.encode() + b"\n" + written).hexdigest()
    if run.running():
        say(
            "joined: the proof an earlier call started still runs,"
            " so it is waited on and not started again"
        )
    elif run.ended() and not run.files.path("told").exists() and run.files.read("key") == key:
        say("checked: the proof ended after the last call, and this is what it said")
    else:
        for name in ("pid", "exit", "told", "out"):
            run.files.path(name).unlink(missing_ok=True)
        run.start(key, command, True, thread, {**os.environ, "D": str(folder)})
        say("started: the proof runs at this head, and this call waits on it")
    run.wait(limit)
    if run.ended() and run.waited_for_a_slot():
        run.files.tell()
        say(
            *run.files.lines(),
            "waiting: no short test slot is free and nothing ran: end your turn now with the one"
            " line, and send this block again when jbus wakes this thread",
        )
        return slot.WAITING
    if run.ended() and run.files.read("key") != key:
        run.files.tell()
        say(
            f"stale: the proof exited {run.files.read('exit')} but it was started for a command"
            " that has changed since: send this block again, and it runs the proof as it is now"
        )
        return STALE
    if run.ended():
        run.files.tell()
        say(f"exit {run.files.read('exit')}", *run.files.lines(5))
        if not at_head(kept):
            say("unproven: the head moved under the proof")
        say(*git("status", "--porcelain").splitlines())
        return 0
    if run.running():
        last = (run.files.lines(1) or [""])[0]
        say(
            f"running: {last}. Send this block again now, in this turn, and again until it"
            " prints exit: never end your turn while it runs"
        )
        return 0
    say(
        "lost: the proof stopped with no exit code: send this block again,"
        " and it starts the proof afresh"
    )
    return 0


def serve(argv: list[str]) -> int:
    """The run itself, in its own session: hold a slot for the command, as `jgauge test-slot
    --thread` does, and write its exit code to the exit file when it ends."""
    exit_file, thread, *rest = argv
    short = "--short" in rest[: rest.index("--")]
    wake = rest[rest.index("--wake") + 1].split() if "--wake" in rest[: rest.index("--")] else None
    command = rest[rest.index("--") + 1 :]
    code = 1
    try:
        lane = slot.short() if short else slot.full(slot.count(None))
        code = slot.run(command, lane, thread, wake)
    except Exception as error:
        print(f"jgauge: {error}", file=sys.stderr, flush=True)
    finally:
        sys.stdout.flush()
        written = Path(f"{exit_file}.{os.getpid()}")
        written.write_text(f"{code}\n")
        written.replace(exit_file)
    return code


if __name__ == "__main__":
    sys.exit(serve(sys.argv[1:]))
