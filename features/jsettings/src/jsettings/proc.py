"""The one runner of a command, `git` and `gh` included, for every command of jstack.

`run` never raises for the command: a program that is missing, or that runs past its `timeout`,
fails like any other, with exit 127 and the error as what it said on stderr. Such a run is an
`Unrun`, and one past its `timeout` a `TimedOut`, for a caller that says so in words of its own.
`ask` is a read: it gives what the command printed, or None where it failed. `git` runs git in a
directory. What is left of GitHub's API allowance, and the floor jbus keeps under it, is
`jsettings.budget`.

Every `gh` that `run` starts takes one of `GH_CAP` slots, shared by every process on the machine
through a lock file each under jbus's state (`SLOTS`), and waits while all are taken. Each writes
one line to `CALLS` there: when it ended, its caller, the endpoint, its exit status, and the
`X-Ratelimit-Remaining` and `Retry-After` GitHub gave. gh says them only in its debug log
(`GH_DEBUG=api`), so `run` asks for it and takes it out of what gh said on stderr: a caller sees
gh's own words only. `jbus budget --callers` counts the lines.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

TIMEOUT = 30
"""The seconds `ask` waits for a read before it counts the read as failed."""

GH_CAP = 16
"""The `gh` processes that may run at one moment, across every project and process."""
SLOTS = "gh-slots"
CALLS = "gh-calls.jsonl"
KEPT = 16 * 2**20
"""The bytes `CALLS` grows to before it becomes `gh-calls.old.jsonl`, and a new one starts."""
WAIT = 0.05

WRAPPERS = frozenset(
    {"jbus.passes.Pass.run", "jbus.watch._api", "jbus.watch.job_log", "jbus.watch._log_failed"}
)
"""The functions that only pass a call on: a call's caller is the first frame above them."""


class Unrun(subprocess.CompletedProcess[str]):
    """A run that never ran to its end: the program could not be started, or it was stopped."""


class TimedOut(Unrun):
    """A run that went past its timeout and was stopped."""


def run(
    *command: str,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
    errors: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the command in `cwd` and return what it did, its output as text, decoded with
    `errors` as `open` takes it. A `gh` waits for a slot and is logged."""
    if not command or Path(command[0]).name != "gh":
        return _run(command, cwd, timeout, stdin, env, errors)
    from jsettings import paths

    state = paths.jbus_state_dir()
    caller = _caller()
    began = time.monotonic()
    with _slot(state / SLOTS):
        waited = time.monotonic() - began
        done = _run(
            command, cwd, timeout, stdin, {**(env or os.environ), "GH_DEBUG": "api"}, errors
        )
    said = Debug.parse(done.stderr or "")
    done.stderr = said.stderr
    _log(state, command, caller, done.returncode, said, waited)
    return done


def _run(
    command: tuple[str, ...],
    cwd: Path | str | None,
    timeout: float | None,
    stdin: str | None,
    env: Mapping[str, str] | None,
    errors: str | None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            input=stdin,
            timeout=timeout,
            env=None if env is None else dict(env),
            errors=errors,
        )
    except subprocess.TimeoutExpired as error:
        return TimedOut(command, 127, "", str(error))
    except OSError as error:
        return Unrun(command, 127, "", str(error))


@contextlib.contextmanager
def _slot(where: Path) -> Iterator[None]:
    """Hold one of `GH_CAP` lock files in `where` while the block runs, waiting while all are
    held. The kernel lets a slot go when its holder ends, however it ends."""
    where.mkdir(parents=True, exist_ok=True)
    while True:
        for number in range(GH_CAP):
            with open(where / str(number), "a") as held:
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                yield
                return
        time.sleep(WAIT)


def _caller() -> str:
    """The module and function that asked for the call: the first frame outside this module and
    the `WRAPPERS`."""
    frame = sys._getframe(1)
    while frame.f_back is not None and (
        frame.f_globals.get("__name__") == __name__
        or f"{frame.f_globals.get('__name__')}.{frame.f_code.co_qualname}" in WRAPPERS
    ):
        frame = frame.f_back
    return f"{frame.f_globals.get('__name__')}.{frame.f_code.co_qualname}"


@dataclass(frozen=True)
class Debug:
    """What gh's debug log (`GH_DEBUG=api`) said of a call's requests, and `stderr`, what gh said
    on stderr without it. `requests` is each request's URL, `http` the last response's status
    line, `remaining` and `retry` the last `X-Ratelimit-Remaining` and `Retry-After` given."""

    stderr: str
    requests: tuple[str, ...] = ()
    http: str = ""
    remaining: int | None = None
    retry: str = ""

    @classmethod
    def parse(cls, stderr: str) -> Debug:
        """Read gh's stderr. Each request's log runs from `* Request at` to `* Request took`;
        what is outside is gh's own. A log cut off before its end keeps no header and no body,
        and gives back the lines that are neither, such as why the request failed."""
        kept: list[str] = []
        block: list[str] | None = None
        requests: list[str] = []
        http, remaining, retry = "", None, ""
        for line in stderr.splitlines(keepends=True):
            if line.startswith("* Request at "):
                block = []
                continue
            if block is None:
                kept.append(line)
                continue
            if line.startswith("* Request took "):
                block = None
                continue
            block.append(line)
            header = line.rstrip("\r\n")
            name, _, value = header[2:].partition(":")
            if header.startswith("* Request to "):
                requests.append(header.removeprefix("* Request to "))
            elif header.startswith("< HTTP/"):
                http = header[2:]
            elif header.startswith("< ") and name.lower() == "x-ratelimit-remaining":
                with contextlib.suppress(ValueError):
                    remaining = int(value)
            elif header.startswith("< ") and name.lower() == "retry-after":
                retry = value.strip()
        if block is not None:
            kept.extend(one for one in block if one.strip() and one[:2] not in ("* ", "> ", "< "))
        return cls("".join(kept), tuple(requests), http, remaining, retry)


def _endpoint(command: tuple[str, ...], said: Debug) -> str:
    """The first request's path, or the gh command's words before its first flag where gh made
    no request it logged."""
    if said.requests:
        url = urlsplit(said.requests[0])
        return url.path + (f"?{url.query}" if url.query else "")
    words = []
    for word in command[1:]:
        if word.startswith("-"):
            break
        words.append(word)
    return " ".join(words[:2])


def _log(
    state: Path, command: tuple[str, ...], caller: str, status: int, said: Debug, waited: float
) -> None:
    """Write the call's line to `CALLS`, in one append, so that lines from many processes never
    mix. A log that cannot be written costs the call nothing."""
    line = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "caller": caller,
        "endpoint": _endpoint(command, said),
        "status": status,
        "remaining": said.remaining,
    }
    if said.retry:
        line["retry_after"] = said.retry
    if said.http:
        line["http"] = said.http
    if len(said.requests) > 1:
        line["requests"] = len(said.requests)
    if waited >= WAIT:
        line["waited"] = round(waited, 2)
    path = state / CALLS
    with contextlib.suppress(OSError):
        if path.stat().st_size > KEPT:
            os.replace(path, state / f"{Path(CALLS).stem}.old.jsonl")
    with contextlib.suppress(OSError), open(path, "a") as log:
        log.write(json.dumps(line) + "\n")


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
