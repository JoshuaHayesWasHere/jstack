"""What a row owes and how it ended, as its brief says: `pull`, what the brief's `Pull request:`
line asks, and `read`, the `Outcome` of a row that ends with no merge.

A row whose brief asks for a pull request (`Pull request: open one`) and that closes with none
names why on one line of its last `## Result`:

- `Outcome: carried by <slug>`: the work goes on under that row, which a merge of its own ends;
- `Outcome: nothing to change, <why>`: the task found nothing to do;
- `Outcome: dropped, <why>`: the work is not wanted any more, done or not.

A row whose brief asks for none (`Pull request: none`, or no line) or asks first (`ask first`)
owes no merge, so it needs no line: its outcome is `NoPullOwed`. The pass reads this to judge a
close (`watch.closes`), `history.brief` keeps it beside `pull` in `brief-versions.jsonl`, and the
telemetry store's `row_outcomes` names each row's end by it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Pull = Literal["open", "ask", "none"]
Kind = Literal["carried", "nothing to change", "dropped"]

_OPENS = re.compile(r"^Pull request:[ \t]*open one\b", re.M)
_ASKS_FIRST = re.compile(r"^Pull request:[ \t]*ask first\b", re.M)
_CARRIED = re.compile(r"carried by `?([a-z0-9][a-z0-9._-]*)`?[.]?")
_WHY = re.compile(r"(nothing to change|dropped)[,:;][ \t]*(\S.*)")
LABEL = "Outcome:"


@dataclass(frozen=True)
class NoPullOwed:
    """The brief asks for no pull request, so its row ends with none and owes no reason."""


@dataclass(frozen=True)
class CarriedBy:
    """The work goes on under the row `slug`."""

    slug: str


@dataclass(frozen=True)
class NothingToChange:
    why: str


@dataclass(frozen=True)
class Dropped:
    why: str


Outcome = NoPullOwed | CarriedBy | NothingToChange | Dropped


def pull(text: str) -> Pull:
    """What a brief's `Pull request:` line asks, of the brief above its first `## ` section:
    `open` for `open one`, `ask` for `ask first`, and `none` for any other text or no line."""
    head = text.split("\n## ")[0]
    if _OPENS.search(head):
        return "open"
    return "ask" if _ASKS_FIRST.search(head) else "none"


def read(brief: str) -> Outcome | None:
    """How the row of `brief` ended with no merge: `NoPullOwed` where the brief asks for no pull
    request, else what the `Outcome:` line of its last `## Result` names. None where that Result
    has no such line, or one that names none of the three ends."""
    if pull(brief) != "open":
        return NoPullOwed()
    said = _line(_last_result(brief))
    if found := _CARRIED.fullmatch(said):
        return CarriedBy(found[1])
    if found := _WHY.fullmatch(said):
        why = found[2].strip()
        return NothingToChange(why) if found[1] == "nothing to change" else Dropped(why)
    return None


def kind(outcome: Outcome | None) -> Kind | None:
    """The word the store keeps for an outcome a Result names, or None for none and for
    `NoPullOwed`, which the version's `pull` already says."""
    match outcome:
        case CarriedBy():
            return "carried"
        case NothingToChange():
            return "nothing to change"
        case Dropped():
            return "dropped"
        case _:
            return None


def _last_result(brief: str) -> list[str]:
    """The lines of the brief's last `## Result` section, up to the next `## ` heading."""
    lines = brief.splitlines()
    starts = [at for at, one in enumerate(lines) if one.startswith("## Result")]
    if not starts:
        return []
    body = []
    for one in lines[starts[-1] + 1 :]:
        if one.startswith("## "):
            break
        body.append(one)
    return body


def _line(lines: list[str]) -> str:
    for one in lines:
        if one.startswith(LABEL):
            return one.removeprefix(LABEL).strip()
    return ""
