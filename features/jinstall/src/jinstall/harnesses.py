"""The harnesses jstack installs for, one row each.

A row has the name of the harness's layout (`Machine.layout`) and the title its README gives it.
It has the root under HOME that its agent reads skills from, and the file under HOME that its
agent reads hook entries from, or none when the harness gets no hook entries. It has the folder
of a checkout that its agent reads the repo's own skills from, or none when the install links no
such skills for the harness. `terms.LEAVES_OUT` holds what each harness leaves out."""

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
