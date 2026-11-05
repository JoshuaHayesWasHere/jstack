import importlib
import re
import sys

import pytest

from jbriefs import skills
from jdrift.explained import COMMENT as CARD
from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))
frontmatter = importlib.import_module("jtrees.frontmatter")

PRINCIPLES = REPO / "features" / "principles" / "skills"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
FILES = sorted(skills.listed("principle").values())


def named(path):
    return path.parent.name


@pytest.mark.parametrize("path", FILES, ids=named)
def test_a_principle_is_a_skill_a_model_may_load_described_by_its_apply_when_line(path):
    front = frontmatter.parse(path.read_text())
    _, text = frontmatter.split(path.read_text())
    apply = " ".join(text.lstrip("\n").split("\n\n")[1].splitlines())
    assert front == {
        "name": named(path),
        "description": apply,
    }
    assert apply.startswith("Apply ")


def test_third_party_lists_every_principle_file_and_no_other():
    text = THIRD_PARTY.read_text()
    listed = re.findall(r"^- `(features/principles/[^`]+)`$", text, re.M)
    (own,) = re.findall(r"^jstack's own: (.+)$", text, re.M)
    ours = [
        path for path in re.findall(r"`([^`]+)`", own) if path.startswith("features/principles/")
    ]
    assert sorted(listed + ours) == [str(path.relative_to(REPO)) for path in FILES]
    assert not set(listed) & set(ours)


UNSTACKED = [
    PRINCIPLES / "principle-build-the-lever" / "SKILL.md",
    PRINCIPLES / "principle-sequence-verifiable-units" / "SKILL.md",
]
STACKING = re.compile(r"\bstack\w*|\brebase onto\b", re.I)


def stacking(text):
    """The lines of `text` that tell a reader to stack work or to rebase onto a branch first."""
    return [n for n, line in enumerate(text.splitlines(), 1) if STACKING.search(line)]


@pytest.mark.parametrize("path", UNSTACKED, ids=named)
def test_a_reworded_principle_does_not_stack(path):
    prose = CARD.sub("", path.read_text())
    assert stacking(prose) == [], f"{named(path)} stacks or rebases first"


@pytest.mark.parametrize(
    "line",
    ["Stack commits and PRs in order.", "how you stack commits", "Rebase onto clean trunk first."],
)
def test_a_line_that_stacks_is_found(line):
    assert stacking(f"# A principle\n\n{line}\n") == [3]


def test_a_card_line_that_names_a_playbook_is_not_a_line_that_stacks():
    card = "<!-- card: A tile | 1 | A rule. | `autopilot-stack` -->"
    assert stacking(f"# A principle\n\n{card}\n") == [3]
    assert stacking(CARD.sub("", f"# A principle\n\n{card}\n")) == []
