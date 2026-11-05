"""Every folder or copy of a repo that a skill or playbook tells a thread to make goes under
`$TMPDIR`.

A crew jbus launches has its `TMPDIR` on disk, in its own scratch folder that jbus removes once it
settles the thread (`jbus.dispatch.scratch`). `/tmp` is a tmpfs with a per-user quota, and full
repo copies made there by name, which nothing removed, filled it on 2026-11-04 and 2026-11-05 and
failed every shell.

The lint runs each command of the installed skill text that makes a folder, a worktree, a clone
or an archive, in a repo of one commit with `TMPDIR` set, after the commands before it in the
same file (a clone into the `$tree` a `mktemp -d` above it made). A placeholder such as
`<commit>` is filled in. The command passes when it adds to what is under `TMPDIR`.
"""

import os
import re
import shutil
import subprocess
from collections import defaultdict

import pytest

from testing.layouts import assembled

READ_SET = ("*.md",)
INSTALLED = ("skills/**/*.md", "playbooks/*.md", "principles/*.md", "templates/**/*.md")
COPY = re.compile(r"mktemp|git worktree add|git clone|git archive")
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")


def copies():
    """Each file's commands that make a folder or a copy, in order: a line of a block, or a span
    of code in a line of prose."""
    root = assembled()
    found = defaultdict(list)
    for pattern in INSTALLED:
        for path in sorted(root.glob(pattern)):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                for command in re.findall(r"`([^`]+)`", line) or [line]:
                    if COPY.search(command):
                        found[str(path.relative_to(root))].append((number, command.strip()))
    return found


FOUND = copies()


def filled(command):
    return re.sub(r"<[^>]+>", lambda m: "HEAD" if "commit" in m.group() else "x", command)


def under_tmpdir(tmp_path, commands):
    """Run the commands in a fresh repo with `TMPDIR` set, and count the paths under it."""
    repo, scratch = tmp_path / "repo", tmp_path / "scratch"
    for made in (repo, scratch):
        shutil.rmtree(made, ignore_errors=True)
        made.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    empty = ["git", *IDENTITY, "commit", "-q", "--allow-empty", "-m", "a"]
    subprocess.run(empty, cwd=repo, check=True)
    script = "\n".join(f"{filled(command)} > /dev/null 2>&1" for command in commands)
    env = {**os.environ, "TMPDIR": str(scratch)}
    subprocess.run(["bash", "-c", script], cwd=repo, env=env, check=False)
    return sum(1 for _ in scratch.rglob("*"))


def test_the_skill_text_has_copy_steps_to_check():
    assert sum(len(commands) for commands in FOUND.values()) >= 5


@pytest.mark.parametrize(
    "where, index",
    [
        pytest.param(where, index, id=f"{where}:{number}")
        for where, commands in FOUND.items()
        for index, (number, _) in enumerate(commands)
    ],
)
def test_a_copy_step_makes_its_copy_under_tmpdir(tmp_path, where, index):
    commands = [command for _, command in FOUND[where][: index + 1]]
    before = under_tmpdir(tmp_path, commands[:-1])
    assert under_tmpdir(tmp_path, commands) > before, f"{where}: {commands[-1]}"
