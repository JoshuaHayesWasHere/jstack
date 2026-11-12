"""Read what sits below a brief's head: its labelled lines, its last section of a heading, and
the lines a crew, a reviewer and jbus add as it runs, the reviewer lines, the pull request a
Result names and the gate headings. A brief's head and its sections are `jbriefs.parse`'s.

Each of these lines has its one reader here or beside it (`jbriefs.status`, `jbriefs.stacked`,
`jbriefs.checked`, the seats of `jbriefs.findings`): jbriefs, jmerge and jbus call it, and the
skills' shell blocks call it through `jbriefs line`, so no block reads a field of its own."""

from __future__ import annotations

import re
from dataclasses import dataclass

_GATE = re.compile(r"^## Gate (\S+?):\s*(.*)$")
_URL = re.compile(r"https?://[^\s)>\]`]+")
_NUMBER = re.compile(r"/pull/(\d+)/?$")


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


def last_result(text: str) -> str:
    """The brief's last `## Result` section, its heading included, to the next `## ` heading,
    or an empty string for a brief with none. A scout's request has a `## Report` in its
    place, read the same way."""
    lines = text.splitlines()
    starts = [at for at, one in enumerate(lines) if one.startswith(("## Result", "## Report"))]
    if not starts:
        return ""
    rest = lines[starts[-1] + 1 :]
    end = next((at for at, one in enumerate(rest) if one.startswith("## ")), len(rest))
    return "\n".join([lines[starts[-1]], *rest[:end]]) + "\n"


AFTER = "after the review"
"""What a Result's `Branch:` line says of a pull request that opens once its review is written."""


@dataclass(frozen=True)
class Pull:
    """What a Result's `Branch:` line, `Branch: <branch>   Pull request: <said>`, says of its
    pull request: `said`, the words after `Pull request:`, and `url`, the first address in them.
    The address may have a note after it, `(merged)`. Words that start `none`, and words with
    no address, `after the review` or `pending`, name none, and `url` is empty."""

    said: str
    url: str = ""

    @property
    def number(self) -> str:
        found = _NUMBER.search(self.url)
        return found[1] if found else ""

    @property
    def after(self) -> bool:
        return self.said == AFTER

    def shown(self) -> str:
        """The pull request as `jbriefs line pr` prints it: its address, `after the review`, or
        `none`."""
        return self.url or (AFTER if self.after else "none")


def pull(result: str) -> Pull | None:
    """What the first `Branch:` line of a Result says of its pull request, or None for a Result
    with no such line. Only that line names it: a `Done when:` or a `Proof:` line may say
    `Pull request:` of anything. A line with no `Pull request:` on it, `Branch: <branch> <url>`,
    says the words after its branch."""
    found = next((one for one in result.splitlines() if one.startswith("Branch:")), None)
    if found is None:
        return None
    before, label, said = found.removeprefix("Branch:").partition("Pull request:")
    said = said.strip() if label else " ".join(before.split()[1:])
    url = _URL.search(said) if not said.lower().startswith("none") else None
    return Pull(said, url[0].rstrip(".,;:*") if url else "")


REVIEWERS = ("Reviewer", "Second reviewer", "Scoped reviewer")


def results(brief: str) -> list[str]:
    """The brief's lines from its first `## Result` on, where a crew and a reviewer write. A
    `Reviewer:` line above it is the home's guidance for the reviewer, and no reviewer."""
    lines = brief.splitlines()
    return lines[
        next((at for at, one in enumerate(lines) if one.startswith("## Result")), len(lines)) :
    ]


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
