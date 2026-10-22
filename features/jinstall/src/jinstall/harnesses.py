"""The harnesses jstack installs for, one row each.

A row has the name of the harness's layout (`Machine.layout`) and the title its README gives it.
It has the root under HOME where the harness's agent reads skills. It has the file under HOME
where that agent reads hook entries, or none when the harness gets no hook entries. It has the
folder of a checkout where that agent reads the repo's own skills, or none when the install
links no such skills for the harness. It has the settings file under HOME where the harness reads
whether its agent adds an AI co-author trailer to a commit or a pull request, and the keys there
that turn the trailer off, or none when the harness has no such setting. For Claude Code, every
other Claude home gets the same keys in its own settings.json (`needs`).
`terms.LEAVES_OUT` holds what each harness leaves out.

Codex has no such setting: codex-cli 0.163.0 warns that `commit_attribution` in config.toml is
an unrecognized setting and ignores it, and whether it adds the trailer is a flag of the account's
workspace. Cursor's CLI reads `attribution` in `~/.cursor/cli-config.json`, as the
`update-cli-config` skill that Cursor installs in `~/.cursor/skills-cursor` documents it."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Harness:
    name: str
    title: str
    root: str
    hooks: str = ""
    project: str = ""
    settings: str = ""
    attribution: dict = field(default_factory=dict, hash=False)


HARNESSES = (
    Harness(
        "claude-code",
        "Claude Code",
        ".claude/skills",
        ".claude/settings.json",
        ".claude/skills",
        ".claude/settings.json",
        {"attribution": {"commit": "", "pr": ""}, "includeCoAuthoredBy": False},
    ),
    Harness("codex", "Codex", ".codex/skills", ".codex/hooks.json"),
    Harness(
        "cursor",
        "Cursor",
        ".agents/skills",
        project=".cursor/skills",
        settings=".cursor/cli-config.json",
        attribution={
            "attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}
        },
    ),
)
CLAUDE_CODE = HARNESSES[0]
