"""`jinstall.layout`: each harness's layout, as the install assembles it from a source tree.
Each test assembles from this checkout, or from a copy of its files that the test changes, and
places the layout where it reads it as an agent does."""

import importlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from jinstall import layout, terms
from jinstall.harnesses import CLAUDE_CODE, HARNESSES
from testing.layouts import place
from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))
tracked = importlib.import_module("jtrees.crawl").tracked
GITHUB = "https://github.com/JoshuaHayesWasHere/jstack"
CODEX = next(harness for harness in HARNESSES if harness.name == "codex")


@pytest.fixture
def copy(tmp_path):
    """This checkout's files, tracked and not yet added, with no git and no .venv."""
    root = tmp_path / "jstack"
    for path in tracked(REPO):
        if (REPO / path).exists():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / path, target, follow_symlinks=False)
    return root


def generate(root):
    script = root / "scripts" / "generate-jstack-trees.py"
    subprocess.run([sys.executable, "-I", script], cwd=root, check=True, capture_output=True)


def kinds(source):
    found = {}
    for item in layout.catalog(source):
        found.setdefault(item["kind"], set()).add(item["name"])
    return found


@pytest.mark.parametrize("harness", HARNESSES, ids=lambda harness: harness.name)
def test_a_layout_holds_each_skill_playbook_principle_template_and_its_own_hooks(harness):
    assembled = layout.assemble(REPO, harness)
    entries = assembled.entries
    assert assembled.faults == ()
    folders = {}
    for path in entries:
        top, _, rest = path.partition("/")
        folders.setdefault(top, set()).add(rest)
    assert {rest.split("/")[0] for rest in folders["skills"]} == set(layout.skills(REPO))
    assert folders["playbooks"] == {f"{name}.md" for name in kinds(REPO)["playbook"]}
    assert folders["principles"] == {f"{name}.md" for name in kinds(REPO)["principle"]}
    assert folders["templates"] == kinds(REPO)["template"]
    hooks = {one["name"] for one in layout.hooks(REPO) if harness.name in one["harnesses"]}
    assert folders.get("hooks", set()) == hooks
    assert {"README.md", "source"} <= set(entries)
    assert entries["source"] == layout.Linked(REPO)
    for path, entry in entries.items():
        if isinstance(entry, layout.Linked):
            assert entry.source.exists(), path


def test_only_claude_code_and_codex_run_the_session_start_hook_and_only_claude_code_the_rest():
    held = {
        harness.name: sorted(
            path for path in layout.assemble(REPO, harness).entries if path.startswith("hooks/")
        )
        for harness in HARNESSES
    }
    assert held["codex"] == ["hooks/home-start.sh"]
    assert held["cursor"] == []
    assert "hooks/limits.sh" in held["claude-code"]
    assert "hooks/pre-push.sh" not in held["claude-code"]


def test_each_skill_file_links_to_its_file_and_an_edit_there_is_live(copy, tmp_path):
    at = place(tmp_path / "claude-code", root=copy)
    skill = at / "skills" / "tdd" / "SKILL.md"
    assert os.readlink(skill) == str(copy / "features" / "tdd" / "SKILL.md")
    (copy / "features" / "tdd" / "SKILL.md").write_text("edited\n")
    assert skill.read_text() == "edited\n"
    assert layout.stale(layout.assemble(copy, CLAUDE_CODE), at) == []


def test_a_written_file_is_stale_once_its_source_changes_and_a_stray_is_named(copy, tmp_path):
    at = place(tmp_path / "claude-code", root=copy)
    entries = layout.assemble(copy, CLAUDE_CODE).entries
    written = sorted(
        path
        for path, entry in entries.items()
        if isinstance(entry, layout.Written) and path.startswith("skills/")
    )
    assert written, "a skill that links into docs/ is written, rewritten"
    source = copy / "skills" / written[0].removeprefix("skills/")
    source.write_text(source.read_text() + "\nOne more line.\n")
    (at / "skills" / "crew" / "stray.md").write_text("not the install's\n")
    found = layout.stale(layout.assemble(copy, CLAUDE_CODE), at)
    assert found == sorted([written[0], "skills/crew/stray.md"])


