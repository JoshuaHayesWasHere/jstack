"""What a CI job's log says failed: `failed_in` reads the failed tests off the log's text, and
`plain` takes the log's colour out.

`jbus.watch` fetches the log and `jmerge` reads its own, and both read it here. jbus imports it
from `jmerge`, which imports nothing of jbus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FAILED_TEST = re.compile(r"\b(?:FAILED|ERROR) (\S+::\S+)")
_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_STAMP = r"^(?:\S+Z )?"
_STEP_COUNT = re.compile(_STAMP + r"(?:##\[warning\]|::warning::).*?\b(\d+) tests? failed\b", re.M)
_STEP_TEST = re.compile(_STAMP + r"FAILED (\S.*?)\s*$", re.M)
_SUMMARY = re.compile(_STAMP + r"=+ (.*\bin [0-9.]+s\b.*?) =+\s*$", re.M)
_SUMMARY_COUNT = re.compile(r"(\d+) (?:failed|errors?)\b")


@dataclass(frozen=True)
class Failed:
    """The tests a job's log reports as failed: `tests` their ids, in order, and `count` how many
    failed, more than the ids where the log counts failures it does not name."""

    tests: tuple[str, ...] = ()
    count: int = 0


def plain(log: str) -> str:
    """Return a job's log without its escape sequences, which colour it in a terminal."""
    return _ESCAPE.sub("", log)


def failed_in(log: str) -> Failed:
    """Return the failed tests a job's log reports. A step that prints a warning `<n> tests
    failed` and then a `FAILED <id>` line for each (macos-nightly.yml's "failed tests") names them
    whole. Where it names none, the ids are pytest's summary lines. The count is the largest of
    the step's, the ids' and pytest's last line's failed plus errors."""
    log = plain(log)
    steps = list(_STEP_COUNT.finditer(log))
    tests = _STEP_TEST.findall(log, steps[-1].end()) if steps else []
    count = int(steps[-1][1]) if steps else 0
    tests = tests or _FAILED_TEST.findall(log)
    summaries = _SUMMARY.findall(log)
    if summaries:
        count = max(count, sum(int(n) for n in _SUMMARY_COUNT.findall(summaries[-1])))
    named = tuple(dict.fromkeys(tests))
    return Failed(named, max(count, len(named)))
