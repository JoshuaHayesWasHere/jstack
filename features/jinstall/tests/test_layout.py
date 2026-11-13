"""`jinstall.layout`: each harness's layout, as the install assembles it from a source tree.
Each test assembles a layout from this checkout, or from a copy of its files that the test
changes. The test then places the layout where an agent reads it, and reads it as the agent
does."""

import importlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from jinstall import layout
from jinstall.harnesses import CLAUDE_CODE, HARNESSES, HIDES
from test_install import User, laid, line_for
from testing.layouts import place
from testing.paths import REPO, skills

sys.path.insert(0, str(REPO / "scripts"))
tracked = importlib.import_module("jtrees.crawl").tracked
GITHUB = "https://github.com/JoshuaHayesWasHere/jstack"
OPENAI = "agents/openai.yaml"
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


def test_a_written_file_is_stale_once_its_source_changes_and_a_stray_is_named(copy, tmp_path):
    at = place(tmp_path / "claude-code", root=copy)
    entries = layout.assemble(copy, CLAUDE_CODE).entries
    written = sorted(
        path
        for path, entry in entries.items()
        if isinstance(entry, layout.Written) and path.startswith("skills/")
    )
    assert written, "a skill that links into docs/ is written, rewritten"
    name, _, file = written[0].removeprefix("skills/").partition("/")
    source = skills(copy)[name] / file
    source.write_text(source.read_text() + "\nOne more line.\n")
    (at / "skills" / "crew" / "stray.md").write_text("not the install's\n")
    found = layout.stale(layout.assemble(copy, CLAUDE_CODE), at)
    assert found == sorted([written[0], "skills/crew/stray.md"])


def test_a_link_to_a_file_the_layout_leaves_out_points_at_github(copy):
    skill = copy / "features" / "bro" / "SKILL.md"
    skill.write_text(
        skill.read_text()
        + "\nSee [the state](../home/docs/state.md#homes), [jbus](../jbus/src/jbus/) and"
        " [ketchup](../ketchup/SKILL.md), but not `[code](../../nowhere.md)`.\n"
    )
    entry = layout.assemble(copy, CLAUDE_CODE).entries["skills/bro/SKILL.md"]
    assert isinstance(entry, layout.Written)
    text = entry.content.decode()
    assert f"[the state]({GITHUB}/blob/main/features/home/docs/state.md#homes)" in text
    assert f"[jbus]({GITHUB}/tree/main/features/jbus/src/jbus)" in text
    assert "[ketchup](../ketchup/SKILL.md)" in text
    assert "`[code](../../nowhere.md)`" in text


def test_a_principle_skill_is_a_skill_with_a_stub_where_principles_are_read(copy):
    skill = copy / "features" / "principles" / "skills" / "principle-alpha" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: principle-alpha\ndescription: Do alpha.\n---\n\n# Alpha\n")
    generate(copy)
    entries = layout.assemble(copy, CLAUDE_CODE).entries
    assert entries["skills/principle-alpha/SKILL.md"] == layout.Linked(skill)
    stub = entries["principles/principle-alpha.md"].content.decode()
    assert "[principle-alpha](../skills/principle-alpha/SKILL.md)" in stub


def test_a_features_spec_folder_is_the_repos_model_and_no_file_of_it_is_in_the_skill(copy):
    spec = copy / "features" / "crew" / "spec"
    spec.mkdir(exist_ok=True)
    (spec / "README.md").write_text("# CrewProof\n\nThe model of a crew's proof.\n")
    (spec / "CrewProof.tla").write_text("---- MODULE CrewProof ----\n====\n")
    (spec / "chart.png").write_bytes(b"\x89PNG\r\n")
    for harness in HARNESSES:
        entries = layout.assemble(copy, harness).entries
        assert "skills/crew/SKILL.md" in entries
        assert [path for path in entries if path.startswith("skills/crew/spec")] == []


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
        if harness.copies:
            assert (link / "SKILL.md").read_bytes() == skill.read_bytes()
        else:
            assert os.path.realpath(link / "SKILL.md") == str(skill)
    skill.write_text(skill.read_text() + "\nOne more line.\n")
    read = (user.home / ".claude" / "skills" / "brand-new" / "SKILL.md").read_text()
    assert read.endswith("\nOne more line.\n")
    code, lines, _ = said("--check")
    codex = f"old hard layout codex {laid(user.home, 'codex')} -> stale: skills/brand-new/SKILL.md"
    assert [line for line in lines if not line.startswith("ok ") and "commands" not in line] == [
        codex
    ]


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
    assert os.readlink(gone) == str(REPO / "features" / "crew" / "SKILL.md")
    assert not (user.layout / "skills" / "crew" / "extra.md").exists()


