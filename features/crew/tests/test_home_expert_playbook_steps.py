"""The home and the expert skills, like crew and scout Start 3, ask for a playbook's steps to be
worked in order and asks for no todo list of them: where a skill and its playbook disagree, the
skill wins, so a skill that still asked for the copy would bring it back."""

import re

import pytest

from testing.paths import REPO

SKILLS = {
    "home": REPO / "features" / "home" / "skills" / "home" / "SKILL.md",
    "expert": REPO / "features" / "expert" / "an-ask.md",
}
TODO = re.compile(r"\btodo", re.I)


@pytest.mark.parametrize("role", SKILLS)
def test_the_skill_works_a_playbooks_steps_in_order_and_names_no_todo_list(role):
    lines = [line.strip() for line in SKILLS[role].read_text().splitlines()]
    assert not [line for line in lines if TODO.search(line)]
    assert "Work its numbered steps in order." in lines
    assert "Report a step you do not do as `skip: <reason>`." in lines
