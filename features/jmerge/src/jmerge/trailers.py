"""The lines that credit an AI tool as a co-author of a commit, found and taken out.

A line is one when it is a `Co-authored-by:` trailer that names Claude, Codex, OpenAI, Cursor or
Copilot as a word, or an `@anthropic.com` address, or when the whole line is the footer that says
it was generated with Claude Code. Case does not matter. A human co-author is never one.

jmerge strips them from the squash commit it writes, and the pull request's check
(`scripts/no_ai_trailers.py`) fails a pull request that carries one. The unit
no-ai-trailers-harness gives the patterns one home for the harness hooks too; until it lands they
are here, and this module then imports them from there.
"""

import re

PATTERNS = (
    re.compile(
        r"^\s*co-authored-by:.*(\b(claude|codex|openai|cursor|copilot)\b|@anthropic\.com)",
        re.IGNORECASE,
    ),
    re.compile(r"^\W*generated with \[?claude code\]?(\([^)]*\))?\W*$", re.IGNORECASE),
)


def ai(line: str) -> bool:
    return any(pattern.search(line) for pattern in PATTERNS)


def found(text: str) -> list[tuple[int, str]]:
    """Each AI co-author line of the text, with its line number, from 1."""
    return [(at, line) for at, line in enumerate(text.splitlines(), 1) if ai(line)]


def strip(text: str) -> str:
    """The text with no AI co-author line, and no blank line or space left at its end."""
    return "\n".join(line for line in text.splitlines() if not ai(line)).rstrip()
