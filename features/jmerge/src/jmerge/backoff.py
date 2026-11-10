"""`jmerge` asks GitHub nothing while GitHub has told it to wait.

GitHub refuses a call for its rate limit with a 403 or a 429 (`jsettings.budget.refused`), and
asks the caller to wait: until its `retry-after` header's seconds have passed, or, where the
window is spent, until the window's reset, and at least a minute otherwise
(https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api). A caller that
asks again before then keeps the limit hot: on 2026-11-03 jmerge asked for 65 refused branch
updates in ten minutes, each one retried on every pass.

So every `gh` call of a `jmerge` run goes through one `Gate`. The first refusal sets the time
GitHub may be asked again, kept in `github-wait.json` in the project's state, beside
`base-merges.json`, so the next run and the merge tick's runs wait too. Until then a `gh` call
is not made: it fails with `WAITS` on stderr, and every caller reads that as GitHub giving no
answer. A run that starts inside the wait says `WAITS` once and asks nothing (`cli._merging`).
The refused call itself gives what `gh` said, and `gh api rate_limit`, which spends nothing, is
always asked.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from jsettings import budget, proc, store

NAME = "github-wait.json"
AT_LEAST = timedelta(minutes=1)
"""GitHub's wait for a refusal that names no time: "wait for at least one minute"."""
GH = "gh"
"""The program `Gate.run` holds to the wait. A global, not a literal in `Gate.run`:
`jsettings.proc` logs a call under the first frame whose code holds the constant `"gh"`, and that
is to be the function that built the command, not the gate it passes through."""
WAITS = f"{budget.REFUSED}, so jmerge asks GitHub nothing until {{until}}"


def is_wait(text: str) -> bool:
    """Whether `text` is the line of a call `Gate` did not make."""
    return bool(re.fullmatch(re.escape(WAITS).replace(r"\{until\}", ".+"), text.strip()))


_HEADER = re.compile(r"^([A-Za-z-]+):\s*(.*?)\s*$")


def _split(stdout: str) -> tuple[str, str]:
    """The headers `gh api --include` printed and its body: no headers where it printed no
    status line."""
    if not stdout.startswith("HTTP/"):
        return "", stdout
    parts = re.split(r"\r?\n\r?\n", stdout, maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def headers(stdout: str) -> dict[str, str]:
    """The headers `gh api --include` printed before its body, by lowercase name."""
    found = (_HEADER.match(line) for line in _split(stdout)[0].splitlines()[1:])
    return {one[1].lower(): one[2] for one in found if one}


def body(stdout: str) -> str:
    """What `gh api --include` printed after its headers, or all it printed where it printed
    none."""
    return _split(stdout)[1]


def told(said: Mapping[str, str], now: datetime) -> datetime | None:
    """The time GitHub's headers ask a refused caller to wait until, or None where they name
    none: `retry-after`, as seconds or a date, else the reset of a window with no call left."""
    after = said.get("retry-after", "")
    if after.isdigit():
        return now + timedelta(seconds=int(after))
    if after:
        try:
            return parsedate_to_datetime(after).astimezone(UTC)
        except (TypeError, ValueError):
            pass
    reset = said.get("x-ratelimit-reset", "")
    if said.get("x-ratelimit-remaining") == "0" and reset.isdigit():
        return datetime.fromtimestamp(int(reset), UTC)
    return None


class Gate:
    """The one way a `jmerge` run asks GitHub. `state` is where the wait is kept, and `keeps`
    whether this run writes it there: a `--check` run waits as any run does and writes nothing."""

    def __init__(self, state: Path | None = None, keeps: bool = False) -> None:
        self.path = None if state is None else state / NAME
        self.keeps = keeps
        self.until = self.kept()

    def kept(self) -> datetime | None:
        if self.path is None:
            return None
        try:
            return datetime.fromisoformat(str(store.read_dict(self.path).get("until")))
        except ValueError:
            return None

    def held(self, now: datetime | None = None) -> str:
        """`WAITS`, while GitHub is not to be asked, or nothing."""
        if self.until is None or (now or datetime.now(UTC)) >= self.until:
            return ""
        return WAITS.format(until=budget.at(self.until))

    def run(
        self,
        *command: str,
        cwd: Path | str | None = None,
        timeout: float | None = None,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run `command` as `proc.run` does, unless it is a `gh` call while GitHub is not to be
        asked: then it fails with `WAITS` and nothing runs. `gh api rate_limit` is always run,
        since asking it spends nothing. A call GitHub refuses for its rate limit sets the wait,
        and gives what `gh` said, so its caller names the window as before (`asked.why`)."""
        is_gh = bool(command) and Path(command[0]).name == GH and list(command) != budget.ASK
        if is_gh and (line := self.held()):
            return subprocess.CompletedProcess(command, 1, "", line)
        ran = proc.run(*command, cwd=cwd, timeout=timeout, stdin=stdin, env=env)
        if is_gh and ran.returncode and budget.refused(ran.stderr or ""):
            self.refused(headers(ran.stdout or ""), cwd, env, why=ran.stderr or "")
        return ran

    def refused(
        self,
        said: Mapping[str, str],
        cwd: Path | str | None,
        env: Mapping[str, str] | None,
        why: str,
    ) -> None:
        """Wait as GitHub's headers say, else until the reset of a window `gh api rate_limit`
        says is spent, which asking spends nothing of, and else `AT_LEAST`."""
        now = datetime.now(UTC)
        until = told(said, now)
        if until is None:
            asked = proc.run(*budget.ASK, cwd=cwd, timeout=proc.TIMEOUT, env=env)
            left = budget.given(asked)
            until = left.low.reset if left is not None and left.is_spent else None
        if until is None or until <= now:
            until = now + AT_LEAST
        self.until = max(until, self.until or until)
        if self.keeps and self.path is not None and self.path.parent.is_dir():
            first = next((line for line in why.splitlines() if line.strip()), "")
            record = {"until": self.until.isoformat(), "at": now.isoformat(), "why": first}
            store.write_json(self.path, record)


gate = Gate()
"""The run's gate: one that holds nothing until `watch` names the project's state."""


def watch(state: Path, keeps: bool) -> Gate:
    """Make `gate` the one of the project whose state is `state`, and return it."""
    global gate
    gate = Gate(state, keeps)
    return gate


def run(*command: str, **how) -> subprocess.CompletedProcess[str]:
    """Run `command` through the run's gate (`Gate.run`)."""
    return gate.run(*command, **how)
