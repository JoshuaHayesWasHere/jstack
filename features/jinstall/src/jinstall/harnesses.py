"""The harnesses jstack installs for, one row each: the name of its layout
(`Machine.layout`), the title its README gives it, and the root under HOME its agent reads
skills from. What each leaves out is `terms.LEAVES_OUT`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Harness:
    name: str
    title: str
    root: str


HARNESSES = (
    Harness("claude-code", "Claude Code", ".claude/skills"),
    Harness("codex", "Codex", ".codex/skills"),
    Harness("cursor", "Cursor", ".agents/skills"),
)
CLAUDE_CODE = HARNESSES[0]
