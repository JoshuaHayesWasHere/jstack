"""A brief's `Checked:` line, the desk proof the crew's check block writes:
`Checked: <command> exit <n> at <head>`. `jmerge` binds a merge to the last one
(`ready.short_on_checked`), and jbus launches the review at its head (`jbus.review.desk_head`):
both read it here, so they name the same line and the same head.

Only a line in that shape is one, read whole: a line with a note after its head, as a crew once
wrote `..., and after merging main the guards passed at <commit>`, names no check, since the
note's commit is no head the command ran at, and the line before it is the last one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LINE = "Checked:"
_ONE = re.compile(r"Checked: (.+) exit (\d+) at ([0-9a-f]{40})")
_TWO_STEP = re.compile(
    r"Checked: (make check-fast BASE=([0-9a-f]{40})(?: PYTEST=:)? PART=guards) exit (\d+) "
    r"\(took \d+ s\), then the import-reached remainder, where exit 124 is the short lane's "
    r"time limit and passes: make check-fast BASE=\2 PART=rest exit (\d+) at ([0-9a-f]{40})"
)
"""The two-step line the crew's check block once wrote: the guards in a full test slot, then the
rest the change reaches in the short lane, whose 124 is that lane's time limit and passes, since
CI's check runs the rest in full."""


@dataclass(frozen=True)
class Checked:
    """The command a `Checked:` line names, its exit and the head it ran at."""

    command: str
    exit: str
    head: str


def read(line: str) -> Checked | None:
    """The check one line names, or None for a line that is no `Checked:` line in its shape. A
    two-step line (`_TWO_STEP`) reads as its guards: their exit where it is not 0, and else 0
    where the rest exited 0 or the short lane's 124, the rest's exit where it is another."""
    two = _TWO_STEP.fullmatch(line.strip())
    if two:
        guards, _, first, rest, at = two.groups()
        return Checked(guards, rest if first == "0" and rest not in ("0", "124") else first, at)
    one = _ONE.fullmatch(line.strip())
    return Checked(one[1], one[2], one[3]) if one else None


def last(text: str) -> Checked | None:
    """The check the brief's last `Checked:` line in its shape names, or None for a brief with
    none."""
    found = [said for line in text.splitlines() if (said := read(line))]
    return found[-1] if found else None
