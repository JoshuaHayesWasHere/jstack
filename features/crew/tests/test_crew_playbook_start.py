"""Start 3 of the crew and scout skills opens the playbook in a call of its own, with no `cat` of
another file beside it, and no skill or playbook asks for its steps in a todo list: 0 of 963
threads made one, and a crew has no todo tool. The Result's `Playbook:` line is the record of the
steps."""

import re

import pytest

from testing.paths import REPO, playbooks

READ_SET = (
    "features/crew/",
    "features/scout/",
    "playbooks/",
    "features/*/playbooks/",
    "features/*/skills/*/playbooks/",
)
SKILLS = {
    "crewmate": REPO / "features" / "crew" / "SKILL.md",
    "scout": REPO / "features" / "scout" / "SKILL.md",
}
TODO = re.compile(r"\btodo", re.I)


def start_3(path):
    text = path.read_text().split("\n## Start\n", 1)[1]
    return re.split(r"^4\. ", text, flags=re.M)[0].split("\n3. ", 1)[1]


@pytest.mark.parametrize("role", SKILLS)
def test_start_3_opens_the_playbook_in_a_call_of_its_own_and_copies_no_todo_list(role):
    step = start_3(SKILLS[role])
    assert not TODO.search(step)
    first = step.split("```")[0]
    assert "in a call of its own" in first
    assert "a call that also prints another file" in first
    block = re.search(r"```sh\n(.*?)```", step, re.S)[1]
    commands = [line.strip() for line in block.splitlines() if line.strip()]
    assert commands[1:] == [f'uv run --project "$T/../source" jbus playbook {role} "$B"']


@pytest.mark.parametrize("path", sorted(playbooks().values()), ids=lambda path: path.stem)
def test_no_playbook_asks_for_its_steps_in_a_todo_list(path):
    assert not TODO.search(path.read_text())
