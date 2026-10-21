"""`scripts/generate-jstack-trees.py [--check]`: what the generator writes from features/, and
that a stale output fails the check by name. Each test runs the script, or `jtrees`, over a
copy of this checkout."""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = "scripts/generate-jstack-trees.py"
sys.path.insert(0, str(REPO / "scripts"))

from jtrees.crawl import Invalid, borders, crawl, tracked  # noqa: E402


def generate(root, *args):
    return subprocess.run(
        [sys.executable, "-I", root / SCRIPT, *args], cwd=root, capture_output=True, text=True
    )


@pytest.fixture
def copy(tmp_path):
    """This checkout's files, tracked and not yet added, with no git and no .venv."""
    root = tmp_path / "jstack"
    for path in tracked(REPO):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / path, target, follow_symlinks=False)
    return root


def test_the_committed_outputs_are_what_the_generator_writes():
    ran = generate(REPO, "--check")
    assert (ran.returncode, ran.stderr) == (0, "")


def test_a_skill_description_edit_makes_the_check_fail_naming_skills_json(copy):
    skill = copy / "skills" / "bro" / "SKILL.md"
    skill.write_text(skill.read_text().replace("description: ", "description: Now ", 1))
    before = (copy / "skills.json").read_bytes()
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert ran.stderr.splitlines() == [
        "stale: skills.json",
        f"run python3 {SCRIPT} and commit the result",
    ]
    assert (copy / "skills.json").read_bytes() == before


def test_a_run_writes_what_is_stale_and_a_second_run_writes_nothing(copy):
    skill = copy / "skills" / "bro" / "SKILL.md"
    skill.write_text(skill.read_text().replace("description: ", "description: Now ", 1))
    assert generate(copy).stdout == "wrote skills.json\n"
    assert generate(copy).stdout.startswith("current: ")
    assert generate(copy, "--check").returncode == 0
    (bro,) = [
        one
        for one in json.loads((copy / "skills.json").read_text())["items"]
        if one["name"] == "bro"
    ]
    assert bro["description"].startswith("Now ")


FOO = {
    "$schema": "../../schemas/feature.schema.json",
    "name": "foo",
    "description": "Does foo.",
    "packages": ["src/foo"],
    "commands": {"foo": "foo.cli:main"},
    "docs": ["docs/foo.md"],
    "hooks": [
        {"event": "SessionStart", "script": "hooks/foo-start.sh", "harnesses": ["claude-code"]}
    ],
    "nameable": ["foo-run"],
}
GENERATED = "<!-- generated: pages by the generator; do not edit -->\n<!-- generated: end -->\n"


def foo(root):
    """A feature with a skill, a playbook, a template, a package, a command, a page with its
    own folder of pages, a hook and a test folder, all under features/foo/."""
    folder = root / "features" / "foo"
    for path, text in {
        "feature.json": json.dumps(FOO),
        "SKILL.md": "---\nname: foo\ndescription: Do foo.\n---\n\n# Foo\n",
        "playbooks/foo-run.md": "# Foo run\n\nRun by: a crewmate, for foo.\n",
        "templates/foo.md": "A foo.\n",
        "src/foo/__init__.py": "",
        "src/foo/cli.py": "def main():\n    return 0\n",
        "docs/foo.md": f"# foo\n\n{GENERATED}",
        "docs/foo/a-topic.md": "# A topic\n",
        "hooks/foo-start.sh": "#!/bin/sh\n",
        "tests/test_foo.py": "",
    }.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(text)


