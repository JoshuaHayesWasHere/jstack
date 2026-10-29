"""The lines that say an AI wrote a commit or a pull request: an AI co-author trailer, and the
"Generated with Claude Code" line. No commit and no pull request carries one.

This module is the one place that names them. Two guards read `PATTERNS`: the hook on an agent's
commands (`jleak --trailers`), which refuses a commit or a pull request whose text has such a line,
and git's `commit-msg` hook (`jleak --commit-msg`), which takes the line out of a commit's
message. jmerge reads them too (`jmerge.trailers`), to take the lines out of the squash commit it
writes and for the pull request's check. A pattern is held against one line at a time, as jleak's
other patterns are. A `Co-authored-by:` line that names a person is not matched, so no reader
takes it out.

    ai-co-author                 a Co-authored-by trailer that names Claude, Codex, OpenAI,
                                 Cursor or Copilot, or an @anthropic.com address
    generated-with-claude-code   the line Claude Code adds under a pull request's body, which
                                 starts the line after any emoji or punctuation
"""

import re

from jleak import Pattern

NAMES = r"claude|codex|openai|cursor|copilot"
PATTERNS = (
    Pattern(
        "ai-co-author",
        re.compile(rf"(?i)^\s*co-authored-by\s*[:=].*(?:\b(?:{NAMES})\b|@anthropic\.com\b)"),
    ),
    Pattern("generated-with-claude-code", re.compile(r"(?i)^\W*generated with \[?claude code\b")),
)


def strip(message: str) -> tuple[str, list[str]]:
    """The message without its AI trailer lines, and the lines taken out. The blank lines that the
    removal leaves at the end go too, and the message keeps the final newline it had. A message
    with no such line comes back as it was, character for character."""
    lines = message.splitlines(keepends=True)
    taken = [line for line in lines if any(p.regex.search(line) for p in PATTERNS)]
    if not taken:
        return message, []
    kept = [line for line in lines if line not in taken]
    while kept and not kept[-1].strip():
        kept.pop()
    text = "".join(kept)
    if kept and not text.endswith("\n") and message.endswith("\n"):
        text += "\n"
    return text, [line.rstrip("\r\n") for line in taken]
