from __future__ import annotations

import re
import subprocess

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


def why(ran: subprocess.CompletedProcess[str], said: str = "") -> str:
    if ran.returncode == 0:
        return f": gh exited 0: {said or NOT_JSON}"
    return f": gh exited {ran.returncode}: {cut(ran.stderr or '') or NOTHING}"


class Silent(Exception):
    pass
