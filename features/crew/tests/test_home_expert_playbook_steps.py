"""The home and the expert skills, like crew and scout Start 3, ask for no todo list of a playbook's
steps: where a skill and its playbook disagree, the skill wins, so a skill that still asked for the
copy would bring it back."""

import re

import pytest

from testing.paths import REPO

HOME = REPO / "features" / "home" / "skills" / "home" / "SKILL.md"
EXPERT = REPO / "features" / "expert" / "an-ask.md"
TODO = re.compile(r"\btodo", re.I)


@pytest.mark.parametrize("path", [HOME, EXPERT], ids=lambda path: path.parent.name)
def test_the_skill_names_no_todo_list(path):
    assert not TODO.search(path.read_text())
