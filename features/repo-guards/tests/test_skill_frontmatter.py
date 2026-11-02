"""A skill its feature.json lists as `hidden` loads only when the user types it: its frontmatter
sets `disable-model-invocation: true`. Every other skill sets no such key, so a model may load it
by itself. Each skill gives a description and the name of its folder. Every skill jstack ships has
the name of its folder, in each of jstack's skill trees, and so does each skill entry of
skills.json. The fixtures show that the checks catch a skill whose key disagrees with the list,
either way, and a skill whose name is not its folder's."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from testing.paths import REPO, skills

SKILLS = [folder / "SKILL.md" for folder in skills().values()]
SHIPPED = sorted(SKILLS)
NAMED_TREE = REPO / "testing" / "tests" / "fixtures" / "skills" / "named-tree"
FIXTURES = REPO / "testing" / "tests" / "fixtures" / "skills"
KEY = "disable-model-invocation"


def front(text):
    """A skill's frontmatter as its `key: value` lines, as written, or None if it has none."""
    found = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not found:
        return None
    pairs = (line.partition(":") for line in found.group(1).splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}


def misnamed(path):
    """Whether the skill at `path` is named for its folder, as a list of what is wrong."""
    fields = front(path.read_text())
    if fields is None:
        return ["has no frontmatter"]
    if fields.get("name") != path.parent.name:
        return [f"is named {fields.get('name')!r}, not {path.parent.name!r}"]
    return []


def misnamed_entries(root):
    """Each skill item of `root`/skills.json whose name is not the folder of its path."""
    items = json.loads((root / "skills.json").read_text())["items"]
    return [
        f"skills.json names {item['path']} {item['name']!r}, not {Path(item['path']).parent.name!r}"
        for item in items
        if item["kind"] == "skill" and item["name"] != Path(item["path"]).parent.name
    ]


def hidden(root):
    """The name of each skill that `root`/skills.json marks `hidden`, as its feature.json lists
    it, or no name where there is no skills.json."""
    listed = root / "skills.json"
    if not listed.is_file():
        return frozenset()
    items = json.loads(listed.read_text())["items"]
    return frozenset(item["name"] for item in items if item.get("hidden"))


def problems(path, hidden=frozenset()):
    """Where the frontmatter of the skill at `path` disagrees with `hidden`, the skills that load
    only when typed: a hidden skill sets the key to true, and any other skill does not set it."""
    fields = front(path.read_text())
    if fields is None:
        return ["has no frontmatter"]
    found = []
    if not fields.get("description"):
        found.append("has no description")
    if path.parent.name not in hidden:
        if KEY in fields:
            found.append(f"sets {KEY}, and its feature.json does not list it as hidden")
    elif KEY not in fields:
        found.append(f"is hidden in its feature.json, and does not set {KEY}")
    elif fields[KEY] != "true":
        found.append(f"sets {KEY} to {fields[KEY]}")
    return found


def test_the_glob_finds_the_skills():
    assert len(SKILLS) >= 33


@pytest.mark.parametrize("path", SKILLS, ids=lambda path: path.parent.name)
def test_lint_a_skill_sets_the_key_as_its_feature_lists_it(path):
    assert problems(path, hidden(REPO)) == []


def holds_this_test(root):
    """Put this file in `root/tests`, with a copy of `testing/` that leaves out its tests, and
    a `pyproject.toml`. `REPO` is then `root`, so the copy's tests read its tree and not this
    checkout's."""
    (root / "tests").mkdir()
    shutil.copy(__file__, root / "tests")
    shutil.copytree(
        REPO / "testing", root / "testing", ignore=shutil.ignore_patterns("__pycache__", "tests")
    )
    if not (root / "pyproject.toml").exists():
        (root / "pyproject.toml").write_text("")


