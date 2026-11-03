"""Read what sits below a brief's head: its labelled lines, its last section of a heading, and
the lines a crew, a reviewer and jbus add as it runs, the reviewer lines and the gate headings.
A brief's head and its sections are `jbriefs.parse`'s."""

from __future__ import annotations

import re

_GATE = re.compile(r"^## Gate (\S+?):\s*(.*)$")


def line(text: str, label: str) -> str:
    """What the first `<label>` line anywhere in the text says, or an empty string for text
    with none. A section's body is read this way, a gate inside it included."""
    for one in text.splitlines():
        if one.startswith(label):
            return one.removeprefix(label).strip()
    return ""


def last(text: str, heading: str) -> list[str] | None:
    """The lines below the last line that starts `heading`, to the end of the text, so a
    Result runs on through any Review written after it. None for text with no such line."""
    lines = text.splitlines()
    starts = [at for at, one in enumerate(lines) if one.startswith(heading)]
    return lines[starts[-1] + 1 :] if starts else None


REVIEWERS = ("Reviewer", "Second reviewer", "Scoped reviewer")


def results(brief: str) -> list[str]:
    """The brief's lines from its first `## Result` on, where a crew and a reviewer write. A
    `Reviewer:` line above it is the home's guidance for the reviewer, and no reviewer."""
    lines = brief.splitlines()
    return lines[next((at for at, one in enumerate(lines) if one.startswith("## Result")), len(lines)) :]


def reviewers(brief: str, kind: str, head: str | None = None) -> list[str]:
    """What each `<kind>:` line of the brief's results says, in order, for a kind of
    `REVIEWERS`. With `head`, only the lines that end `of <head>`, as a scoped reviewer's line
    names the head it reviews."""
    label = f"{kind}:"
    found = [one.removeprefix(label).strip() for one in results(brief) if one.startswith(label)]
    return found if head is None else [s for s in found if s.split()[-2:] == ["of", head]]


def launched(said: str) -> bool:
    """Whether a reviewer line says a reviewer was launched: it names something, and not
    `none`, as `Reviewer: none, <why>` says none runs."""
    return bool(said) and not re.match(r"none\b", said)


def gate(heading: str) -> tuple[str, str] | None:
    """The number and the question of a `## Gate <n>: <question>` heading, or None for any
    other line."""
    found = _GATE.match(heading)
    return (found[1], found[2].strip()) if found else None
