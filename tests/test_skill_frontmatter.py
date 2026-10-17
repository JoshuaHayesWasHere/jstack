"""Every skill loads only when typed: its frontmatter sets `disable-model-invocation: true`, and
names it for its folder with a description. The broken fixture shows the check catches one that
does not."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILLS = sorted(REPO.glob("skills/*/SKILL.md"))
NO_KEY = Path(__file__).parent / "fixtures" / "skills" / "no-key" / "SKILL.md"
KEY = "disable-model-invocation"


def front(text):
    """A skill's frontmatter as its `key: value` lines, as written, or None if it has none."""
    found = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not found:
        return None
    pairs = (line.partition(":") for line in found.group(1).splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}


def problems(path):
    """What stops the skill at `path` from being one that loads only when it is typed."""
    fields = front(path.read_text())
    if fields is None:
        return ["has no frontmatter"]
    found = []
    if fields.get("name") != path.parent.name:
        found.append(f"is named {fields.get('name')!r}, not {path.parent.name!r}")
    if not fields.get("description"):
        found.append("has no description")
    if KEY not in fields:
        found.append(f"does not set {KEY}")
    elif fields[KEY] != "true":
        found.append(f"sets {KEY} to {fields[KEY]}")
    return found


def test_the_glob_finds_the_skills():
    assert len(SKILLS) >= 33


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_lint_a_skill_loads_only_when_typed(path):
    assert problems(path) == []


@pytest.mark.parametrize("mended", [False, True], ids=["broken", "mended"])
def test_lint_fails_on_the_broken_fixture_and_passes_it_mended(tmp_path, mended):
    """The lint, run as CI runs it, over a skills folder that holds only the fixture."""
    (tmp_path / "tests").mkdir()
    shutil.copy(__file__, tmp_path / "tests")
    skill = tmp_path / "skills" / NO_KEY.parent.name / NO_KEY.name
    skill.parent.mkdir(parents=True)
    first, *rest = NO_KEY.read_text().splitlines(keepends=True)
    skill.write_text("".join([first, *([f"{KEY}: true\n"] if mended else []), *rest]))
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", "only_when_typed"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    failed = re.findall(r"^FAILED (\S+)", done.stdout, re.M)
    expected = (
        []
        if mended
        else ["tests/test_skill_frontmatter.py::test_lint_a_skill_loads_only_when_typed[no-key]"]
    )
    assert (done.returncode, failed) == (0 if mended else 1, expected)


GOOD = """\
---
name: a-skill
description: Do a thing.
disable-model-invocation: true
---

# A
"""


def check(tmp_path, text):
    path = tmp_path / "a-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return problems(path)


def test_a_skill_hidden_from_the_model_has_no_problem(tmp_path):
    assert check(tmp_path, GOOD) == []


@pytest.mark.parametrize(
    "value", ["false", "yes", "", pytest.param('"true"', id="a quoted true is a string to YAML")]
)
def test_a_value_that_is_not_true_is_a_problem(tmp_path, value):
    assert check(tmp_path, GOOD.replace(": true", f": {value}")) == [f"sets {KEY} to {value}"]


def test_a_quoted_description_with_a_colon_is_read(tmp_path):
    text = GOOD.replace("Do a thing.", '"A standard: four layers."')
    assert front(text)["description"] == '"A standard: four layers."'
    assert check(tmp_path, text) == []


def test_a_key_in_the_text_and_not_the_frontmatter_is_a_problem(tmp_path):
    text = GOOD.replace(f"{KEY}: true\n", "") + f"\n{KEY}: true\n"
    assert check(tmp_path, text) == [f"does not set {KEY}"]


def test_a_name_that_is_not_the_folder_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD.replace("a-skill", "other")) == ["is named 'other', not 'a-skill'"]


def test_no_description_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD.replace("Do a thing.", "")) == ["has no description"]


def test_no_frontmatter_is_a_problem(tmp_path):
    assert check(tmp_path, "# A\n") == ["has no frontmatter"]
