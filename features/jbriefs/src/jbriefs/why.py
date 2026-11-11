"""A brief's `Why:` line, as a check of its fields (`jbriefs.parse.fields`).

`Why:` says why the change is wanted: the problem, the evidence that it happens, and what goes
better once it lands. The title and `Task:` already say what is asked, so a `Why:` with no word
beyond theirs says nothing a crewmate can make a choice by. `parse.faults` runs this when a row
is first queued, after it has refused a missing or empty line (`parse._filled`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

Fields = Iterable[tuple[str, list[str]]]

FILLER = frozenset(
    "a an the of to in on at for by with is are was be been it its that this as from so then "
    "there and or but because since we our us i you they it's need needs needed want wants "
    "wanted asked asks ask user users".split()
)
_WORD = re.compile(r"[\w./-]+")


def _words(lines: list[str]) -> set[str]:
    said = " ".join(lines).lower().replace("’", "'")
    found = (word.strip("./-'") for word in _WORD.findall(said))
    return {word for word in found if word and word not in FILLER}


def fault(fields: Fields) -> str:
    """Why the brief's `Why:` line is at fault, as one line, or an empty string when it is not.

    It is at fault when each of its words, less `FILLER`, is a word of the title or of `Task:`:
    it only says again what is asked. A missing or empty `Why:` is `parse._filled`'s to name.
    """
    held = list(fields)
    said = _words(next((lines for name, lines in held if name == "Why"), []))
    asked = set().union(*(_words(lines) for name, lines in held if name in ("title", "Task")))
    if said and said <= asked:
        return (
            "brief's Why: line only repeats its title and Task: say why the change is wanted, "
            "the problem, the evidence that it happens (a run, a count or the user's words) and "
            "what goes better once it lands"
        )
    return ""
