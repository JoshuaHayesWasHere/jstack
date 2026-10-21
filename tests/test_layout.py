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
from test_install import User, laid, line_for
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


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def copied(tmp_path):
    """This checkout's files, tracked and not yet added, at a folder of the test's own."""
    checkout = tmp_path / "checkout"
    listed = subprocess.run(
        ["git", "-C", REPO, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    for name in filter(None, listed.stdout.decode().split("\0")):
        if (REPO / name).exists():
            (checkout / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, checkout / name, follow_symlinks=False)
    return checkout


def test_a_new_skill_is_in_every_layout_on_the_next_install_and_an_edit_is_live(user, tmp_path):
    checkout = copied(tmp_path)
    skill = checkout / "features" / "brand-new" / "SKILL.md"
    skill.parent.mkdir()
    bro = (checkout / "features" / "bro" / "SKILL.md").read_text()
    skill.write_text(bro.replace("name: bro", "name: brand-new", 1))

    def said(*args):
        done = user.start(*args, checkout=checkout)
        out, err = done.communicate()
        return done.returncode, out.splitlines(), err

    code, lines, err = said()
    assert code == 1
    assert lines[0].startswith("old hard generated files are current -> stale: ")
    generate = checkout / "scripts" / "generate-jstack-trees.py"
    assert f"run python3 {generate} and commit the result" in err
    assert not (user.home / ".claude" / "skills" / "brand-new").exists()
    subprocess.run([sys.executable, "-I", generate], check=True, capture_output=True)
    code, lines, _ = said()
    assert [line for line in lines if not line.startswith("ok ") and "commands" not in line] == []
    for harness in HARNESSES:
        link = user.home / harness.root / "brand-new"
        assert os.readlink(link) == str(laid(user.home, harness.name) / "skills" / "brand-new")
        assert os.path.realpath(link / "SKILL.md") == str(skill)
    skill.write_text(skill.read_text() + "\nOne more line.\n")
    read = (user.home / ".claude" / "skills" / "brand-new" / "SKILL.md").read_text()
    assert read.endswith("\nOne more line.\n")
    code, lines, _ = said("--check")
    assert [line for line in lines if not line.startswith("ok ") and "commands" not in line] == []


@pytest.mark.parametrize("broken", ["conflicted", "missing", "wrong shape"])
@pytest.mark.parametrize("args", [("--check",), ()], ids=["check", "install"])
def test_a_source_whose_catalog_cannot_be_read_is_named_on_its_lines_and_ends_in_no_traceback(
    user, tmp_path, broken, args
):
    checkout = copied(tmp_path)
    catalog = checkout / "skills.json"
    if broken == "missing":
        catalog.unlink()
    elif broken == "wrong shape":
        catalog.write_text("[1]\n")
    else:
        catalog.write_text("<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> theirs\n")
    done = user.start(*args, checkout=checkout)
    out, err = done.communicate()
    lines = out.splitlines()
    assert done.returncode == 1
    assert "Traceback" not in err
    generated = line_for(lines, "generated files are current")
    assert len(generated) == 1 and generated[0].startswith("old hard ")
    for harness in HARNESSES:
        part = f"layout {harness.name} {laid(user.home, harness.name)}"
        [said] = line_for(lines, part)
        assert said.startswith(f"old hard {part} -> the source cannot be read: ")


def test_check_names_what_is_stale_in_a_layout_and_a_run_mends_it(user):
    user.run()
    gone = user.layout / "skills" / "crew" / "SKILL.md"
    gone.unlink()
    (user.layout / "skills" / "crew" / "extra.md").write_text("not the install's\n")
    part = f"layout claude-code {user.layout}"
    code, said = user.run("--check")
    stale = "stale: skills/crew/SKILL.md, and 1 more"
    assert (code, line_for(said, part)) == (1, [f"old hard {part} -> {stale}"])
    assert user.run() == (0, user.every("ok"))
    assert os.readlink(gone) == str(REPO / "skills" / "crew" / "SKILL.md")
    assert not (user.layout / "skills" / "crew" / "extra.md").exists()


def test_each_layout_keeps_templates_and_playbooks_beside_its_skills(user):
    user.run()
    for harness in HARNESSES:
        skill = user.home / harness.root / "crew"
        root = os.path.realpath(skill / ".." / "..")
        assert root == str(laid(user.home, harness.name))
        assert os.path.realpath(f"{root}/templates/result.md") == str(
            REPO / "templates" / "result.md"
        )
        assert os.path.isfile(f"{root}/playbooks/feature.md")
        assert os.path.realpath(f"{root}/source") == str(REPO)


def test_uninstall_takes_every_layout_away(user):
    user.run()
    code, said = user.run("--uninstall")
    assert code == 0
    for harness in HARNESSES:
        assert f"removed layout {laid(user.home, harness.name)}" in said
        assert not laid(user.home, harness.name).exists()


def test_an_install_over_one_from_before_the_layouts_repoints_its_links_and_hooks(user):
    copy = REPO / "harness" / "jstack" / "claude-code"
    old = {
        user.home / ".claude" / "skills" / "crew": copy / "skills" / "crew",
        user.home / ".claude" / "skills" / "retired": copy / "skills" / "retired",
        user.home / ".codex" / "skills" / "gone": laid(user.home, "codex") / "skills" / "gone",
    }
    for link, target in old.items():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    hook = f"sh '{copy / 'hooks' / 'home-start.sh'}' 2>/dev/null || true"
    started = {"matcher": "startup", "hooks": [{"type": "command", "command": hook, "timeout": 5}]}
    user.write(user.settings, {"hooks": {"SessionStart": [started]}})
    code, said = user.run("--check")
    assert code == 1
    crew, retired, gone = old
    assert line_for(said, crew) == [f"old hard {crew} -> {copy / 'skills' / 'crew'}"]
    gone_from = f"{copy / 'skills' / 'retired'}, a skill this checkout no longer has"
    assert line_for(said, retired) == [f"old hard {retired} -> {gone_from}"]
    assert line_for(said, gone)[0].startswith(f"old hard {gone} -> ")
    assert line_for(said, f"hook {user.settings} SessionStart") == [
        f"old hard hook {user.settings} SessionStart -> {hook}"
    ]
    code, said = user.run()
    assert (code, [line for line in said if not line.startswith("ok ")]) == (0, [])
    for dead in (retired, gone):
        assert line_for(said, dead) == [f"ok hard {dead} -> unlinked"]
    assert user.run("--check") == (0, user.every("ok"))
    assert os.readlink(crew) == str(user.layout / "skills" / "crew")
    assert not retired.is_symlink() and not gone.is_symlink()
    assert json.loads(user.settings.read_text())["hooks"]["SessionStart"] == [user.START]


def test_check_names_a_skill_link_whose_target_a_move_took_away_and_a_run_mends_it(user, tmp_path):
    checkout = copied(tmp_path)

    def said(*args):
        done = user.start(*args, checkout=checkout)
        out, _ = done.communicate()
        return done.returncode, [line for line in out.splitlines() if "commands" not in line]

    said()
    skill = user.home / ".claude" / "skills" / "why" / "SKILL.md"
    assert skill.is_file()
    moved = checkout / "features" / "why" / "skills" / "why"
    moved.mkdir(parents=True)
    for name in ("SKILL.md", "references"):
        shutil.move(checkout / "features" / "why" / name, moved / name)
    generate(checkout)
    assert not skill.exists()
    part = f"layout claude-code {laid(user.home)}"
    code, lines = said("--check")
    assert code == 1
    [line] = line_for(lines, part)
    assert line.startswith(f"old hard {part} -> stale: features/why/")
    _, lines = said()
    assert [line for line in lines if not line.startswith("ok ")] == []
    assert os.path.realpath(skill) == str(moved / "SKILL.md")
