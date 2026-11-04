"""`jbus playbook` prints a playbook's steps and the name and path of each principle it cites,
never a principle's text: a crew read the text at the path when a step names it, and a print
that carried it all ran to 16 KB, over the size a harness shows a call's output inline."""

import re
from pathlib import Path

import pytest

from jbus import playbook
from testing.paths import playbooks

CITED = re.compile(r"principles/([a-z0-9-]+)\.md")
NAMED = re.compile(r"^- ([a-z0-9-]+): (/\S+)$")


def principles(name):
    return list(dict.fromkeys(CITED.findall(playbooks()[name].read_text())))


def test_a_crewmate_s_bug_fix_print_is_under_5_kb():
    said = "\n".join(playbook.opened("crewmate", "", "bug-fix")) + "\n"
    assert len(said.encode()) < 5000


@pytest.mark.parametrize(
    ("role", "name"),
    [
        ("crewmate", "bug-fix"),
        ("crewmate", "refactoring"),
        ("scout", "investigation"),
        ("reviewer", "bug-fix"),
    ],
)
def test_each_cited_principle_is_named_with_a_path_that_loads_it_and_its_text_is_not_printed(
    role, name
):
    said = playbook.opened(role, "", name)
    at = said.index(f"the principles playbooks/{name}.md cites, each read in full at its path:")
    named = [NAMED.match(line) for line in said[at + 1 :]]
    assert all(named)
    assert [one[1] for one in named] == principles(name)
    printed = "\n".join(said)
    for one in named:
        text = Path(one[2]).read_text()
        assert text.startswith(f"---\nname: {one[1]}\n")
        body = text.split("\n---\n", 1)[1].strip()
        assert body.splitlines()[0] not in printed