def test_a_link_to_a_file_the_layout_leaves_out_points_at_github(copy):
    skill = copy / "features" / "bro" / "SKILL.md"
    skill.write_text(
        skill.read_text()
        + "\nSee [the state](../../docs/state.md#homes), [jbus](../../src/jbus/) and"
        " [ketchup](../ketchup/SKILL.md), but not `[code](../../nowhere.md)`.\n"
    )
    entry = layout.assemble(copy, CLAUDE_CODE).entries["skills/bro/SKILL.md"]
    assert isinstance(entry, layout.Written)
    text = entry.content.decode()
    assert f"[the state]({GITHUB}/blob/main/docs/state.md#homes)" in text
    assert f"[jbus]({GITHUB}/tree/main/src/jbus)" in text
    assert "[ketchup](../ketchup/SKILL.md)" in text
    assert "`[code](../../nowhere.md)`" in text


def test_a_link_that_dangles_is_a_fault_naming_the_file_and_a_link_in_code_is_none(copy):
    playbook = copy / "playbooks" / "bug-fix.md"
    playbook.write_text(
        playbook.read_text()
        + "\nSee [`state`](../docs/state.md), [`gone`](../docs/gone.md) and `[code](../x.md)`.\n"
    )
    assert layout.assemble(copy, CLAUDE_CODE).faults == (
        "playbooks/bug-fix.md links to ../docs/gone.md, which is not in the tree",
    )
    playbook.write_text(playbook.read_text().replace(", [`gone`](../docs/gone.md)", ""))
    assembled = layout.assemble(copy, CLAUDE_CODE)
    assert assembled.faults == ()
    text = assembled.entries["playbooks/bug-fix.md"].content.decode()
    assert f"See [`state`]({GITHUB}/blob/main/docs/state.md) and `[code](../x.md)`." in text


def test_a_principle_skill_is_a_skill_with_a_stub_where_principles_are_read(copy):
    skill = copy / "features" / "principles" / "skills" / "principle-alpha" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: principle-alpha\ndescription: Do alpha.\n---\n\n# Alpha\n")
    generate(copy)
    entries = layout.assemble(copy, CLAUDE_CODE).entries
    assert entries["skills/principle-alpha/SKILL.md"] == layout.Linked(skill)
    stub = entries["principles/principle-alpha.md"].content.decode()
    assert "[principle-alpha](../skills/principle-alpha/SKILL.md)" in stub


TEXT = (
    "Call `t3_thread_send`, or `delegate_task` with `run_in_background`; wait with Monitor; ask "
    "with AskUserQuestion after ToolSearch; edit ~/.claude/settings.json."
)


def test_codex_and_cursor_leave_out_each_claude_code_term_and_claude_code_leaves_out_none():
    for harness in ("codex", "cursor"):
        assert terms.used(TEXT, harness) == set(terms.CLAUDE_CODE_ONLY)
        assert terms.used("Read the brief and open a pull request.", harness) == set()
    assert terms.used(TEXT, "claude-code") == set()


def test_the_readme_of_a_layout_names_what_each_skill_asks_for_that_its_harness_leaves_out():
    assert layout.assemble(REPO, CLAUDE_CODE).flagged == {}
    assembled = layout.assemble(REPO, CODEX)
    assert assembled.flagged
    readme = assembled.entries["README.md"].content.decode()
    for name, found in assembled.flagged.items():
        assert set(found) <= set(terms.LEAVES_OUT["codex"])
        assert f"| [{name}](skills/{name}/SKILL.md) | " in readme
        assert (
            readme.split(f"| [{name}](skills/{name}/SKILL.md) | ", 1)[1]
            .split("\n")[0]
            .endswith(f" | {', '.join(found)} |")
        )


def test_the_catalog_lists_each_hook_with_the_harnesses_that_run_it():
    listed = {one["name"]: one for one in json.loads((REPO / "skills.json").read_text())["hooks"]}
    assert listed["home-start.sh"]["harnesses"] == ["claude-code", "codex"]
    assert listed["limits.sh"]["harnesses"] == ["claude-code"]
    assert "pre-push.sh" not in listed
    for one in listed.values():
        assert (REPO / one["path"]).is_file()
