"""The harnesses jstack installs for, one row each: the name of its layout
(`Machine.layout`), the title its README gives it, the root under HOME its agent reads
skills from, and the file under HOME its agent reads hook entries from, none for a harness
that gets none. What each leaves out is `terms.LEAVES_OUT`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Harness:
    name: str
    title: str
    root: str
    hooks: str = ""


HARNESSES = (
    Harness("claude-code", "Claude Code", ".claude/skills", ".claude/settings.json"),
    Harness("codex", "Codex", ".codex/skills", ".codex/hooks.json"),
    Harness("cursor", "Cursor", ".agents/skills"),
)
CLAUDE_CODE = HARNESSES[0]
