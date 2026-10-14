"""Which briefs still hold the files on their `Where:` line, for a home to read before a launch.

This is the one copy of the rules. They are read from a brief, from the pull requests GitHub
lists as open, and from the homes this repo has; nothing here runs a command.
"""

from __future__ import annotations

from dataclasses import dataclass

from jmerge import ready, sweep

ROOT = "root"
NOT_LAUNCHED = "not launched"
OUT = "out"
NO_WHERE = "no Where line"


@dataclass(frozen=True)
class Claim:
    """One brief whose task is not finished, and what it may still change."""

    slug: str
    state: str
    home: str
    where: str

    def line(self) -> str:
        return f"{self.slug} {self.state} {self.home} {self.where}"


def _where(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Where:"):
            return line.strip()
    return NO_WHERE


def home_of(text: str, homes: dict[str, str]) -> str:
    """The name of the home a brief is, by its `Home:` line: `ROOT` or a scope's name.

    The line is one of three kinds. None: the root's. A scope's name, which is what a
    scoped home writes: that scope's. A thread id, in a brief written before a home wrote
    its scope there: the home `homes` has for it, which gives a home's name by its thread
    id and by its directory. A line that names no home of this repo is the root's too: a
    thread that never was one, or a directory that is no scope. No brief is left to a home
    nobody runs.
    """
    return homes.get(ready.home_of(text), ROOT)


def of_brief(
    slug: str, text: str, open_pulls: dict[str, int], homes: dict[str, str]
) -> Claim | None:
    """The brief's claim, or nothing: its last Result names no pull request that is open.

    That is a task merged, closed, ended with no pull request, or folded into another brief.
    A task paused before its pull request has not ended, and still holds its files.
    `homes` gives a home's name by its thread id and by its directory.
    """
    record = sweep.of_brief(slug, text)
    if not any(line.startswith("## Result") for line in text.splitlines()):
        state = OUT if record.thread else NOT_LAUNCHED
    elif record.pull in open_pulls:
        state = f"pull request {open_pulls[record.pull]}"
        if record.paused:
            state = f"{sweep.PAUSED} {state}"
    elif record.paused and not record.pull:
        state = sweep.PAUSED
    else:
        return None
    return Claim(slug, state, home_of(text, homes), _where(text))
