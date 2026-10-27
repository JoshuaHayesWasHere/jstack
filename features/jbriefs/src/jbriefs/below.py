"""Read what sits below a brief's head: its labelled lines, its last section of a heading, and
the lines a crew, a reviewer and jbus add as it runs, the reviewer lines, the `Rebase:` lines and
the gate headings. A brief's head and its sections are `jbriefs.parse`'s."""

from __future__ import annotations

import re

_REBASE = re.compile(
    r"^Rebase: patch (?P<how>unchanged|changed in .+), before (?P<before>[0-9a-f]{40}), "
    r"head (?P<head>[0-9a-f]{40})$",
    re.MULTILINE,
)
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


def reviewers(brief: str, kind: str, head: str | None = None) -> list[str]:
    """What each `<kind>:` line of the brief says, in order, for a kind of `REVIEWERS`. With
    `head`, only the lines that end `of <head>`, as a scoped reviewer's line names the head it
    reviews."""
    label = f"{kind}:"
    found = [one.removeprefix(label).strip() for one in brief.splitlines() if one.startswith(label)]
    return found if head is None else [s for s in found if s.split()[-2:] == ["of", head]]


def launched(said: str) -> bool:
    """Whether a reviewer line says a reviewer was launched: it names something, and not
    `none`, as `Reviewer: none, <why>` says none runs."""
    return bool(said) and not re.match(r"none\b", said)


def rebases(brief: str) -> list[tuple[bool, str, str]]:
    """Each `Rebase:` line of the brief, in order: whether the rebase changed the patch, the
    head before it and the head after it."""
    return [(m["how"] != "unchanged", m["before"], m["head"]) for m in _REBASE.finditer(brief)]


def gate(heading: str) -> tuple[str, str] | None:
    """The number and the question of a `## Gate <n>: <question>` heading, or None for any
    other line."""
    found = _GATE.match(heading)
    return (found[1], found[2].strip()) if found else None
