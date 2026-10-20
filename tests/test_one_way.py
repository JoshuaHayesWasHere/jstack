"""One supported way per feature: a feature a command owns has no copy of its old block in a
skill, a file a skill reads, or a hook.

Each row of `ONE_WAY` is a feature, the command that owns it, and a fragment of the block
the command replaced, distinctive enough that only a copy of that block carries it. A file
that carries a row's fragment fails with an error that names the command to call in its
place. A copy pasted back into a skill is the mistake this catches: a copy drifts from the
others, and one of them broke under zsh while the tests ran it under `sh` alone.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


ONE_WAY = [
    ("playbook", 'uv run --project "$T/.." jbus playbook <role> "$B"', "/^Playbook:/"),
]


def carriers():
    """Every file that could carry a copy of a block: each skill and each file beside it,
    and each hook."""
    return sorted(REPO.glob("skills/**/*.md")) + sorted(
        path for path in (REPO / "hooks").iterdir() if path.is_file()
    )


def copies(text, fragment):
    """The lines of `text` that carry `fragment`."""
    return [line.strip() for line in text.splitlines() if fragment in line]


def faults(files):
    """For each file and row, the error a copy of the row's old block gets."""
    found = []
    for path, text in files:
        for feature, command, fragment in ONE_WAY:
            for line in copies(text, fragment):
                said = f"is a copy of the {feature} block: call `{command}` in its place"
                found.append(f"{path}: `{line}` {said}")
    return found


def test_no_skill_and_no_hook_carries_a_copy_of_a_block_a_command_owns():
    files = [(path.relative_to(REPO).as_posix(), path.read_text()) for path in carriers()]
    assert faults(files) == []


@pytest.mark.parametrize(("feature", "command", "fragment"), ONE_WAY)
def test_a_copy_put_back_into_a_skill_is_caught_and_named_with_its_command(
    feature, command, fragment
):
    skill = (REPO / "skills" / "crew" / "SKILL.md").read_text()
    copied = f"{skill}\n   ```sh\n   name=$(awk '{fragment} {{print $(2); exit}}' \"$B\")\n   ```\n"
    (said,) = faults([("skills/crew/SKILL.md", copied)])
    assert said.endswith(f"is a copy of the {feature} block: call `{command}` in its place")


@pytest.mark.parametrize(("feature", "command", "fragment"), ONE_WAY)
def test_the_command_that_owns_a_feature_is_one_jbus_runs(feature, command, fragment):
    words = command.split()
    verb = words[words.index("jbus") + 1]
    ran = subprocess.run(
        ["uv", "run", "--project", str(REPO), "jbus", verb, "--help"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith(f"usage: jbus {verb} ")
