"""The one runner of a command, `git` and `gh` included, for every command of jstack.

`run` never raises for the command: a program that is missing, or that runs past its `timeout`,
fails like any other, with exit 127 and the error as what it said on stderr. A run past its
`timeout` is a `TimedOut`, for a caller that says so in words of its own. `ask` is a read: it
gives what the command printed, or None where it failed. `git` runs git in a directory. What is
left of GitHub's API allowance, and the floor jbus keeps under it, is `jsettings.budget`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

TIMEOUT = 30
"""The seconds `ask` waits for a read before it counts the read as failed."""


class TimedOut(subprocess.CompletedProcess[str]):
    """A run that went past its timeout and was stopped."""


def run(
    *command: str,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the command in `cwd` and return what it did, its output as text."""
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            input=stdin,
            timeout=timeout,
            env=None if env is None else dict(env),
        )
    except subprocess.TimeoutExpired as error:
        return TimedOut(command, 127, "", str(error))
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def ask(
    command: list[str] | tuple[str, ...],
    cwd: Path | str | None = None,
    timeout: float = TIMEOUT,
) -> str | None:
    """Run a command that reads and return what it printed, or None where it failed."""
    done = run(*command, cwd=cwd, timeout=timeout)
    return done.stdout if done.returncode == 0 else None


def git(
    cwd: Path | str | None, *args: str, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git with `args` in `cwd`, this process's own directory when it is None."""
    return run("git", *args, cwd=cwd, timeout=timeout)
