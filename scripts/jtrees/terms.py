"""The words of one harness that a skill copied for another harness needs an adapter for.

`TERMS` holds one table a harness: the tools, paths and files a skill names that only that
harness has. A skill copied for harness `h` that uses a term of another harness's table needs
the adapter, `docs/harness/<h>.md`, with a row for each such term. With one harness there is no
other table, so nothing is flagged: the table is here for the harness that comes next, whose
copy points its skills at the adapter.
"""

from __future__ import annotations

import re

TERMS: dict[str, dict[str, re.Pattern[str]]] = {
    "claude-code": {
        "t3_thread_*": re.compile(r"\bt3_thread_\w+"),
        "delegate_task": re.compile(r"\bdelegate_task\b"),
        "run_in_background": re.compile(r"\brun_in_background\b"),
        "Monitor": re.compile(r"\bMonitor\b"),
        "AskUserQuestion": re.compile(r"\bAskUserQuestion\b"),
        "ToolSearch": re.compile(r"\bToolSearch\b"),
        "~/.claude/": re.compile(r"~/\.claude/"),
        "settings.json": re.compile(r"\bsettings\.json\b"),
    },
}


def used(text: str, harness: str) -> set[str]:
    """The terms of every other harness's table that `text` names: what a copy of it for
    `harness` needs the adapter for."""
    return {
        term
        for owner, table in TERMS.items()
        if owner != harness
        for term, pattern in table.items()
        if pattern.search(text)
    }
