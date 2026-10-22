"""`scripts/generate-jstack-trees.py [--check]`: what the generator writes from features/, and
that a stale output fails the check by name. Each test runs the script, or `jtrees`, over a
copy of this checkout."""

import importlib
import json
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

from jbriefs import skills
from jinstall import layout
from jinstall.harnesses import CLAUDE_CODE
from testing.paths import REPO

SCRIPT = "scripts/generate-jstack-trees.py"
sys.path.insert(0, str(REPO / "scripts"))

jtrees = importlib.import_module("jtrees.crawl")
Invalid, borders, crawl, tracked = jtrees.Invalid, jtrees.borders, jtrees.crawl, jtrees.tracked


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
    skill = copy / "features" / "bro" / "SKILL.md"
    skill.write_text(skill.read_text().replace("description: ", "description: Now ", 1))
    before = (copy / "skills.json").read_bytes()
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert ran.stderr.splitlines() == [
        "stale: skills.json",
        f"run python3 {SCRIPT} and commit the result",
    ]
    assert (copy / "skills.json").read_bytes() == before


def test_a_hand_edit_inside_a_generated_region_makes_the_check_fail_naming_that_file(copy):
    page = copy / "CATALOG.md"
    page.write_text(page.read_text().replace("| `bro` |", "| `bro-edited` |", 1))
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert ran.stderr.splitlines() == [
        "stale: CATALOG.md",
        f"run python3 {SCRIPT} and commit the result",
    ]


def test_a_run_writes_what_is_stale_and_a_second_run_writes_nothing(copy):
    skill = copy / "features" / "bro" / "SKILL.md"
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


@pytest.mark.parametrize("part", ["commands", "catalog", "hooks"])
def test_a_region_that_joins_every_feature_in_a_page_a_feature_owns_is_refused(copy, part):
    page = copy / "features" / "jleak" / "docs" / "jleak.md"
    page.write_text(page.read_text() + f"\n<!-- generated: {part} -->\n<!-- generated: end -->\n")
    ran = generate(copy, "--check")
    assert ran.returncode == 2
    said = "features/jleak/docs/jleak.md: is jleak's, and holds a region that joins every feature"
    assert f"{said}, ['{part}']" in ran.stderr
    assert generate(copy).returncode == 2