@pytest.mark.parametrize("mended", [False, True], ids=["broken", "mended"])
@pytest.mark.parametrize(
    ("fixture", "listed"), [("no-key", True), ("extra-key", False)], ids=["no-key", "extra-key"]
)
def test_lint_fails_on_the_broken_fixture_and_passes_it_mended(tmp_path, fixture, listed, mended):
    """The test gives the lint a skills folder that holds only the fixture, and a skills.json
    that lists it as hidden or not, and has it run as CI runs it. The fixture disagrees with the
    list, and mending it adds the key it lacks or takes out the key it has."""
    holds_this_test(tmp_path)
    source = FIXTURES / fixture / "SKILL.md"
    skill = tmp_path / "skills" / fixture / "SKILL.md"
    skill.parent.mkdir(parents=True)
    item = {"name": fixture, "kind": "skill", "path": f"skills/{fixture}/SKILL.md"}
    (tmp_path / "skills.json").write_text(
        json.dumps({"items": [item | ({"hidden": True} if listed else {})]})
    )
    first, *rest = source.read_text().splitlines(keepends=True)
    if mended and listed:
        rest = [f"{KEY}: true\n", *rest]
    elif mended:
        rest = [line for line in rest if not line.startswith(f"{KEY}:")]
    skill.write_text("".join([first, *rest]))
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", "as_its_feature"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    failed = re.findall(r"^FAILED (\S+)", done.stdout, re.M)
    module = "tests/test_skill_frontmatter.py::"
    expected = (
        []
        if mended
        else [f"{module}test_lint_a_skill_sets_the_key_as_its_feature_lists_it[{fixture}]"]
    )
    assert (done.returncode, failed) == (0 if mended else 1, expected), done.stdout


GOOD = """\
---
name: a-skill
description: Do a thing.
disable-model-invocation: true
---

# A
"""


def check(tmp_path, text, hidden=frozenset({"a-skill"})):
    path = tmp_path / "a-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return problems(path, hidden)


def test_a_skill_hidden_from_the_model_has_no_problem(tmp_path):
    assert check(tmp_path, GOOD) == []


def test_a_skill_the_model_may_load_has_no_key_and_no_problem(tmp_path):
    assert check(tmp_path, GOOD.replace(f"{KEY}: true\n", ""), hidden=frozenset()) == []


def test_a_key_on_a_skill_not_listed_hidden_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD, hidden=frozenset()) == [
        f"sets {KEY}, and its feature.json does not list it as hidden"
    ]


def test_the_list_comes_from_skills_json(tmp_path):
    items = [{"name": "a-skill", "kind": "skill", "hidden": True}, {"name": "b", "kind": "skill"}]
    (tmp_path / "skills.json").write_text(json.dumps({"items": items}))
    assert hidden(tmp_path) == {"a-skill"}


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
    assert check(tmp_path, text) == [f"is hidden in its feature.json, and does not set {KEY}"]


def test_a_name_that_is_not_the_folder_is_a_problem(tmp_path):
    path = tmp_path / "a-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(GOOD.replace("a-skill", "other"))
    assert misnamed(path) == ["is named 'other', not 'a-skill'"]


def test_no_description_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD.replace("Do a thing.", "")) == ["has no description"]


def test_no_frontmatter_is_a_problem(tmp_path):
    assert check(tmp_path, "# A\n") == ["has no frontmatter"]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda path: str(path.parent.relative_to(REPO)))
def test_every_shipped_skill_is_named_for_its_folder(path):
    assert misnamed(path) == []


@pytest.mark.skipif(
    not (REPO / "skills.json").is_file(), reason="no skills.json yet: the generator writes it"
)
def test_every_skill_entry_in_skills_json_is_named_for_its_folder():
    assert misnamed_entries(REPO) == []


@pytest.mark.parametrize("renamed", [False, True], ids=["as-named", "renamed"])
def test_a_tree_whose_folders_are_renamed_fails_with_the_folder_and_the_name(tmp_path, renamed):
    """This runs the name checks as CI runs them, over a FAKE tree whose folders the test
    renamed."""
    shutil.copytree(NAMED_TREE, tmp_path, dirs_exist_ok=True)
    holds_this_test(tmp_path)
    if renamed:
        (tmp_path / "skills/fake-skill").rename(tmp_path / "skills/fake-renamed")
        listed = tmp_path / "skills.json"
        listed.write_text(listed.read_text().replace("skills/fake-skill/", "skills/fake-renamed/"))
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", "named_for_its"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    failed = sorted(re.findall(r"^FAILED (\S+)", done.stdout, re.M))
    module = "tests/test_skill_frontmatter.py::"
    expected = (
        [
            f"{module}test_every_shipped_skill_is_named_for_its_folder[skills/fake-renamed]",
            f"{module}test_every_skill_entry_in_skills_json_is_named_for_its_folder",
        ]
        if renamed
        else []
    )
    assert (done.returncode, failed) == (1 if renamed else 0, expected), done.stdout
    if renamed:
        assert "is named 'fake-skill', not 'fake-renamed'" in done.stdout
        assert "names skills/fake-renamed/SKILL.md 'fake-skill', not 'fake-renamed'" in done.stdout
