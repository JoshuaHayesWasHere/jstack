"""The last two steps of an answer before the server sends it: cut it to a shape, and clean it.

`keep` cuts a value to a shape, a fixed list of keys. It leaves out each key the shape does
not name, whatever value a file has under it. `clean` then goes through every string that is
left. A URL stays only when it is a pull request or a workflow run of one of the repos
given, and `clean` turns any other URL into `LINK`. Text with the shape of a token becomes
`jbus.REDACTED`. A token's shape counts only where it starts a word, so `task-...` is no
`sk-` key. The text after a word such as `key=` becomes `jbus.REDACTED` too. So does the
text after a word such as `Authorization:`, when that text is one run of 16 or more of the
characters a key is written in. A word of prose is never such a run.

Neither function knows a secret. To read, the server reads no config, so it cannot take a
webhook's key out by name as `jbus.redact` does. Two things keep a key out of an answer:
the server reads no file that holds one, and an answer has only the keys of its shape. The
one write that loads the config takes the config's secrets out by name from what that write
returns, before this module sees it.
"""

from __future__ import annotations

import re
from typing import Any

from jbus import REDACTED

HOST = "github.com"
LINK = "[link]"
ANY = "*"
_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s\"'<>`]+", re.I)
_END = ".,;:!?)]}"
_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abeoprs]-[A-Za-z0-9-]{10,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"
    r"|A[KS]IA[A-Z0-9]{16}"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{8,}"
    r")"
)
_NAMED = r"(?i)\b([\w-]*(?:key|token|secret|password|passwd|authorization)\b\"?\s*{sign}\s*\"?)"
_ASSIGNED = re.compile(_NAMED.format(sign="=") + r"(?!\[redacted\])[^\s\"',;]{6,}")
_SAID = re.compile(_NAMED.format(sign=":") + r"(?!\[redacted\])[A-Za-z0-9._~+/=-]{16,}(?![\w:])")
Shape = Any


def allowed(repos: tuple[str, ...]) -> re.Pattern[str]:
    """The pattern a whole URL must match to stay: a pull request or a run of one of the repos."""
    named = "|".join(re.escape(repo) for repo in repos if repo) or "(?!)"
    kinds = r"pull/\d+|actions/runs/\d+(?:/job/\d+)?"
    return re.compile(rf"https://{re.escape(HOST)}/(?:{named})/(?:{kinds})")


def _text(text: str, stays: re.Pattern[str]) -> str:
    def link(found: re.Match[str]) -> str:
        url = found[0].rstrip(_END)
        return (url if stays.fullmatch(url) else LINK) + found[0][len(url) :]

    text = _TOKEN.sub(REDACTED, _URL.sub(link, text))
    for named in (_ASSIGNED, _SAID):
        text = named.sub(lambda found: found[1] + REDACTED, text)
    return text


def clean(value: Any, repos: tuple[str, ...]) -> Any:
    """The value with every string cleaned, the keys of its dicts included."""
    stays = allowed(repos)

    def walk(one: Any) -> Any:
        if isinstance(one, str):
            return _text(one, stays)
        if isinstance(one, list):
            return [walk(each) for each in one]
        if isinstance(one, dict):
            return {walk(key): walk(each) for key, each in one.items()}
        return one

    return walk(value)


def keep(value: Any, shape: Shape) -> Any:
    """The value cut to the shape.

    A shape has one of three forms. It is `None` for a value with no dict or list in it. It
    is a dict of each key to keep, with that key's own shape, where the key `ANY` stands for
    every key. It is a list of one shape, which each item takes. A value that does not match
    its shape becomes `None`.
    """
    if shape is None:
        return value if isinstance(value, str | int | float | bool) else None
    if isinstance(shape, list):
        return [keep(one, shape[0]) for one in value] if isinstance(value, list) else None
    if not isinstance(value, dict):
        return None
    if ANY in shape:
        return {key: keep(one, shape[ANY]) for key, one in value.items() if isinstance(key, str)}
    return {key: keep(value[key], inner) for key, inner in shape.items() if key in value}
