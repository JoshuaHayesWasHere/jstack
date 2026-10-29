"""How `jmerge` and jbus say that `gh` gave no answer: its exit code and the first line of its
stderr, with tokens and URL queries cut out, or, for a call GitHub refused for its rate limit,
the window and when it starts again (`jsettings.budget`)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from jsettings import budget

LIMIT = 160
NOTHING = "it said nothing"
NOT_JSON = "its output was not JSON"

_TOKEN = re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]*")
_QUERY = re.compile(r"(https?://[^\s?#\"'<>)]*)\?[^\s\"'<>)]*")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def cut(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    plain = _CONTROL.sub(" ", _QUERY.sub(r"\1", _TOKEN.sub("[redacted]", first))).strip()
    return plain if len(plain) <= LIMIT else plain[: LIMIT - 3].rstrip() + "..."


Ask = Callable[..., subprocess.CompletedProcess[str]]
"""Run a command, as `ask(*command)`, and return how it ran."""


def why(ran: subprocess.CompletedProcess[str], ask: Ask, said: str = "") -> str:
    """Why `ran` gave no answer, after a colon. A refusal for the rate limit asks `gh api
    rate_limit` with `ask`, which spends nothing, and names the window in place of the stderr."""
    if ran.returncode == 0:
        return f": gh exited 0: {said or NOT_JSON}"
    if budget.refused(ran.stderr or ""):
        return f": {budget.named(ask(*budget.ASK))}"
    return f": gh exited {ran.returncode}: {cut(ran.stderr or '') or NOTHING}"


class Silent(Exception):
    pass
