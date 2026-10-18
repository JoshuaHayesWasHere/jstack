"""Which briefs still hold the files on their `Where:` line, for a home to read before a launch.

This is the one copy of the rules. They are read from a brief, from the pull requests GitHub
lists as open, and from the homes this repo has; nothing here runs a command.
"""

from __future__ import annotations

from dataclasses import dataclass

from jbriefs import parse
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


def _last_result(text: str) -> list[str]:
    """The lines from the brief's last `## Result` heading on, or none for a brief with none."""
    lines = text.splitlines()
    last = [at for at, line in enumerate(lines) if line.startswith("## Result")]
    return lines[last[-1] :] if last else []


def _wider(text: str) -> dict[str, str]:
    """The files the last Result gives a reason for, by their `Wider: <path>: <why>` lines."""
    found: dict[str, str] = {}
    for line in _last_result(text):
        path, _, why = line.removeprefix("Wider:").partition(":")
        path = path.strip().strip("`")
        if line.startswith("Wider:") and path and not path.startswith("<") and why.strip():
            found[path] = why.strip()
    return found


def branch_of(slug: str, text: str) -> tuple[str, str]:
    """The branch the last Result names, or the slug before there is a Result, and its pull
    request's url, or nothing for a Result that opened none."""
    for line in _last_result(text):
        if line.startswith("Branch:"):
            words = line.removeprefix("Branch:").split()
            pull = next((word for word in words if word.startswith("http")), "")
            return (words[0] if words else slug), pull
    return slug, ""


def stacked_on(text: str) -> str:
    """The branch a link of a stack sits on, from `Stack: <name> <place> on <branch>` in the
    brief's head, or nothing for a brief that is no link."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Stack:"):
            words = line.removeprefix("Stack:").split()
            return words[-1] if len(words) == 4 and words[2] == "on" else ""
    return ""


def scope(text: str, changed: list[str]) -> list[str]:
    """One line for each changed file the brief's `Where:` does not cover, in `changed`'s order.

    `outside: <path>` is a file nothing covers. `wider: <path>: <why>` is one the last
    Result's `Wider: <path>: <why>` line gives a reason for. A file inside is not printed.
    """
    inside, wider = parse.where(text), _wider(text)
    return [
        f"wider: {path}: {wider[path]}" if path in wider else f"outside: {path}"
        for path in changed
        if not parse.covers(inside, path)
    ]


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
