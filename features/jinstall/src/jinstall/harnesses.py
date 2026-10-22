"""The harnesses jstack installs for, one row each: the name of its layout
(`Machine.layout`), the title its README gives it, the root under HOME its agent reads
skills from, the file under HOME its agent reads hook entries from, none for a harness
that gets none, and the folder of a checkout its agent reads the repo's own skills from, none
for a harness the install links none for. What each leaves out is `terms.LEAVES_OUT`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Harness:
    name: str
    title: str
    root: str
    hooks: str = ""
    project: str = ""


HARNESSES = (
    Harness(
        "claude-code", "Claude Code", ".claude/skills", ".claude/settings.json", ".claude/skills"
    ),
    Harness("codex", "Codex", ".codex/skills", ".codex/hooks.json"),
    Harness("cursor", "Cursor", ".agents/skills", project=".cursor/skills"),
)
CLAUDE_CODE = HARNESSES[0]
