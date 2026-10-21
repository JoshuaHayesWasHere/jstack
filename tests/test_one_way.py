"""One supported way per feature: a feature a command owns has no copy of its old block in a
skill, a file a skill reads, or a hook.

Each row of `ONE_WAY` is a feature, the command that owns it, and a fragment of the block
the command replaced, distinctive enough that only a copy of that block carries it. A file
that carries a row's fragment fails with an error that names the command to call in its
place. A copy pasted back into a skill is the mistake this catches: a copy drifts from the
others, and one of them broke under zsh while the tests ran it under `sh` alone.
"""

import os
import re
import subprocess
import textwrap

import pytest

from testing.paths import REPO

ONE_WAY = [
    ("playbook", 'uv run --project "$T/.." jbus playbook <role> "$B"', "/^Playbook:/"),
    ("gate", "jbus gate <slug>, the gate's lines on stdin", "grep -c '^## '"),
    ("home", 'uv run --project "$T/.." jbus home "$B"', "s/^Home:[[:space:]]*"),
    ("checks", 'uv run --project "$T/.." jmerge --checks', "checks() {"),
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
    copied = (
        f"# A skill\n\n   ```sh\n   name=$(awk '{fragment} {{print $(2); exit}}' \"$B\")\n   ```\n"
    )
    (said,) = faults([("skills/crew/SKILL.md", copied)])
    assert said.endswith(f"is a copy of the {feature} block: call `{command}` in its place")


@pytest.mark.parametrize(("feature", "command", "fragment"), ONE_WAY)
def test_the_command_that_owns_a_feature_is_one_jstack_runs(feature, command, fragment):
    words = command.split()
    (program,) = [word for word in words if word in ("jbus", "jmerge")]
    asked = words[words.index(program) + 1]
    verb = [asked] if program == "jbus" else []
    ran = subprocess.run(
        ["uv", "run", "--project", str(REPO), program, *verb, "--help"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith(f"usage: {' '.join([program, *verb])} ")
    if program == "jmerge":
        assert asked in ran.stdout.split()


FENCED = re.compile(r"^([ \t]*)```sh\n(.*?)^\1```", re.M | re.S)
NOT_ONE_GATE = """\
## Gate <n>: <the question>
Asked by: one-way, thread mcp:one-way
## Gate <n>: a second one"""

RUN = [
    ("gate", "jbus gate", "<the gate, filled in>", NOT_ONE_GATE),
]
FILLS = {
    "'<slug>'": "'one-way'",
    "'<project>'": "'demo'",
    "'<about>'": "'one-way'",
}


def blocks(placeholder):
    """Each shell block of a skill that holds `placeholder`, by the file and line it starts at."""
    for path in sorted((REPO / "skills").glob("*/*.md")):
        text = path.read_text()
        for found in FENCED.finditer(text):
            if placeholder in found[2]:
                line = text.count("\n", 0, found.start()) + 1
                yield f"{path.relative_to(REPO)}:{line}", textwrap.dedent(found[2])


def run(tmp_path, command, block):
    """`block` with `lines` in place of the placeholder, beside a fake `command` that keeps its
    stdin. What the block printed, and what reached the command."""
    bin_dir, kept = tmp_path / "bin", tmp_path / "kept"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / command.split()[0]
    fake.write_text(f'#!/bin/sh\ncat > "{kept}"\necho "queued: question 1"\n')
    fake.chmod(0o755)
    kept.unlink(missing_ok=True)
    for placeholder, fill in FILLS.items():
        block = block.replace(placeholder, fill)
    ran = subprocess.run(
        ["sh", "-c", f"SEP=$(printf '\\037'); own=home; N=one; T={REPO / 'templates'}\n{block}"],
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin"},
        cwd=tmp_path,
    )
    return ran.stdout + ran.stderr, kept.read_text() if kept.exists() else None


@pytest.mark.parametrize(
    ("feature", "command", "placeholder", "lines"), RUN, ids=[r[0] for r in RUN]
)
def test_each_block_of_a_feature_leaves_its_checks_to_the_command(
    tmp_path, feature, command, placeholder, lines
):
    """A check no fragment names is caught too: each block of the feature is run, and a check
    in front of the command, whatever its words, stops the lines before the command."""
    found = list(blocks(placeholder))
    assert found, f"no skill has a block for {feature}: the placeholder {placeholder} moved"
    for where, block in found:
        said, reached = run(tmp_path, command, block.replace(placeholder, lines))
        kept = [line for line in lines.splitlines() if not line.startswith("Asked by:")]
        assert reached is not None and all(line in reached for line in kept), (
            f"{where}: the block for {feature} did not hand {command} the lines and said "
            f"{said.strip()!r}: leave the checks to {command}, which owns them"
        )