def test_codex_finds_beside_each_hidden_skill_a_policy_that_bars_implicit_invocation(user):
    """Codex ignores `disable-model-invocation` and reads `agents/openai.yaml` beside the skill,
    in its own root and in `~/.agents/skills`. The hidden skills are the ones skills.json marks."""
    user.run()
    items = json.loads((REPO / "skills.json").read_text())["items"]
    hidden = {item["name"] for item in items if item.get("hidden")}
    exposed = set(layout.skills(REPO)) - hidden
    assert "home" in hidden and "grilling" in exposed
    policy = "policy:\n  allow_implicit_invocation: false\n"
    own = {name for name, folder in skills().items() if (folder / OPENAI).exists()}
    for root in (".codex/skills", ".agents/skills"):
        for name in hidden - own:
            assert (user.home / root / name / OPENAI).read_text() == policy
        assert {name for name in exposed if (user.home / root / name / "agents").exists()} == own
    claude = user.home / ".claude" / "skills"
    assert [name for name in hidden if (claude / name / "agents").exists()] == []


def interface(text):
    """The `interface` keys of an `agents/openai.yaml`, as Codex reads its three strings."""
    found, inside = {}, False
    for line in text.splitlines():
        if not line.startswith(" "):
            inside = line == "interface:"
        elif inside:
            key, _, value = line.strip().partition(": ")
            found[key] = json.loads(value)
    return found


def test_codex_shows_a_skill_by_the_name_description_and_prompt_its_own_file_gives(user):
    """A skill that keeps `agents/openai.yaml`, as tstack's do, gives Codex a display name, a
    short description and a default prompt. The install puts the file where Codex reads it."""
    user.run()
    own = {name: folder / OPENAI for name, folder in skills().items() if (folder / OPENAI).exists()}
    assert "engine" in own
    for name, path in own.items():
        said = interface(path.read_text())
        assert set(said) == {"display_name", "short_description", "default_prompt"}, name
        assert all(said.values()) and f"${name}" in said["default_prompt"], name
        for root in (".codex/skills", ".agents/skills"):
            assert interface((user.home / root / name / OPENAI).read_text()) == said


def test_a_hidden_skill_keeps_its_own_interface_beside_the_policy(copy):
    """A hidden skill with its own `agents/openai.yaml` gets that file with the policy after it,
    so Codex shows it by its name and still never loads it by itself."""
    mine = 'interface:\n  display_name: "Home"\n'
    (skills(copy)["home"] / "agents").mkdir()
    (skills(copy)["home"] / OPENAI).write_text(mine)
    generate(copy)
    entry = layout.assemble(copy, CODEX).entries[f"skills/home/{OPENAI}"]
    assert entry == layout.Written((mine + HIDES[1]).encode())


def test_codex_finds_each_skill_md_as_a_file_and_not_a_link(user):
    """codex-cli 0.165.0 lists no skill whose SKILL.md is a symlink, so the Codex layout copies
    each one, with the bytes of its source. Claude Code's layout still links it."""
    user.run()
    for name in layout.skills(REPO):
        codex = user.home / ".codex" / "skills" / name / "SKILL.md"
        assert codex.is_file() and not codex.is_symlink(), name
    grilling = user.home / ".codex" / "skills" / "grilling" / "SKILL.md"
    assert grilling.read_bytes() == (REPO / "features" / "grilling" / "SKILL.md").read_bytes()
    assert (user.home / ".claude" / "skills" / "grilling" / "SKILL.md").is_symlink()


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
    old_hooks = [
        line
        for line in line_for(said, f"hook {user.settings} SessionStart")
        if line.startswith("old ")
    ]
    assert old_hooks == [f"old hard hook {user.settings} SessionStart -> {hook}"]
    code, said = user.run()
    assert (code, [line for line in said if not line.startswith("ok ")]) == (0, [])
    for dead in (retired, gone):
        assert line_for(said, dead) == [f"ok hard {dead} -> unlinked"]
    assert user.run("--check") == (0, user.every("ok"))
    assert os.readlink(crew) == str(user.layout / "skills" / "crew")
    assert not retired.is_symlink() and not gone.is_symlink()
    assert (
        json.loads(user.settings.read_text())["hooks"]["SessionStart"]
        == (user.written()["SessionStart"])
    )
