import pytest

from testing.paths import REPO

FEATURE = REPO / "features" / "writing"
SKILLS = [FEATURE / "skills" / name / "SKILL.md" for name in ("unslop", "technical-writing")]
THIRD_PARTY = REPO / "THIRD_PARTY.md"
EM_DASH = "\N{EM DASH}"


def skill_problems(path):
    """What is wrong with the writing skill at `path` beyond what the frontmatter lint checks:
    em dashes."""
    return em_dashes(path.read_text())


def em_dashes(text):
    lines = [n for n, line in enumerate(text.splitlines(), 1) if EM_DASH in line]
    return [f"has an em dash on line {lines}"] if lines else []


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_lint_third_party_names_the_skill(path):
    assert f"`features/writing/skills/{path.parent.name}/SKILL.md`" in THIRD_PARTY.read_text()
