"""The grilling skill: THIRD_PARTY.md names it."""

from testing.paths import REPO

THIRD_PARTY = REPO / "THIRD_PARTY.md"


def test_lint_third_party_names_the_skill():
    assert "`features/grilling/SKILL.md`" in THIRD_PARTY.read_text()
