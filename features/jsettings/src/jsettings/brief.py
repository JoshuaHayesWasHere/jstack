"""The reader of a brief's head, which every command shares: the lines the home wrote above the
brief's first `## ` heading, before any Result or Review.

`head_lines` gives those lines and `head` what the first of them with a label says. What a line
means is its reader's: `jbriefs.parse` judges each line of a brief, and each command reads the
lines it acts on through `head`. `page` reads a scout's Report for the page it names.
"""

from __future__ import annotations

import re

HEADING = "## "


def head_lines(text: str) -> list[str]:
    """The lines of a brief above its first `## `: what the home wrote, with no result."""
    lines = []
    for line in text.splitlines():
        if line.startswith(HEADING):
            break
        lines.append(line)
    return lines


def head(text: str, label: str) -> str | None:
    """What the first `<label>` line of a brief's head says, or None for a head with none."""
    for line in head_lines(text):
        if line.startswith(label):
            return line.removeprefix(label).strip()
    return None


def page(report: str) -> str:
    """Return what a scout's Report says after its last `Page:`, or nothing when the Report names
    no page.

    `Page: none` names no page, and neither does `Page: none, <why>`. `jmerge --sweep` and the
    scout skill's own settle block read the line the same way.
    """
    named = [
        line.split("Page:", 1)[1].strip(" \t") for line in report.splitlines() if "Page:" in line
    ]
    return "" if not named or re.match(r"none(,|$)", named[-1]) else named[-1]
