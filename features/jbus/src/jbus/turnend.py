"""`jbus told <home directory>`: the end of a home's turn, which tells the user only what is theirs.

A home writes what its turn did on stdin, one line each, its kind first: `decision <key>: ...` or
`stop <key>: ...` asks the user, `merged:`, `launched:`, `handled:`, `parked:` and `waits:` are
told on status only, and `cleared local <slug>: ...` ends the `local` decisions and stops of that
slug. A key is `question <n>`, `local <slug>` or `jbus`, and a `jbus` line's key is the whole line,
since it is jbus's event word for word.

`told` in the home's directory keeps each decision and stop told, one a line, so that each key is
told once. The status block of the home skill shows its `local` lines until a `cleared` line ends
them. The verb prints `say: <line>` for each line whose key is new, in its order, or one `silent:`
line when there is none. A line it cannot read is refused with a `refused:` line that names it, it
exits 2, and nothing is marked told. The rules are the home skill's "How a turn ends".
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import jbus
from jbus import verbs

FILE = "told"
REFUSED = 2
SILENT = "silent: end the turn with no message"
QUIET = ("merged:", "launched:", "handled:", "parked:", "waits:")
KEYED = re.compile(r"^(decision|stop) (question [0-9]+|local [^ :]+|jbus): .")
CLEARED = re.compile(r"^cleared local ([^ :]+): .")
NO_KEY = "a decision or a stop names its key first: question <n>, jbus or local <slug>"
NO_KIND = (
    "its kind is none of decision, stop, merged, launched, handled, parked, waits, "
    "cleared local <slug>"
)


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("home", metavar="directory", help="the home's directory, $M")


def key(line: str) -> str | None:
    """The key a decision or a stop is told once by, or None for a line that names none."""
    found = KEYED.match(line)
    if found is None:
        return None
    return line if found[2] == "jbus" else found[0][:-3]


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
    told = Path(args.home) / FILE
    kept = [line for line in _lines(told) if key(line)]
    ends: set[str] = set()
    mine: list[str] = []
    bad: list[str] = []
    for line in verbs.piped("told", "the turn's lines", " <home directory>").splitlines():
        words = line.split()
        if not words or words[0] in QUIET:
            continue
        if words[0] == "cleared" and (cleared := CLEARED.match(line)):
            ends.add(cleared[1])
        elif re.fullmatch(r"(decision|stop):?", words[0]) is None:
            bad.append(f"{line}: {NO_KIND}")
        elif key(line) is None:
            bad.append(f"{line}: {NO_KEY}")
        else:
            mine.append(line)
    if bad:
        print("\n".join(f"refused: {why}" for why in bad))
        return REFUSED
    still = [line for line in kept if not (line.split()[1] == "local" and _slug(line) in ends)]
    seen = {key(line) for line in still}
    tell = []
    for line in mine:
        if key(line) not in seen:
            seen.add(key(line))
            tell.append(line)
    if tell or len(still) < len(kept):
        new = told.with_name(f"{FILE}.new")
        new.write_text("".join(f"{line}\n" for line in [*still, *tell]))
        os.replace(new, told)
    print("\n".join(f"say: {line}" for line in tell) or SILENT)
    return 0


def _lines(told: Path) -> list[str]:
    try:
        return told.read_text().splitlines()
    except FileNotFoundError:
        return []


def _slug(line: str) -> str:
    """The slug of a `local` line, `x` of `stop local x: ...`."""
    return line.split()[2][:-1]


VERBS = (
    verbs.Verb(
        "told",
        "end a home's turn: say each decision and stop not told before, and keep it in told",
        _arguments,
        _run,
        config=False,
    ),
)
