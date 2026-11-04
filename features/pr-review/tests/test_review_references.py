import re

from jdrift import read_section
from testing.paths import REPO

REVIEW = REPO / "features" / "pr-review" / "the-review.md"
REFERENCES = REPO / "features" / "skill-library" / "skills" / "interrogate" / "references"


def test_the_references_the_review_fills_its_prompt_from_are_jstack_s_own():
    """pstack #986 deleted interrogate's references, and the skill-cut eval ruled its rerun-proven
    form of the review a regression, so jstack keeps them. jdrift reads each one the review's
    block fills its prompt from as jstack's own and from no upstream path: no sync of pstack
    takes the deletion with it, and jdrift never prints the review's own prompt as gone."""
    text = REVIEW.read_text()
    named = r"\"\$I/([a-z-]+\.md)\"|refs \"/([a-z-]+\.md)\""
    filled = {"".join(found) for found in re.findall(named, text)}
    assert filled == {"reviewer-prompt.md", "rubric.md", "code-quality-review.md"}
    pinned = read_section((REPO / "THIRD_PARTY.md").read_text())
    mapped = {local for locals_ in pinned.sources.values() for local in locals_}
    for name in sorted(filled):
        local = (REFERENCES / name).relative_to(REPO).as_posix()
        assert (REPO / local).is_file(), local
        assert local in pinned.own, local
        assert local not in mapped, local
    assert pinned.at("pstack/skills/interrogate/SKILL.md").startswith("ab1f702")
