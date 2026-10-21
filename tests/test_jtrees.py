"""`scripts/generate-jstack-trees.py [--check]`: what the generator writes from features/, and
that a stale output fails the check by name. Each test runs the script, or `jtrees`, over a
copy of this checkout."""

import filecmp
import importlib
import json
import os
import shutil
import subprocess
import sys
import tomllib

import pytest

from testing.paths import REPO

SCRIPT = "scripts/generate-jstack-trees.py"
COPY = "harness/jstack/claude-code"
sys.path.insert(0, str(REPO / "scripts"))

jtrees = importlib.import_module("jtrees.crawl")
terms = importlib.import_module("jtrees.terms")
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
        f"stale: {COPY}/README.md",
        f"stale: {COPY}/skills.json",
        f"stale: {COPY}/skills/bro/SKILL.md",
        "stale: skills.json",
        f"run python3 {SCRIPT} and commit the result",
    ]
    assert (copy / "skills.json").read_bytes() == before


def test_a_hand_edit_inside_a_generated_region_makes_the_check_fail_naming_that_file(copy):
    page = copy / "docs" / "playbooks.md"
    page.write_text(page.read_text().replace("| `bro` |", "| `bro-edited` |", 1))
    ran = generate(copy, "--check")
    assert ran.returncode == 1
    assert ran.stderr.splitlines() == [
        "stale: docs/playbooks.md",
        f"run python3 {SCRIPT} and commit the result",
    ]


def test_a_run_writes_what_is_stale_and_a_second_run_writes_nothing(copy):
    skill = copy / "features" / "bro" / "SKILL.md"
    skill.write_text(skill.read_text().replace("description: ", "description: Now ", 1))
    assert generate(copy).stdout == (
        f"wrote {COPY}/README.md\nwrote {COPY}/skills.json\n"
        f"wrote {COPY}/skills/bro/SKILL.md\nwrote skills.json\n"
    )
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
        f"stale: {COPY}/README.md",
        f"stale: {COPY}/hooks/foo-start.sh",
        f"stale: {COPY}/playbooks/foo-run.md",
        f"stale: {COPY}/skills.json",
        f"stale: {COPY}/skills/foo/SKILL.md",
        f"stale: {COPY}/templates/foo.md",
        "stale: harness/jstack/pythonpath",
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
    copied = {
        (one["kind"], one["name"]): one["path"]
        for one in json.loads((copy / COPY / "skills.json").read_text())["items"]
    }
    assert copied["skill", "foo"] == "skills/foo/SKILL.md"
    assert copied["playbook", "foo-run"] == "playbooks/foo-run.md"
    assert copied["template", "foo.md"] == "templates/foo.md"
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
    assert sorted(p.name for p in (copy / COPY / "skills" / "foo").iterdir()) == ["SKILL.md"]
    assert (copy / "harness/jstack/pythonpath").read_text() == "features/foo/src\nsrc\n"
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
    assert tree.owners("src/jbus/cli.py") == ("jbus",)
    assert tree.owners("src/jbriefs/cli.py") == ("jbriefs",)
    assert tree.owners("pyproject.toml") == ("INFRA",)
    assert tree.owners("nowhere/at/all.txt") == ()
    owns(copy, "bro", "src/jbus/cli.py")
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


def test_the_copy_holds_each_skill_playbook_principle_template_unit_and_hook(copy):
    shutil.rmtree(copy / COPY)
    assert generate(copy).returncode == 0
    copied = copy / COPY
    skills = sorted(one.name for one in crawl(copy).items if one.kind == "skill")
    assert sorted(path.name for path in (copied / "skills").iterdir()) == skills
    for folder in ("playbooks", "principles"):
        assert sorted(p.name for p in (copied / folder).iterdir()) == sorted(
            p.name for p in (copy / folder).glob("*.md")
        )
    templates = sorted(
        p.relative_to(copy / "templates").as_posix()
        for p in (copy / "templates").rglob("*")
        if p.is_file()
    )
    assert "jbus.timer" in templates
    assert (
        sorted(
            p.relative_to(copied / "templates").as_posix()
            for p in (copied / "templates").rglob("*")
            if p.is_file()
        )
        == templates
    )
    for unit in (copy / "templates").glob("*.service"):
        assert filecmp.cmp(copied / "templates" / unit.name, unit, shallow=False)
    for hook in (copy / "hooks").iterdir():
        assert filecmp.cmp(copied / "hooks" / hook.name, hook, shallow=False)
        assert os.access(copied / "hooks" / hook.name, os.X_OK) == os.access(hook, os.X_OK)
    for plugin in ("plugin.json", ".claude-plugin/plugin.json"):
        assert filecmp.cmp(copied / plugin, copy / "plugin.json", shallow=False)
    assert (copied / "README.md").is_file()
    assert (copy / "harness/jstack/pythonpath").read_text() == "src\n"
    root = json.loads((copy / "skills.json").read_text())["items"]
    listed = json.loads((copied / "skills.json").read_text())["items"]
    assert [(one["kind"], one["name"]) for one in listed] == [
        (one["kind"], one["name"]) for one in root
    ]
    for one in listed:
        assert (copied / one["path"]).is_file(), one
    pairs = {(one["kind"], one["name"]): one["path"] for one in listed}
    assert pairs["skill", "crew"] == "skills/crew/SKILL.md"
    assert pairs["playbook", "feature"] == "playbooks/feature.md"
    assert pairs["template", "jbus.timer"] == "templates/jbus.timer"
    assert generate(REPO, "--check").returncode == 0


