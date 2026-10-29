"""The lines that credit an AI tool as a co-author of a commit, found and taken out.

The patterns are jleak's (`jleak.trailers.PATTERNS`), the one place that names them, so jmerge
and jleak's hooks take out the same lines. A human co-author is never one.

jmerge strips them from the squash commit it writes, and the pull request's check
(`scripts/no_ai_trailers.py`) fails a pull request that carries one.
"""

from jleak.trailers import PATTERNS


def ai(line: str) -> bool:
    return any(pattern.regex.search(line) for pattern in PATTERNS)


def found(text: str) -> list[tuple[int, str]]:
    """Each AI co-author line of the text, with its line number, from 1."""
    return [(at, line) for at, line in enumerate(text.splitlines(), 1) if ai(line)]


def strip(text: str) -> str:
    """The text with no AI co-author line, and no blank line or space left at its end."""
    return "\n".join(line for line in text.splitlines() if not ai(line)).rstrip()
