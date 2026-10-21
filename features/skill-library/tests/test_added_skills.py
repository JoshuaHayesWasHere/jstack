"""The skills added after the first eleven: each is typed only, its shell blocks are run, and
each subagent it starts is a read-only Explore agent its tool takes. The tests of what one
skill's blocks print are in its own feature's folder."""

import re

import pytest

from skill_blocks import COPY, SKILLS, blocks, home, repo, run
from test_tool_calls import CALLS, errors

__all__ = ["home", "repo"]

EM_DASH = "\N{EM DASH}"
BEFORE = {
    "correct",
    "crew",
    "expert",
    "grilling",
    "handoff",
    "home",
    "nohome",
    "pr-review",
    "reflect",
    "scout",
    "technical-writing",
    "unslop",
}
ADDED = sorted(name for name in SKILLS if name not in BEFORE)
BUILT_IN = set(
    """
    add-dir agents bashes bug clear code-review compact config context copy cost diff doctor
    effort exit export fast feedback help hooks ide init insights login logout loop mcp
    memory model permissions plan plugin pr-comments quit release-notes rename resume review
    rewind run sandbox schedule security-review simplify skills stats status statusline
    tasks terminal-setup theme todos upgrade usage vim workflows
    """.split()
)
NOT_IN_A_SUBAGENT_CALL = {"model", "effort", "isolation"}
SUBAGENT_CALLS = [
    call for call in CALLS if call.tool == "Agent" and call.where.split(":")[0] in ADDED
]


def test_each_skill_listed_as_here_before_the_understanding_skills_is_still_a_skill():
    assert BEFORE <= set(SKILLS)


def front(text):
    """A skill's frontmatter as its `key: value` lines, as written, or None if it has none."""
    found = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not found:
        return None
    pairs = (line.partition(":") for line in found.group(1).splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}


def em_dashes(path):
    lines = [n for n, line in enumerate(path.read_text().splitlines(), 1) if EM_DASH in line]
    return [f"{path.name} has an em dash on line {lines}"] if lines else []


def problems(directory):
    """What is wrong with the skill in `directory` beyond what `test_skill_frontmatter.py` checks:
    a built-in command's name, and em dashes."""
    skill = directory / "SKILL.md"
    if not skill.is_file():
        return ["has no SKILL.md"]
    fields = front(skill.read_text())
    if fields is None:
        return ["has no frontmatter"]
    found = []
    name = fields.get("name")
    if name in BUILT_IN:
        found.append(f"has the name of the built-in command /{name}")
    for path in sorted(directory.rglob("*.md")):
        found += em_dashes(path)
    return found


def named_files(skill):
    """Every file a skill's text names by a path from its own directory."""
    text = skill.read_text()
    paths = re.findall(r"`((?:references|\.\.)/[^`<>*\s]+\.md)`", text)
    paths += re.findall(r"\]\(((?:\.|references)[^)\s]*)\)", text)
    return sorted(set(paths))


def test_skills_were_added():
    assert ADDED != []


@pytest.mark.parametrize("name", ADDED)
def test_an_added_skill_has_no_problem(name):
    assert problems(SKILLS[name]) == []


@pytest.mark.parametrize("name", ADDED)
def test_every_file_an_added_skill_names_is_there(name):
    skill = COPY / "skills" / name / "SKILL.md"
    missing = [path for path in named_files(skill) if not (skill.parent / path).is_file()]
    assert missing == []


@pytest.mark.parametrize(
    ("name", "body"),
    [
        pytest.param(name, body, id=f"{name}:{number}")
        for name in ADDED
        for number, body in enumerate(blocks((SKILLS[name] / "SKILL.md").read_text(), "sh"), 1)
    ],
)
def test_every_block_of_an_added_skill_runs_and_says_something(name, body, repo, home):
    assert run(body, repo, home) != []


@pytest.mark.parametrize("call", SUBAGENT_CALLS, ids=lambda call: call.where)
def test_a_subagent_an_added_skill_starts_is_read_only_on_this_sessions_model(call):
    given = call.given
    assert errors(call, given) == []
    assert given.get("subagent_type") == "Explore"
    assert NOT_IN_A_SUBAGENT_CALL & set(given) == set()


GOOD = """\
---
name: a-skill
description: Explain it.
disable-model-invocation: true
---

# A
"""


def check(tmp_path, text, name="a-skill"):
    path = tmp_path / name / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return problems(path.parent)


def test_a_skill_hidden_from_the_model_has_no_problem(tmp_path):
    assert check(tmp_path, GOOD) == []


def test_the_name_of_a_built_in_command_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD.replace("a-skill", "review"), name="review") == [
        "has the name of the built-in command /review"
    ]


def test_no_frontmatter_and_no_skill_file_are_problems(tmp_path):
    assert check(tmp_path, "# A\n") == ["has no frontmatter"]
    (tmp_path / "empty").mkdir()
    assert problems(tmp_path / "empty") == ["has no SKILL.md"]


def test_an_em_dash_in_a_file_beside_the_skill_is_a_problem(tmp_path):
    check(tmp_path, GOOD)
    reference = tmp_path / "a-skill" / "references" / "prompt.md"
    reference.parent.mkdir()
    reference.write_text(f"One thing {EM_DASH} and another.\n")
    assert problems(tmp_path / "a-skill") == ["prompt.md has an em dash on line [1]"]


def test_a_block_inside_a_list_is_found_with_its_indent_taken_off():
    text = (
        "1. a\n\n   ```sh\n   if true; then\n       echo b\n   fi\n   ```\n\n```sh\necho c\n```\n"
    )
    assert blocks(text, "sh") == ["if true; then\n    echo b\nfi\n", "echo c\n"]
