import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILLS = [REPO / "skills" / name / "SKILL.md" for name in ("unslop", "technical-writing")]
TEMPLATE = REPO / "templates" / "pr-body.md"
PLAYBOOK = REPO / "playbooks" / "opening-a-pr.md"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
EM_DASH = "\N{EM DASH}"
HEADINGS = ["Why", "What changed", "Scope", "Tradeoffs", "Blast radius", "Verification"]
NEVER_DROPPED = "Scope"
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def frontmatter(text):
    """The keys and values between the two `---` lines a skill opens with, as written."""
    found = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not found:
        return {}
    pairs = (line.partition(":") for line in found.group(1).splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}


def skill_problems(path):
    """What stops the skill at `path` from being one that loads only when it is typed."""
    text = path.read_text()
    front = frontmatter(text)
    found = []
    if not front:
        found.append("has no frontmatter")
    elif front.get("name") != path.parent.name:
        found.append(f"is named {front.get('name')}")
    if front and "disable-model-invocation" not in front:
        found.append("does not set disable-model-invocation")
    elif front and front["disable-model-invocation"] != "true":
        found.append(f"sets disable-model-invocation to {front['disable-model-invocation']}")
    return found + em_dashes(text)


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
    step = re.search(r"^5\. .*$", PLAYBOOK.read_text(), re.M).group()
    named = [REPO / name for name in re.findall(r"`((?:skills|templates)/[^`]+\.md)`", step)]
    templates = [path for path in named if path.parent == TEMPLATE.parent]
    skills = [path for path in named if path not in templates]
    assert [body_problems(build(path.read_text())) for path in templates] == [[]]
    assert [skill_problems(path) for path in skills] == [[], []]


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_lint_third_party_names_the_skill(path):
    assert f"`skills/{path.parent.name}/SKILL.md`" in THIRD_PARTY.read_text()


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


def test_a_skill_that_is_hidden_from_the_model_has_no_problem(tmp_path):
    assert check(tmp_path, GOOD_SKILL) == []


def test_a_quoted_description_with_a_colon_is_read(tmp_path):
    text = GOOD_SKILL.replace("Cut it.", '"A standard: four layers."')
    assert frontmatter(text)["description"] == '"A standard: four layers."'
    assert check(tmp_path, text) == []


def test_a_skill_the_model_may_load_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD_SKILL.replace("disable-model-invocation: true\n", "")) == [
        "does not set disable-model-invocation"
    ]


@pytest.mark.parametrize(
    "value", ["false", "yes", "", pytest.param('"true"', id="a quoted true is a string to YAML")]
)
def test_a_value_that_is_not_true_is_a_problem(tmp_path, value):
    assert check(tmp_path, GOOD_SKILL.replace(": true", f": {value}")) == [
        f"sets disable-model-invocation to {value}"
    ]


def test_a_key_in_the_text_and_not_the_frontmatter_is_a_problem(tmp_path):
    text = GOOD_SKILL.replace("disable-model-invocation: true\n", "")
    assert check(tmp_path, text + "\ndisable-model-invocation: true\n") == [
        "does not set disable-model-invocation"
    ]


def test_no_frontmatter_is_a_problem(tmp_path):
    assert check(tmp_path, "# A\n") == ["has no frontmatter"]


def test_a_name_that_is_not_the_directory_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD_SKILL.replace("a-skill", "other")) == ["is named other"]


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
