"""The harnesses jstack installs for, one row each.

A row has the name of the harness's layout (`Machine.layout`) and the title its README gives it.
It has the root under HOME where the harness's agent reads skills. It has the file under HOME
where that agent reads hook entries, or none when the harness gets no hook entries. It has the
folder of a checkout where that agent reads the repo's own skills, or none when the install
links no such skills for the harness. `terms.LEAVES_OUT` holds what each harness leaves out."""

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
