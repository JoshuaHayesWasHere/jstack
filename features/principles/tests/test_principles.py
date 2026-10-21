import importlib
import re
import sys

import pytest

from jdrift.explained import COMMENT as CARD
from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))
frontmatter = importlib.import_module("jtrees.frontmatter")

PRINCIPLES = REPO / "features" / "principles" / "skills"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
PSTACK_COMMIT = "99743e9c151c8537cbbf1f98bb38f34ef3368453"
EM_DASH = "\N{EM DASH}"
FILES = sorted(PRINCIPLES.glob("principle-*/SKILL.md"))


def named(path):
    return path.parent.name


def test_the_directory_holds_only_principles():
    assert FILES, "features/principles/skills/ has no principle"
    assert sorted(PRINCIPLES.iterdir()) == [path.parent for path in FILES]
    assert all(sorted(path.parent.iterdir()) == [path] for path in FILES)


@pytest.mark.parametrize("path", FILES, ids=named)
def test_a_principle_opens_with_its_heading_and_has_a_body(path):
    _, text = frontmatter.split(path.read_text())
    first, _, body = text.lstrip("\n").partition("\n")
    assert re.fullmatch(r"# \S.*", first), f"{named(path)} does not open with a heading"
    assert body.strip(), f"{named(path)} has a heading and nothing under it"


@pytest.mark.parametrize("path", FILES, ids=named)
def test_a_principle_is_a_skill_typed_by_name_described_by_its_apply_when_line(path):
    front = frontmatter.parse(path.read_text())
    _, text = frontmatter.split(path.read_text())
    apply = text.lstrip("\n").split("\n\n")[1]
    assert front == {
        "name": named(path),
        "description": apply,
        "disable-model-invocation": True,
    }
    assert apply.startswith("Apply ")


@pytest.mark.parametrize("path", [*FILES, THIRD_PARTY], ids=lambda path: path.parent.name)
def test_no_em_dash(path):
    lines = [n for n, line in enumerate(path.read_text().splitlines(), 1) if EM_DASH in line]
    assert not lines, f"{path} has an em dash on line {lines}"


@pytest.mark.parametrize("path", FILES, ids=named)
def test_a_link_to_another_file_finds_it(path):
    targets = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", path.read_text())
    missing = [t for t in targets if "://" not in t and not (path.parent / t).is_file()]
    assert not missing, f"{named(path)} links to {missing}"


def test_third_party_names_the_commit_and_carries_the_notice():
    text = THIRD_PARTY.read_text()
    assert PSTACK_COMMIT in text
    assert "https://github.com/cursor/plugins/tree/main/pstack" in text
    assert "Copyright (c) 2026 Lauren Tan" in text
    assert "Permission is hereby granted, free of charge" in text
    assert "The above copyright notice and this permission notice shall be included" in text


def test_third_party_lists_every_principle_file_and_no_other():
    text = THIRD_PARTY.read_text()
    listed = re.findall(r"^- `(features/principles/[^`]+)`$", text, re.M)
    (own,) = re.findall(r"^jstack's own: (.+)$", text, re.M)
    ours = [
        path for path in re.findall(r"`([^`]+)`", own) if path.startswith("features/principles/")
    ]
    assert sorted(listed + ours) == [str(path.relative_to(REPO)) for path in FILES]
    assert not set(listed) & set(ours)


def test_there_are_25_principles_and_the_25th_is_depth_over_breadth():
    assert len(FILES) == 25
    assert PRINCIPLES / "principle-depth-over-breadth" / "SKILL.md" in FILES


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


def test_units_that_merge_by_themselves_do_not_stack():
    assert (
        stacking("# A principle\n\nEach unit merges by itself. Rebase only on a conflict.\n") == []
    )
