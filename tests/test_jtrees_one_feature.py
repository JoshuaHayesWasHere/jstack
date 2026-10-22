"""A new hook, playbook or skill is one feature's change: in a copy of this checkout each case
adds one to one feature, the generator runs, and the docs check passes. Every path the case
and the generator changed is then that feature's or only the repo's own (`INFRA`,
`SHARED-DELETE`), so lint-borders sees one feature and asks for no `cross-cutting` label."""

import importlib.util
import json
import shutil
import subprocess
import sys

import pytest

from jinstall.kinds import HookGroup
from jinstall.machine import Machine
from jinstall.needs import needs
from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))
from jtrees.crawl import crawl, tracked

spec = importlib.util.spec_from_file_location("lint_borders", REPO / "scripts" / "lint-borders.py")
assert spec is not None and spec.loader is not None
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)
REPO_OWNED = {"INFRA", "SHARED-DELETE"}


def hook(root):
    """A hook of jleak's: its manifest entry, its script, and its section with the entry."""
    manifest = root / "features" / "jleak" / "feature.json"
    declared = json.loads(manifest.read_text())
    declared["hooks"].append(
        {"event": "PostToolUse", "matcher": "Bash", "script": "hooks/after-push.sh"}
        | {"harnesses": ["claude-code"]}
    )
    manifest.write_text(json.dumps(declared, indent=2) + "\n")
    (root / "features" / "jleak" / "hooks" / "after-push.sh").write_text("#!/bin/sh\nexit 0\n")
    entry = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "sh '<layout>/hooks/after-push.sh' 2>/dev/null || true",
                            "timeout": 5,
                        }
                    ],
                }
            ]
        }
    }
    page = root / "features" / "jleak" / "docs" / "jleak.md"
    section = "\n## The after-push hook\n\n"
    section += "`features/jleak/hooks/after-push.sh` is a `PostToolUse` hook.\n"
    section += f"\n```json\n{json.dumps(entry, indent=2)}\n```\n"
    page.write_text(page.read_text() + section)


def playbook(root):
    """A playbook of scout's, shaped as its others are."""
    folder = root / "features" / "scout" / "playbooks"
    text = (folder / "investigation.md").read_text()
    (folder / "survey.md").write_text(text.replace("# Investigation", "# Survey", 1))


def skill(root):
    """A skill of why's, under its `skills/`."""
    text = (root / "features" / "why" / "SKILL.md").read_text()
    folder = root / "features" / "why" / "skills" / "why-not"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(text.replace("name: why\n", "name: why-not\n", 1))


CASES = {"jleak": hook, "scout": playbook, "why": skill}


def files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


@pytest.fixture
def copy(tmp_path):
    """This checkout's files, tracked and not yet added, with no git and no .venv."""
    root = tmp_path / "jstack"
    for path in tracked(REPO):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / path, target, follow_symlinks=False)
    return root


@pytest.mark.parametrize("feature", CASES)
def test_one_new_hook_playbook_or_skill_changes_its_own_feature_and_the_repo_only(copy, feature):
    before = files(copy)
    CASES[feature](copy)
    for script in ("generate-jstack-trees.py", "check-jstack-docs.py"):
        ran = subprocess.run(
            [
                sys.executable,
                "-I",
                copy / "scripts" / script,
                *([copy] if "docs" in script else []),
            ],
            cwd=copy,
            capture_output=True,
            text=True,
        )
        assert ran.returncode == 0, ran.stdout + ran.stderr
    after = files(copy)
    changed = sorted(path for path in before | after if before.get(path) != after.get(path))
    tree = crawl(copy)
    assert lint.features(tree, changed, set()) is None
    for path in changed:
        owners = set(tree.owners(path))
        assert owners == {feature} or (owners and owners <= REPO_OWNED), (path, owners)
    if feature == "jleak":
        listed = json.loads((copy / "skills.json").read_text())["hooks"]
        (added,) = [one for one in listed if one["name"] == "after-push.sh"]
        assert added["events"] == [
            {"harness": "claude-code", "event": "PostToolUse", "matcher": "Bash"}
        ]
        script = "features/jleak/hooks/after-push.sh"
        assert (
            f"| [{script}]({script}) | claude-code | `jleak` |" in (copy / "CATALOG.md").read_text()
        )
        machine = Machine.here(copy)
        settings = machine.home / ".claude" / "settings.json"
        hooked = HookGroup(settings, "PostToolUse", "Bash", "hooks/after-push.sh")
        assert hooked in [need.kind for need in needs(machine)]
