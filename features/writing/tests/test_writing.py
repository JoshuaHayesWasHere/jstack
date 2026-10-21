import re

import pytest

from jbriefs.skills import listed
from testing.paths import REPO

FEATURE = REPO / "features" / "writing"
SKILLS = [FEATURE / "skills" / name / "SKILL.md" for name in ("unslop", "technical-writing")]
TEMPLATE = REPO / "features" / "pr-review" / "templates" / "pr-body.md"
PLAYBOOK = FEATURE / "playbooks" / "opening-a-pr.md"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
EM_DASH = "\N{EM DASH}"
HEADINGS = ["Why", "What changed", "Scope", "Tradeoffs", "Blast radius", "Verification"]
NEVER_DROPPED = "Scope"
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def skill_problems(path):
    """What is wrong with the writing skill at `path` beyond what the frontmatter lint checks:
    em dashes."""
    return em_dashes(path.read_text())


def em_dashes(text):
    lines = [n for n, line in enumerate(text.splitlines(), 1) if EM_DASH in line]
    return [f"has an em dash on line {lines}"] if lines else []


def headings(text):
    return re.findall(r"^## (.+)$", text, re.M)


def build(template, drop=()):
    """A pull request body from the template: every placeholder filled, `drop` left out."""
    sections = re.split(r"^(?=## )", template, flags=re.M)
    kept = [s for s in sections if not any(s.startswith(f"## {name}\n") for name in drop)]
    return PLACEHOLDER.sub("The check command printed 3 passed.", "".join(kept))


def body_problems(body, dropped=()):
    """What is wrong with a pull request body that left out the headings in `dropped`."""
    found = []
    wanted = [name for name in HEADINGS if name not in dropped]
    if NEVER_DROPPED in dropped:
        found.append(f"drops {NEVER_DROPPED}")
    if headings(body) != wanted:
        missing = [name for name in wanted if name not in headings(body)]
        found.append(f"lacks {missing}" if missing else f"has the headings {headings(body)}")
    if PLACEHOLDER.search(body):
        found.append("has a placeholder left")
    under = re.findall(r"^## (.+)\n((?:(?!## ).*\n?)*)", body, re.M)
    empty = [name for name, text in under if not text.strip()]
    if empty:
        found.append(f"has nothing under {empty}")
    return found + em_dashes(body)


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_a_writing_skill_loads_only_when_typed(path):
    assert skill_problems(path) == []


@pytest.mark.parametrize("path", [TEMPLATE, PLAYBOOK], ids=lambda path: path.stem)
def test_no_em_dash(path):
    assert em_dashes(path.read_text()) == []


def test_a_body_built_from_the_template_has_every_heading():
    assert body_problems(build(TEMPLATE.read_text())) == []


@pytest.mark.parametrize("name", [name for name in HEADINGS if name != NEVER_DROPPED])
def test_a_body_may_drop_a_heading_with_nothing_to_say(name):
    assert body_problems(build(TEMPLATE.read_text(), drop=[name]), dropped=[name]) == []


def test_the_playbook_step_names_a_template_that_builds_a_body_and_two_skills_that_load():
    step = re.search(r"^5\. .*?(?=^\d\. )", PLAYBOOK.read_text(), re.M | re.S).group()
    named = [REPO / name for name in re.findall(r"`((?:features|skills)/[^`]+\.md)`", step)]
    templates = [path for path in named if path in listed("template", REPO).values()]
    skills = [path for path in named if path not in templates]
    assert templates == [TEMPLATE]
    assert skills == [listed("skill", REPO)[path.parent.name] for path in skills]
    assert [body_problems(build(path.read_text())) for path in templates] == [[]]
    assert [skill_problems(path) for path in skills] == [[], []]


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_lint_third_party_names_the_skill(path):
    assert f"`features/writing/skills/{path.parent.name}/SKILL.md`" in THIRD_PARTY.read_text()


GOOD_SKILL = """\
---
name: a-skill
description: Cut it.
disable-model-invocation: true
---

# A
"""
GOOD_BODY = "".join(f"## {name}\nOne plain sentence.\n\n" for name in HEADINGS)


def check(tmp_path, text):
    path = tmp_path / "a-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return skill_problems(path)


def test_an_em_dash_in_a_skill_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD_SKILL + f"\nOne thing {EM_DASH} and another.\n") == [
        "has an em dash on line [9]"
    ]


def test_a_full_body_has_no_problem():
    assert body_problems(GOOD_BODY) == []


@pytest.mark.parametrize("name", HEADINGS)
def test_a_template_with_a_heading_missing_builds_a_body_with_a_problem(name):
    template = "".join(f"## {each}\n<what to say>\n\n" for each in HEADINGS if each != name)
    assert body_problems(build(template)) == [f"lacks {[name]}"]


def test_a_body_with_its_headings_out_of_order_is_a_problem():
    body = "".join(f"## {name}\nOne plain sentence.\n\n" for name in reversed(HEADINGS))
    assert body_problems(body) == [f"has the headings {HEADINGS[::-1]}"]


def test_a_body_that_drops_scope_is_a_problem():
    assert body_problems(build(GOOD_BODY, drop=[NEVER_DROPPED]), dropped=[NEVER_DROPPED]) == [
        f"drops {NEVER_DROPPED}"
    ]


def test_a_placeholder_left_in_a_body_is_a_problem():
    assert body_problems(GOOD_BODY.replace("One plain sentence.", "<what to say>", 1)) == [
        "has a placeholder left"
    ]


def test_a_heading_with_nothing_under_it_is_a_problem():
    assert body_problems(GOOD_BODY.replace("One plain sentence.\n", "", 1)) == [
        "has nothing under ['Why']"
    ]