def test_a_new_feature_shows_in_every_output_with_no_list_edited(copy):
    foo(copy)
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert set(ran.stderr.splitlines()[:-1]) == {
        "stale: README.md",
        "stale: docs/hooks.md",
        "stale: docs/playbooks.md",
        "stale: features/foo/docs/foo.md",
        "stale: pyproject.toml",
        "stale: skills.json",
    }
    assert generate(copy).returncode == 0
    items = {
        (one["kind"], one["name"]): one
        for one in json.loads((copy / "skills.json").read_text())["items"]
    }
    assert items["skill", "foo"]["path"] == "features/foo/SKILL.md"
    assert items["playbook", "foo-run"] == {
        "name": "foo-run",
        "kind": "playbook",
        "path": "features/foo/playbooks/foo-run.md",
        "source": "josh",
        "nameable": True,
    }
    assert items["template", "foo.md"]["path"] == "features/foo/templates/foo.md"
    project = tomllib.loads((copy / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["foo"] == "foo.cli:main"
    assert (
        "features/foo/src/foo" in project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    )
    assert "features/foo/src" in project["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert "features/foo/tests" in project["tool"]["pytest"]["ini_options"]["testpaths"]
    assert "features/foo/tests" in project["tool"]["ruff"]["src"]
    readme = (copy / "README.md").read_text()
    assert "| `foo` | [features/foo/docs/foo.md](features/foo/docs/foo.md) | Does foo. |" in readme
    assert "[foo](../features/foo/SKILL.md)" in (copy / "docs" / "playbooks.md").read_text()
    assert (
        "[foo-run](../features/foo/playbooks/foo-run.md)"
        in (copy / "docs" / "playbooks.md").read_text()
    )
    hooks = (copy / "docs" / "hooks.md").read_text()
    assert (
        "| `SessionStart` | [features/foo/hooks/foo-start.sh](../features/foo/hooks/foo-start.sh) |"
        in hooks
    )
    assert (
        "- [A topic](foo/a-topic.md)\n"
        in (copy / "features" / "foo" / "docs" / "foo.md").read_text()
    )
    assert generate(copy, "--check").returncode == 0


def test_a_page_added_to_the_jbus_folder_without_the_index_is_stale(copy):
    (copy / "docs" / "jbus" / "a-new-page.md").write_text("# A new page\n\nIts words.\n")
    ran = generate(copy, "--check")
    assert ran.stderr.splitlines()[0] == "stale: docs/jbus.md"
    generate(copy)
    assert "- [A new page](jbus/a-new-page.md)\n" in (copy / "docs" / "jbus.md").read_text()


@pytest.mark.parametrize(
    ("change", "fault"),
    [
        (
            lambda root: (root / "features" / "jpack" / "feature.json").write_text(
                (root / "features" / "jpack" / "feature.json")
                .read_text()
                .replace('"jpack",', '"jpacks",', 1)
            ),
            "features/jpack/feature.json: names 'jpacks', not its folder 'jpack'",
        ),
        (
            lambda root: (root / "features" / "bro" / "feature.json").write_text(
                json.dumps(
                    {
                        "$schema": "../../schemas/feature.schema.json",
                        "name": "bro",
                        "description": "x",
                        "owns": ["skills/bro/**"],
                        "extra": 1,
                    }
                )
            ),
            "features/bro/feature.json: /: has extra, which the schema does not allow",
        ),
        (
            lambda root: (root / "plugin.json").write_text(
                (root / "plugin.json").read_text().replace('"0.1.0"', '"9.9.9"')
            ),
            "plugin.json: version '9.9.9' is not pyproject's '0.1.0'",
        ),
        (
            lambda root: (root / "features" / "empty").mkdir(),
            "features/empty: has neither feature.json nor SKILL.md",
        ),
    ],
)
def test_a_tree_that_breaks_a_rule_is_refused_with_its_fault_and_nothing_is_written(
    copy, change, fault
):
    change(copy)
    before = (copy / "skills.json").read_bytes()
    ran = generate(copy)
    assert ran.returncode == 2
    assert f"invalid: {fault}" in ran.stderr.splitlines()
    assert (copy / "skills.json").read_bytes() == before


def test_every_file_of_the_checkout_has_exactly_one_owner():
    unowned, twice = borders(crawl(REPO), tracked(REPO))
    assert (unowned, twice) == ([], {})


def test_an_owner_is_the_feature_folder_or_one_row_and_two_rows_are_both_seen(copy):
    tree = crawl(copy)
    assert tree.owners("features/jbus/feature.json") == ("jbus",)
    assert tree.owners("src/jbus/cli.py") == ("jbus",)
    assert tree.owners("skills/bro/SKILL.md") == ("bro",)
    assert tree.owners("pyproject.toml") == ("INFRA",)
    assert tree.owners("nowhere/at/all.txt") == ()
    manifest = copy / "features" / "bro" / "feature.json"
    manifest.write_text(
        manifest.read_text().replace('"skills/bro/**"', '"skills/bro/**", "src/jbus/cli.py"')
    )
    assert crawl(copy).owners("src/jbus/cli.py") == ("bro", "jbus")


def test_the_crawl_raises_every_fault_at_once(copy):
    for name in ("bro", "tdd"):
        (copy / "features" / name / "feature.json").write_text("{}")
    with pytest.raises(Invalid) as raised:
        crawl(copy)
    assert {fault.split(":")[0] for fault in raised.value.faults} >= {
        "features/bro/feature.json",
        "features/tdd/feature.json",
    }
