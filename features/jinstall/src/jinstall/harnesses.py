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

A row has the variables the install sets in `env` of each Claude home's settings.json, or none.
Claude Code lists every skill a model may load, with its description, in a listing it cuts to a
budget of 1% of the context window, about 8,000 characters in a session of 200k tokens, and it
drops the descriptions of the skills used least first. jstack's 50 skills a model may load bring
the listing to about 29,000 characters, so `SLASH_COMMAND_TOOL_CHAR_BUDGET` sets the budget to
the listing's size, which keeps jstack's descriptions in it.

A row has, last, the file the layout writes into the folder of each skill that skills.json marks
`hidden`, by its path in that folder and its text, or none. Claude Code and Cursor read
`disable-model-invocation: true` in the skill's frontmatter. Codex does not: it reads
`policy.allow_implicit_invocation` in `agents/openai.yaml` beside the skill. Codex reads
`~/.agents/skills`, Cursor's root, as well as its own, so Cursor's layout carries the file too.

A row says, after that, whether its layout copies each skill's SKILL.md rather than linking it.
codex-cli 0.165.0 lists no skill whose SKILL.md is a symlink, though it follows a linked folder,
so the Codex layout writes each SKILL.md as a copy, which the install's `--check` names stale once
its source changes.

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
    env: dict = field(default_factory=dict, hash=False)
    hides: tuple[str, str] | None = None
    copies: bool = False


HIDES = ("agents/openai.yaml", "policy:\n  allow_implicit_invocation: false\n")
HARNESSES = (
    Harness(
        "claude-code",
        "Claude Code",
        ".claude/skills",
        ".claude/settings.json",
        ".claude/skills",
        ".claude/settings.json",
        {"attribution": {"commit": "", "pr": ""}, "includeCoAuthoredBy": False},
        env={"SLASH_COMMAND_TOOL_CHAR_BUDGET": "32000"},
    ),
    Harness("codex", "Codex", ".codex/skills", ".codex/hooks.json", hides=HIDES, copies=True),
    Harness(
        "cursor",
        "Cursor",
        ".agents/skills",
        project=".cursor/skills",
        settings=".cursor/cli-config.json",
        attribution={
            "attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}
        },
        hides=HIDES,
    ),
)
CLAUDE_CODE = HARNESSES[0]
