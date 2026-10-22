"""What each harness leaves out: the tools, paths and files a skill may name that the agent of
that harness does not have.

`LEAVES_OUT` holds one table for each harness. When `layout` assembles a harness's layout, it
flags each term of that harness's table that a skill's text names. The layout's README lists
those terms, so a reader of that harness sees which steps name something it lacks.
Claude Code leaves out nothing a skill names: the skills are written for it. Codex and Cursor
have none of Claude Code's own tools, its home folder or its settings file.
"""

from __future__ import annotations

import re

CLAUDE_CODE_ONLY: dict[str, re.Pattern[str]] = {
    "t3_thread_*": re.compile(r"\bt3_thread_\w+"),
    "delegate_task": re.compile(r"\bdelegate_task\b"),
    "run_in_background": re.compile(r"\brun_in_background\b"),
    "Monitor": re.compile(r"\bMonitor\b"),
    "AskUserQuestion": re.compile(r"\bAskUserQuestion\b"),
    "ToolSearch": re.compile(r"\bToolSearch\b"),
    "~/.claude/": re.compile(r"~/\.claude/"),
    "settings.json": re.compile(r"\bsettings\.json\b"),
}

LEAVES_OUT: dict[str, dict[str, re.Pattern[str]]] = {
    "claude-code": {},
    "codex": CLAUDE_CODE_ONLY,
    "cursor": CLAUDE_CODE_ONLY,
}


def used(text: str, harness: str) -> set[str]:
    """The terms of `harness`'s table that `text` names, which are what `text` asks for and
    the harness leaves out."""
    return {term for term, pattern in LEAVES_OUT[harness].items() if pattern.search(text)}
