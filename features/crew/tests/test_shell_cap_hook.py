"""Every Bash command an agent runs caps its own shell first: the crew's SessionStart hook writes
a line to `CLAUDE_ENV_FILE` that runs `jgauge cap-shell $$`, and Claude Code puts the file's lines
at the head of each command, a `run_in_background` one included, in the shell that runs it.

A stub `jgauge` on PATH stands in for the real one, which would move the test's shell into a
real cgroup; it records the pid it is given and complains on stderr, which the command must not
show. Where cgroup v2 is not mounted (macOS, cgroup v1) the hook writes no such line."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from testing.paths import REPO

HOOK = REPO / "features" / "crew" / "hooks" / "gh-logged.sh"
V2 = Path("/sys/fs/cgroup/cgroup.controllers").exists()
STUB = '#!/bin/sh\necho "$*" >> "$CAPPED"\necho "a complaint no command shows" >&2\nexit 1\n'


@pytest.fixture
def agent(tmp_path):
    """The hook run as Claude Code runs it at a session's start, `again` more times, as a resume
    or a compaction runs it, and a function that runs a command as the Bash tool does."""
    stub = tmp_path / "bin" / "jgauge"
    stub.parent.mkdir()
    stub.write_text(STUB)
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{stub.parent}:{os.environ['PATH']}",
        "CLAUDE_ENV_FILE": str(tmp_path / "env"),
        "CAPPED": str(tmp_path / "capped"),
    }

    def start() -> None:
        started = subprocess.run(
            ["sh", str(HOOK)],
            input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
            env=env,
            capture_output=True,
            text=True,
        )
        assert (started.returncode, started.stderr) == (0, "")

    def run(command: str, background: bool = False) -> tuple[str, str]:
        """Run `command` after the env file's lines, in a session of its own for a background
        command, and return its stdout and stderr."""
        ran = subprocess.Popen(
            ["bash", "-c", f"{(tmp_path / 'env').read_text()}\neval '{command}'"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=background,
        )
        return ran.communicate(timeout=30)

    return start, run, tmp_path


@pytest.mark.skipif(not V2, reason="cgroup v2 is not mounted here")
def test_each_command_caps_its_own_shell_in_the_foreground_and_the_background(agent):
    start, run, tmp_path = agent
    start()
    start()

    foreground, heard = run("echo $$")
    background, heard_too = run("echo $$; sleep 0.1", background=True)

    assert (heard, heard_too) == ("", "")
    assert (tmp_path / "capped").read_text().splitlines() == [
        f"cap-shell {foreground.strip()}",
        f"cap-shell {background.strip()}",
    ]


@pytest.mark.skipif(V2, reason="cgroup v2 is mounted here")
def test_a_machine_with_no_cgroup_v2_gets_no_cap_line(agent):
    start, _run, tmp_path = agent
    start()

    assert "cap-shell" not in (tmp_path / "env").read_text()
