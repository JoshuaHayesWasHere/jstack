"""No skill jstack installs shares a name with a Claude Code built-in command, a bundled skill or
an alias of one. Claude Code runs its own command for such a name, whatever `~/.claude/skills`
holds: `/review` ran the built-in code review, so jstack's review skill is `/pr-review`.

The names jstack installs are the skill and principle items of skills.json and its project
skills. `BUILT_IN` is the command table of https://code.claude.com/docs/en/commands, read on
2026-10-28, with each alias it gives. A name Claude Code adds later goes on the list. The fixture
case shows that the check catches a skill named `init` and a project skill named `review`."""

import json

from testing.paths import REPO

BUILT_IN = frozenset(
    """
    add-dir advisor agents allowed-tools android app artifact-capabilities artifact-diagramming
    artifacts auto-mode-setup autocompact autofix-pr background batch bg branch btw bug cd
    checkpoint checkup chrome claude-api claude-in-chrome clear code-review color compact config
    context continue copy cost dataviz debug deep-research design design-login design-sync
    desktop diff doctor effort exit export fast feedback fewer-permission-prompts focus fork goal
    heapdump help hooks ide import init insights install-github-app install-slack-app ios
    keybindings list-agents login logout loop mcp memory mobile model new output-style passes
    permissions plan plugin plugin-authoring powerup pr-comments privacy-settings proactive quit
    radio rate-limit-options rc recap release-notes reload-plugins reload-skills remote-control
    remote-env rename reset resume review rewind routines run run-skill-generator sandbox
    schedule scroll-speed security-review settings setup-bedrock setup-vertex share simplify
    skill-doctor skills slides stats status statusline stickers stop subtask tasks
    team-onboarding teleport terminal-setup theme tui ultraplan ultrareview undo update-config
    upgrade usage usage-credits verify vim voice web-setup workflow-authoring workflows
    """.split()
)


def installed(root):
    """Each name jstack installs as a skill, from `root`/skills.json."""
    tree = json.loads((root / "skills.json").read_text())
    items = [item["name"] for item in tree["items"] if item["kind"] in ("skill", "principle")]
    return sorted({*items, *(skill["name"] for skill in tree.get("projectSkills", []))})


def clashes(root):
    """Each name jstack installs that Claude Code already takes."""
    return [name for name in installed(root) if name in BUILT_IN]


def test_jstack_installs_its_skills():
    names = installed(REPO)
    assert {"crew", "pr-review", "principle-prove-it-works", "verify-jstack"} <= set(names)


def test_no_skill_takes_a_built_in_name():
    assert clashes(REPO) == []


def test_a_skill_named_as_a_built_in_is_caught(tmp_path):
    items = [
        {"name": "init", "kind": "skill"},
        {"name": "fake-skill", "kind": "skill"},
        {"name": "help", "kind": "playbook"},
    ]
    projects = [{"name": "review"}]
    tree = {"items": items, "projectSkills": projects}
    (tmp_path / "skills.json").write_text(json.dumps(tree))
    assert clashes(tmp_path) == ["init", "review"]
