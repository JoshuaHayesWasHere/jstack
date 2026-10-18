"""What `gh` said when it was asked and gave no answer, as the text a line about it ends on.

`jmerge` and `jbus` both stop and wait when GitHub cannot be asked, and both print the line
and log it, so the text is cut of what must not be kept there: a token, and the query of a
URL, which is where `gh` puts one. It is one line, of at most `LIMIT` characters.
"""

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
    """The text on one line with its tokens and URL queries taken out, and at most `LIMIT` long."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    plain = _CONTROL.sub(" ", _QUERY.sub(r"\1", _TOKEN.sub("[redacted]", first))).strip()
    return plain if len(plain) <= LIMIT else plain[: LIMIT - 3].rstrip() + "..."


def why(ran: subprocess.CompletedProcess[str], said: str = "") -> str:
    """` gh exited <code>: <what it said>` for a `gh` that gave no answer to use, to end a line on.

    A `gh` that failed gave its first line of stderr. One that exited 0 gave output that could
    not be used, and `said` names what was wrong with it where that is not that it was no JSON.
    """
    if ran.returncode == 0:
        return f": gh exited 0: {said or NOT_JSON}"
    return f": gh exited {ran.returncode}: {cut(ran.stderr or '') or NOTHING}"


class Silent(Exception):
    """GitHub gave no answer to use. The message is `why`: what ends the line that says so."""