def test_a_new_feature_shows_in_every_output_with_no_list_edited(copy):
    foo(copy)
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert set(ran.stderr.splitlines()[:-1]) == {
        "stale: README.md",
        "stale: CATALOG.md",
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
    hooks = json.loads((copy / "skills.json").read_text())["hooks"]
    assert {
        "name": "foo-start.sh",
        "path": "features/foo/hooks/foo-start.sh",
        "harnesses": ["claude-code"],
        "events": [{"harness": "claude-code", "event": "SessionStart"}],
    } in hooks
    laid = layout.assemble(copy, CLAUDE_CODE).entries
    assert sorted(path for path in laid if "foo" in path) == [
        "hooks/foo-start.sh",
        "playbooks/foo-run.md",
        "skills/foo/SKILL.md",
        "templates/foo.md",
    ]
    project = tomllib.loads((copy / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["foo"] == "foo.cli:main"
    assert (
        "features/foo/src/foo" in project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    )
    assert "features/foo/src" in project["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert "features/foo/tests" in project["tool"]["pytest"]["ini_options"]["testpaths"]
    assert "features/foo/tests" in project["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert "features/foo/tests" in project["tool"]["ruff"]["src"]
    readme = (copy / "README.md").read_text()
    assert "| `foo` | [features/foo/docs/foo.md](features/foo/docs/foo.md) | Does foo. |" in readme
    catalog = (copy / "CATALOG.md").read_text()
    assert "[foo](features/foo/SKILL.md)" in catalog
    assert "[foo-run](features/foo/playbooks/foo-run.md)" in catalog
    assert (
        "| `SessionStart` | [features/foo/hooks/foo-start.sh](features/foo/hooks/foo-start.sh) |"
        in catalog
    )
    assert (
        "- [A topic](foo/a-topic.md)\n"
        in (copy / "features" / "foo" / "docs" / "foo.md").read_text()
    )
    assert generate(copy, "--check").returncode == 0


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=jtrees", "-c", "user.email=jtrees@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def unmoved(root, name):
    """A feature whose package, command, page, hook, skill and test sit at the repo root, as a
    feature's do before its move: its manifest owns them there."""
    files = {
        f"src/{name}/__init__.py": "",
        f"src/{name}/cli.py": "def main():\n    return 0\n",
        f"docs/{name}.md": f"# {name}\n",
        f"hooks/{name}-start.sh": "#!/bin/sh\n",
        f"skills/{name}/SKILL.md": f"---\nname: {name}\ndescription: Do {name}.\n---\n\n# {name}\n",
        f"tests/test_{name}.py": "",
    }
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    manifest = {
        "$schema": "../../schemas/feature.schema.json",
        "name": name,
        "description": f"Does {name}.",
        "packages": [f"src/{name}"],
        "commands": {name: f"{name}.cli:main"},
        "docs": [f"docs/{name}.md"],
        "hooks": [
            {"event": "SessionStart", "script": f"hooks/{name}-start.sh", "harnesses": ["codex"]}
        ],
        "owns": [f"src/{name}/**", f"docs/{name}.md", f"hooks/{name}-start.sh"]
        + [f"skills/{name}/**", f"tests/test_{name}.py"],
    }
    (root / "features" / name).mkdir(parents=True)
    (root / "features" / name / "feature.json").write_text(json.dumps(manifest))


def move(root, name):
    """Move the feature's files into features/<name>/, drop its owns rows, and regenerate."""
    folder = f"features/{name}"
    for old, new in {
        f"src/{name}": f"{folder}/src/{name}",
        f"docs/{name}.md": f"{folder}/docs/{name}.md",
        f"hooks/{name}-start.sh": f"{folder}/hooks/{name}-start.sh",
        f"skills/{name}/SKILL.md": f"{folder}/SKILL.md",
        f"tests/test_{name}.py": f"{folder}/tests/test_{name}.py",
    }.items():
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        assert git(root, "mv", old, new).returncode == 0
    manifest = root / folder / "feature.json"
    manifest.write_text(json.dumps(json.loads(manifest.read_text()) | {"owns": []}))
    assert generate(root).returncode == 0


def test_two_moves_of_different_features_from_one_base_merge_with_no_conflict(copy):
    """foo and qux move on two branches, while bar stays where it is, as some feature does until
    the last move, so the root folders they leave are not emptied by the merge."""
    for name in ("foo", "qux", "bar"):
        unmoved(copy, name)
    assert generate(copy).returncode == 0
    assert git(copy, "init", "-q", "-b", "main").returncode == 0
    assert git(copy, "add", "-A").returncode == 0
    assert git(copy, "commit", "-qm", "base").returncode == 0
    for name in ("foo", "qux"):
        assert git(copy, "checkout", "-qb", name, "main").returncode == 0
        move(copy, name)
        assert git(copy, "add", "-A").returncode == 0
        assert git(copy, "commit", "-qm", f"move {name}").returncode == 0
    changed = git(copy, "diff", "--name-only", "main", "foo").stdout.split()
    assert {"README.md", "CATALOG.md", "pyproject.toml", "skills.json"} <= set(changed)
    merged = git(copy, "merge-tree", "--write-tree", "--name-only", "foo", "qux")
    assert (merged.returncode, merged.stdout.splitlines()[1:]) == (0, [])
    tree = merged.stdout.split()[0]
    assert git(copy, "read-tree", "--reset", "-u", tree).returncode == 0
    assert generate(copy, "--check").returncode == 0


def test_a_page_added_to_the_jbus_folder_without_the_index_is_stale(copy):
    (copy / "docs" / "jbus" / "a-new-page.md").write_text("# A new page\n\nIts words.\n")
    ran = generate(copy, "--check")
    assert ran.stderr.splitlines()[0] == "stale: features/jbus/docs/jbus.md"
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
                        "owns": [],
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


def owns(root, name, *rows):
    """Give the feature `name` a manifest whose `owns` is `rows`."""
    manifest = {"$schema": "../../schemas/feature.schema.json", "name": name}
    manifest |= {"description": "x", "owns": list(rows)}
    (root / "features" / name / "feature.json").write_text(json.dumps(manifest))


def test_every_file_of_the_checkout_has_exactly_one_owner():
    unowned, twice = borders(crawl(REPO), tracked(REPO))
    assert (unowned, twice) == ([], {})


def test_an_owner_is_the_feature_folder_or_one_row_and_two_rows_are_both_seen(copy):
    tree = crawl(copy)
    assert tree.owners("features/jbus/feature.json") == ("jbus",)
    assert tree.owners("features/jbus/src/jbus/cli.py") == ("jbus",)
    assert tree.owners("features/jbriefs/src/jbriefs/cli.py") == ("jbriefs",)
    assert tree.owners("pyproject.toml") == ("INFRA",)
    assert tree.owners("nowhere/at/all.txt") == ()
    owns(copy, "bro", "features/jbus/src/jbus/cli.py")
    assert crawl(copy).owners("features/jbus/src/jbus/cli.py") == ("bro", "jbus")


def test_the_crawl_raises_every_fault_at_once(copy):
    for name in ("bro", "tdd"):
        (copy / "features" / name / "feature.json").write_text("{}")
    with pytest.raises(Invalid) as raised:
        crawl(copy)
    assert {fault.split(":")[0] for fault in raised.value.faults} >= {
        "features/bro/feature.json",
        "features/tdd/feature.json",
    }


def test_a_feature_row_that_claims_another_features_folder_is_a_second_owner(copy):
    owns(copy, "bro", "features/jbus/**")
    assert crawl(copy).owners("features/jbus/feature.json") == ("bro", "jbus")


def test_an_owns_row_with_a_double_star_inside_it_is_refused(copy):
    owns(copy, "bro", "skills/**/SKILL.md")
    ran = generate(copy, "--check")
    assert ran.returncode == 2
    assert "features/bro/feature.json: owns skills/**/SKILL.md: ** is only" in ran.stderr


def test_a_principle_skill_does_not_make_the_skills_after_it_principles(copy):
    for name in ("principle-alpha", "zeta"):
        skill = copy / "features" / "bro" / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {name}\ndescription: Do {name}.\n---\n\n# {name}\n")
    kinds = {(one.kind, one.name) for one in crawl(copy).items}
    assert {("principle", "principle-alpha"), ("skill", "zeta")} <= kinds


def test_the_wheel_carries_the_source_as_shared_data_and_jinstall_as_a_command():
    project = tomllib.loads((REPO / "pyproject.toml").read_text())
    wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    shared = wheel["shared-data"]
    assert {path: f"{skills.PACKAGED}/{path}" for path in shared} == shared
    paths = [one["path"] for one in layout.catalog(REPO)] + [
        one["path"] for one in layout.hooks(REPO)
    ]
    assert {path.split("/", 1)[0] for path in paths} <= set(shared)
    assert {"skills.json", "plugin.json", "docs"} <= set(shared)
    assert "features/jinstall/src/jinstall" in wheel["packages"]
    assert project["project"]["scripts"]["jinstall"] == "jinstall.cli:main"


def test_every_path_the_readmes_table_of_the_repo_names_is_in_the_repo():
    """The rows below "| Path | Holds |" are written by hand, so no run of the generator moves
    them: each path in the Path column is in the checkout, and each name a row gives in backticks
    is too, from the root or from the row's own folder. A name with `~`, `<`, `{` or a space is a
    pattern, and one with no `/` and no `.` is a command."""
    lines = (REPO / "README.md").read_text().splitlines()
    rows = []
    for line in lines[lines.index("| Path | Holds |") + 2 :]:
        if not line.startswith("|"):
            break
        path, holds = (cell.strip() for cell in line.strip("|").split("|", 1))
        rows.append((path.strip("`"), re.findall(r"`([^`]+)`", holds)))
    assert rows
    for path, named in rows:
        assert (REPO / path).exists(), path
        folder = REPO / path if path.endswith("/") else REPO
        for name in named:
            if re.search(r"[~<{\s]", name) or not re.search(r"[./]", name):
                continue
            assert (REPO / name).exists() or (folder / name).exists(), f"{path}: {name}"
