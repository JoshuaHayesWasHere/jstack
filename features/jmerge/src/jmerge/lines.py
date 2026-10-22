"""The lines that `jmerge` prints about a pull request, and the one parser of them.

`jmerge` prints each line with a formatter here (`waits`, `merged`, `ready`), and jbus reads
them back with `parse`, or `one` for a single line, so a printer and its reader cannot drift
apart. A line with no number after its word, such as `wait: could not ask GitHub`, is about
no pull request, and `parse` skips it.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

Word = Literal["merged", "wait", "hold", "refused"]
LINE = re.compile(r"^(merged|wait|hold|refused) (\d+)\b(?: (\S+)(?: (.+))?)?")
READY = re.compile(r"^ready (\d+) \S+ .*?, (safe because .+ \(proven at [0-9a-f]+\))$")
GATE_OK = "gate: ok"


@dataclass(frozen=True)
class Line:
    """A line that `jmerge` prints about a pull request: `<word> <number> <name>: <reason>`.

    `word` is `merged`, `wait` or `hold`, or the `refused` of an accept. `name` is the word
    after the number, which is the pull request's URL or the merged slug with no comma after
    it. `reason` is what follows the colon. A line with no name has neither field, and a
    line with no colon has no reason.
    """

    word: Word
    number: int
    name: str = ""
    reason: str = ""


def one(text: str) -> Line | None:
    """The `Line` that a line of `jmerge` is, or nothing where the line is not about a pull
    request."""
    found = LINE.match(text.strip())
    if not found:
        return None
    word, number, name, rest = found.groups()
    word = cast(Word, word)
    if rest and len(name) > 1 and name.endswith(":"):
        return Line(word, int(number), name[:-1], rest)
    return Line(word, int(number), (name or "").rstrip(","))


def parse(text: str) -> list[Line]:
    """The `Line` of each line of `text` that is about a pull request, in order."""
    return [line for line in map(one, text.splitlines()) if line]


def waits(verb: Literal["wait", "hold"], number: int, url: str, why: str) -> str:
    """The line of a pull request that does not merge on this run, and why."""
    return f"{verb} {number} {url}: {why}"


def merged(number: int, slug: str, commit: str, title: str, notes: Sequence[str], url: str) -> str:
    """The line of a pull request that this run merged, with how to revert it at the end."""
    revert = f"revert: gh pr revert {shlex.quote(url)}"
    return ", ".join([f'merged {number} {slug} {commit} "{title}"', *notes, revert])


def ready(number: int, head: str, branch: str, slug: str, notes: Sequence[str]) -> str:
    """The line of a pull request that `--check` finds would merge, with what it notes."""
    return ", ".join([f"ready {number} {head} {branch} {slug}", *filter(None, notes)])


NOT_REINSTALLED = "the tool {tool} was not reinstalled after its package list changed ({why})"
NOT_INSTALLED = "the install was not run again after the merge changed what it assembles ({why})"
UNFOLLOWED = re.compile(
    "|".join(
        re.escape(note).replace(r"\{tool\}", r"\S+").replace(r"\{why\}", ".*?") + "(?=, )"
        for note in (NOT_REINSTALLED, NOT_INSTALLED)
    )
)


def reinstalled(tool: str, main: object) -> str:
    """The note of a merge after which `jmerge` installed the tool again from the main checkout."""
    return f"reinstalled the tool {tool} from {main}: its package list changed"


def not_reinstalled(tool: str, why: str) -> str:
    """The note of a merge that moved a package of the tool, after which the tool could not be
    installed again. Every command of the tool may fail on an import until it is."""
    return NOT_REINSTALLED.format(tool=tool, why=why)


def installed(main: object) -> str:
    """The note of a merge after which the install ran again in the main checkout."""
    return f"ran the install again in {main}: the merge changed what it assembles"


def not_installed(why: str) -> str:
    """The note of a merge that changed what the install assembles, after which the install
    failed. Until the install runs again, a skill that the merge moved or removed may be
    linked to a file that no longer exists."""
    return NOT_INSTALLED.format(why=why)


def unfollowed(text: str) -> str:
    """The `not_reinstalled` and `not_installed` notes of a `merged` line, or nothing where
    the line has neither."""
    return "; ".join(found[0] for found in UNFOLLOWED.finditer(text))
