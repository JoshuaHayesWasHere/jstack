"""Every copy of a repo that a skill or playbook tells a thread to make goes under `$TMPDIR`.

A crew jbus launches has its `TMPDIR` on disk, in its own scratch folder that jbus removes once it
settles the thread (`jbus.dispatch.scratch`). `/tmp` is a tmpfs with a per-user quota, and full
repo copies made there by name, which nothing removed, filled it on 2026-11-04 and 2026-11-05 and
failed every shell. So a step that makes a scratch folder, a worktree, a clone or an archive names
its place through `$TMPDIR` (a bare `mktemp -d` reads it), never `/tmp` itself.
"""

import re

import pytest

from testing.layouts import assembled

INSTALLED = ("skills/**/*.md", "playbooks/*.md", "principles/*.md", "templates/**/*.md")
COPY = re.compile(r"mktemp|git worktree add|git clone|git archive")
DEFAULT = re.compile(r"\$\{TMPDIR:-/tmp\}")
UNDER = re.compile(r"mktemp|\$\{?TMPDIR\b|\$VERIFY_JSTACK_SANDBOX|\$HOME/")


def copies():
    """Each line of the installed skill text that makes a folder or a copy, with where it is."""
    root = assembled()
    for pattern in INSTALLED:
        for path in sorted(root.glob(pattern)):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if COPY.search(line):
                    yield f"{path.relative_to(root)}:{number}", line


def test_the_skill_text_has_copy_steps_to_check():
    assert sum(1 for _ in copies()) >= 5


@pytest.mark.parametrize("where, line", [pytest.param(*one, id=one[0]) for one in copies()])
def test_a_copy_step_names_its_place_through_tmpdir(where, line):
    kept = DEFAULT.sub("$TMPDIR", line)
    assert "/tmp" not in kept, f"{where} makes a copy in /tmp by name: {line.strip()}"
    if "git worktree add" in kept or "git archive" in kept:
        assert UNDER.search(kept), f"{where} names no place under $TMPDIR: {line.strip()}"