def test_the_wheel_takes_the_copy_whole_as_shared_data_and_jinstall_as_a_command():
    project = tomllib.loads((REPO / "pyproject.toml").read_text())
    wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["shared-data"] == {COPY: "share/jstack/claude-code"}
    assert "src/jinstall" in wheel["packages"]
    assert project["project"]["scripts"]["jinstall"] == "jinstall.cli:main"


def test_a_link_to_a_file_the_copy_leaves_out_points_at_github(copy):
    skill = copy / "features" / "bro" / "SKILL.md"
    skill.write_text(
        skill.read_text()
        + "\nSee [the state](../../docs/state.md#homes), [jbus](../../src/jbus/) and"
        " [ketchup](../ketchup/SKILL.md), but not `[code](../../nowhere.md)`.\n"
    )
    assert generate(copy).returncode == 0
    text = (copy / COPY / "skills" / "bro" / "SKILL.md").read_text()
    github = "https://github.com/JoshuaHayesWasHere/jstack"
    assert f"[the state]({github}/blob/main/docs/state.md#homes)" in text
    assert f"[jbus]({github}/tree/main/src/jbus)" in text
    assert "[ketchup](../ketchup/SKILL.md)" in text
    assert "`[code](../../nowhere.md)`" in text


def test_a_link_that_still_dangles_fails_naming_the_file_and_writes_nothing(copy):
    playbook = copy / "playbooks" / "bug-fix.md"
    playbook.write_text(playbook.read_text() + "\nSee [gone](../docs/gone.md).\n")
    before = (copy / COPY / "playbooks" / "bug-fix.md").read_bytes()
    ran = generate(copy)
    assert ran.returncode == 2
    assert ran.stderr.splitlines() == [
        f"FAIL {COPY}/playbooks/bug-fix.md links to ../docs/gone.md, which is not in the tree"
    ]
    assert (copy / COPY / "playbooks" / "bug-fix.md").read_bytes() == before


def test_a_file_in_the_copy_that_no_item_makes_is_stale_and_removed(copy):
    stray = copy / COPY / "skills" / "retired" / "SKILL.md"
    stray.parent.mkdir()
    stray.write_text("---\nname: retired\n---\n")
    ran = generate(copy, "--check")
    assert ran.stderr.splitlines()[0] == f"stale: {COPY}/skills/retired/SKILL.md"
    assert generate(copy).stdout == f"removed {COPY}/skills/retired/SKILL.md\n"
    assert not stray.parent.exists()
    assert generate(copy, "--check").returncode == 0


def test_a_hook_that_loses_its_executable_bit_is_stale(copy):
    (copy / COPY / "hooks" / "pre-push.sh").chmod(0o644)
    ran = generate(copy, "--check")
    assert ran.stderr.splitlines()[0] == f"stale: {COPY}/hooks/pre-push.sh"
    generate(copy)
    assert os.access(copy / COPY / "hooks" / "pre-push.sh", os.X_OK)


def test_a_principle_skill_is_copied_as_a_skill_with_a_stub_where_principles_are_read(copy):
    skill = copy / "features" / "principles" / "skills" / "principle-alpha" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: principle-alpha\ndescription: Do alpha.\n---\n\n# Alpha\n")
    assert generate(copy).returncode == 0
    copied = copy / COPY / "skills" / "principle-alpha" / "SKILL.md"
    assert copied.read_bytes() == skill.read_bytes()
    stub = (copy / COPY / "principles" / "principle-alpha.md").read_text()
    assert "[principle-alpha](../skills/principle-alpha/SKILL.md)" in stub


TEXT = (
    "Call `t3_thread_send`, or `delegate_task` with `run_in_background`; wait with Monitor; ask "
    "with AskUserQuestion after ToolSearch; edit ~/.claude/settings.json."
)


def test_a_copy_for_another_harness_flags_each_claude_code_term_the_text_uses():
    assert terms.used(TEXT, "codex") == set(terms.TERMS["claude-code"])
    assert terms.used("Read the brief and open a pull request.", "codex") == set()


def test_the_claude_code_copy_flags_nothing_in_any_file_it_holds():
    assert terms.used(TEXT, "claude-code") == set()
    flagged = {
        path.relative_to(REPO / COPY).as_posix(): found
        for path in (REPO / COPY).rglob("*.md")
        if (found := terms.used(path.read_text(), "claude-code"))
    }
    assert flagged == {}


def test_the_adapter_line_points_from_a_skill_at_its_harness_page():
    line = terms.adapter_line("codex")
    assert line.startswith("In codex, read [the adapter](../../docs/harness/codex.md) ")
