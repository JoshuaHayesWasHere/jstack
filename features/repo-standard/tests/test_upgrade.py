"""`repo-standard upgrade --to N` moves a repo made from one version of the standard to the next.

The fixture is an upstream that stands in for jstack, with two tags. `repo-standard-v2` is this
tree, with its version set to 2 as the release of v2 sets it. `repo-standard-v1` is the same tree
set to version 1, with the skeleton's Makefile and owners as v1 had them, before `local.mk`. A
repo is made from v1 with the python-uv adapter, as `features/repo-standard/docs/skeleton.md`
says, on a runner of its own. The tool of the v2 clone upgrades it, and one `make lint` passes
conform at v2.

The rule of which files a version owns (`repo_standard.owned.RULES`) places every file of the
skeleton and of each adapter, or the first case fails.
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

from repo_standard import VERSION, owned
from repo_standard.cli import main
from repo_standard.config import Config, Refused, Stack, load
from repo_standard.tree import Unreadable, tracked
from repo_standard.upgrade import run as upgrade_run
from test_skeleton_python import ADAPTER, INHERITED, SKELETON, STANDARD, git, make
from testing.paths import REPO

LOCAL_MAKE = "\n-include local.mk\n"
OWNS_LOCAL_MAKE = "    - Makefile\n    - local.mk\n"
RUNNER = "self-hosted-builder"


def test_every_file_of_the_skeleton_and_each_adapter_has_a_kind():
    folders = [("skeleton", SKELETON)]
    folders += [("adapter", one) for one in sorted((STANDARD / "adapters").iterdir())]
    unplaced = [
        f"{folder.relative_to(REPO)}/{path}"
        for origin, folder in folders
        for path in tracked(folder)
        if owned.kind(origin, path) is None
    ]
    assert unplaced == [], "place each in repo_standard.owned.RULES"


def test_a_repo_owns_the_skeletons_owned_files_and_its_adapters_scripts():
    paths = ["scripts/select.py"]
    found = owned.files(STANDARD, Config(), paths, owned.Kind.OWNED)
    assert sorted(found) == [
        ".github/workflows/borders.yml",
        ".github/workflows/check.yml",
        "Makefile",
        "schemas/feature.core.schema.json",
        "scripts/generate-index.py",
        "scripts/select.py",
        "scripts/stack.mk",
    ]


def at_version(root, version):
    """Set the tree at `root` to the version `version`, as a release sets it."""
    feature = root / "features" / "repo-standard"
    edits = {
        feature / "src/repo_standard/__init__.py": (r"(?m)^VERSION = \d+$", f"VERSION = {version}"),
        feature / "skeleton/.repo-standard.yml": (r"(?m)^standard: \d+$", f"standard: {version}"),
        feature / "adapters/go/.repo-standard.yml": (
            r"(?m)^standard: \d+$",
            f"standard: {version}",
        ),
        feature / "skeleton/.github/workflows/check.yml": (
            r"@repo-standard-v\d+",
            f"@repo-standard-v{version}",
        ),
    }
    for path, (pattern, value) in edits.items():
        text, count = re.subn(pattern, value, path.read_text())
        assert count == 1, path
        path.write_text(text)


@pytest.fixture(scope="module")
def upstream(tmp_path_factory):
    """jstack with the tags of v1 and v2, and a copy of the tree at v1 to make a repo from."""
    root = tmp_path_factory.mktemp("upstream")
    ignore = shutil.ignore_patterns("__pycache__", ".venv", ".cache", ".ruff_cache")
    for part in ("src", "skeleton", "adapters"):
        shutil.copytree(STANDARD / part, root / "features" / "repo-standard" / part, ignore=ignore)
    git(root, "init", "-q", "-b", "main")
    makefile = root / "features/repo-standard/skeleton/Makefile"
    v2_makefile = makefile.read_text()
    assert v2_makefile.endswith(LOCAL_MAKE)
    makefile.write_text(v2_makefile.removesuffix(LOCAL_MAKE))
    configs = [
        root / "features/repo-standard" / one / ".repo-standard.yml"
        for one in ("skeleton", "adapters/go")
    ]
    v2_configs = [one.read_text() for one in configs]
    for one, text in zip(configs, v2_configs, strict=True):
        assert OWNS_LOCAL_MAKE in text
        one.write_text(text.replace(OWNS_LOCAL_MAKE, "    - Makefile\n"))
    at_version(root, 1)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "v1")
    git(root, "tag", "repo-standard-v1")
    v1 = tmp_path_factory.mktemp("v1")
    shutil.copytree(root / "features", v1 / "features")
    makefile.write_text(v2_makefile)
    for one, text in zip(configs, v2_configs, strict=True):
        one.write_text(text)
    at_version(root, 2)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "v2")
    git(root, "tag", "repo-standard-v2")
    tool = tmp_path_factory.mktemp("tool") / "repo-standard-v2"
    git(root, "clone", "-q", "--depth", "1", "--branch", "repo-standard-v2", str(root), str(tool))
    return root, v1 / "features" / "repo-standard", tool


@pytest.fixture
def v1_repo(tmp_path, upstream):
    """A repo made from v1's skeleton and python-uv adapter, on a runner of its own."""
    source, v1, _ = upstream
    root = tmp_path / "repo"
    shutil.copytree(v1 / "skeleton", root)
    shutil.copytree(v1 / "adapters" / ADAPTER.name, root, dirs_exist_ok=True)
    caller = root / ".github/workflows/check.yml"
    text = caller.read_text().replace("runner: ubuntu-24.04", f"runner: {RUNNER}")
    caller.write_text(text.replace("runs-on: ubuntu-24.04", f"runs-on: {RUNNER}"))
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(source)
    make(root, env, "generate")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from repo-standard-v1")
    return root, env


def upgrade(root, env, tool, to):
    env = {**env, "PYTHONPATH": str(tool / "features" / "repo-standard" / "src")}
    command = [sys.executable, "-m", "repo_standard", "upgrade", "--to", str(to)]
    done = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and ".git" not in path.relative_to(root).parts[:1]
        and ".cache" not in path.relative_to(root).parts
    }


def test_a_repo_made_from_v1_passes_conform_at_v2_after_one_upgrade_and_one_lint(v1_repo, upstream):
    root, env = v1_repo
    _, _, tool = upstream
    code, said = upgrade(root, env, tool, 2)
    assert code == 0, said
    lines = said.splitlines()
    for path in (".repo-standard.yml", ".github/workflows/check.yml", "Makefile"):
        assert f"wrote {path}" in lines, said
    assert lines[-1] == "upgrade to repo-standard-v2: 3 files written; run `make lint` next"
    config = (root / ".repo-standard.yml").read_text()
    assert "standard: 2\n" in config
    assert OWNS_LOCAL_MAKE in config, config
    caller = (root / ".github/workflows/check.yml").read_text()
    assert "repo-standard-check.yml@repo-standard-v2" in caller
    assert f"runner: {RUNNER}" in caller and f"runs-on: {RUNNER}" in caller

    (root / "local.mk").write_text("deploy-hello:\n\t@echo a target of the repo\n")
    assert make(root, env, "-s", "deploy-hello") == "a target of the repo\n"
    out = make(root, env, "lint")
    assert "conform repo-standard-v2, " in out
    assert "errors 0, warnings 0" in out, out

    before = snapshot(root)
    code, said = upgrade(root, env, tool, 2)
    assert code == 0, said
    assert said.splitlines()[-1] == (
        "upgrade to repo-standard-v2: nothing to write; run `make lint` next"
    )
    assert not [line for line in said.splitlines() if line.startswith("wrote ")], said
    assert snapshot(root) == before


def test_an_owned_file_the_repo_keeps_local_is_left_and_said(v1_repo, upstream):
    root, env = v1_repo
    _, _, tool = upstream
    config = root / ".repo-standard.yml"
    config.write_text(config.read_text() + "local:\n  Makefile: the deploy targets live here\n")
    makefile = (root / "Makefile").read_text()
    code, said = upgrade(root, env, tool, 2)
    assert code == 0, said
    assert "left Makefile: local, the deploy targets live here" in said.splitlines()
    assert (root / "Makefile").read_text() == makefile


def test_upgrade_runs_only_from_the_tool_of_the_version_it_moves_to(v1_repo, upstream):
    root, env = v1_repo
    _, _, tool = upstream
    code, said = upgrade(root, env, tool, 3)
    assert code == 2
    assert "this tool is repo-standard-v2: run upgrade from the tool at repo-standard-v3" in said


def test_upgrade_with_no_version_to_move_to_is_refused(v1_repo):
    root, _ = v1_repo
    with pytest.raises(SystemExit) as exit_:
        main(["upgrade", "--root", str(root)])
    assert exit_.value.code == 2


def test_the_tools_own_upgrade_keeps_the_runner_and_gives_local_mk_an_owner(v1_repo, capsys):
    """This tree's tool, in process, moves a repo of its own version to its copies."""
    root, _ = v1_repo
    config = root / ".repo-standard.yml"
    config.write_text(re.sub(r"(?m)^standard: \d+$", f"standard: {VERSION}", config.read_text()))
    assert main(["upgrade", "--to", str(VERSION), "--root", str(root), "--upstream", ""]) == 0
    said = capsys.readouterr().out.splitlines()
    assert "wrote Makefile" in said, said
    assert (root / "Makefile").read_text().endswith(LOCAL_MAKE)
    assert OWNS_LOCAL_MAKE in config.read_text()
    caller = (root / ".github/workflows/check.yml").read_text()
    assert f"runner: {RUNNER}" in caller and f"runs-on: {RUNNER}" in caller
    assert main(["upgrade", "--to", str(VERSION), "--root", str(root), "--upstream", ""]) == 0
    assert (
        capsys.readouterr().out.splitlines()[-1].endswith("nothing to write; run `make lint` next")
    )


def test_upgrade_never_moves_a_pin_down(v1_repo):
    root, _ = v1_repo
    config = load(root)
    above = Config(standard=VERSION + 1, owners=config.owners)
    with pytest.raises(Refused, match="a pin only moves up"):
        upgrade_run(root, above, tracked(root), VERSION, None)


def test_a_repo_of_several_stacks_owns_each_adapters_scripts_and_no_stack_mk():
    config = Config(stacks={"api": Stack("go", ("api",)), "app": Stack("python-uv", ("app",))})
    found = owned.files(STANDARD, config, [], owned.Kind.OWNED)
    assert {"scripts/go.py", "scripts/select.py"} <= set(found)
    assert "scripts/stack.mk" not in found


def test_another_versions_tree_is_cloned_once_into_the_cache(tmp_path, upstream, monkeypatch):
    source, _, _ = upstream
    other = 2 if VERSION == 1 else 1
    with pytest.raises(Unreadable, match="no upstream to clone it from"):
        owned.tree(other, tmp_path, None)
    with pytest.raises(Unreadable, match="git clone"):
        owned.tree(other, tmp_path, str(tmp_path / "gone"))
    monkeypatch.setattr(owned, "CLONE_SECONDS", 0.000001)
    with pytest.raises(Unreadable, match="took over"):
        owned.tree(other, tmp_path, str(source))
    monkeypatch.undo()
    shutil.rmtree(tmp_path / ".cache", ignore_errors=True)
    found = owned.tree(other, tmp_path, str(source))
    assert found == tmp_path / ".cache" / f"repo-standard-v{other}" / "features" / "repo-standard"
    assert owned.tree(other, tmp_path, None) == found
    bare = tmp_path / "bare"
    (bare / ".cache" / f"repo-standard-v{other}").mkdir(parents=True)
    with pytest.raises(Unreadable, match="holds no features/repo-standard/skeleton"):
        owned.tree(other, bare, None)


def test_upgrade_says_each_thing_it_left_in_a_repo_shaped_its_own_way(v1_repo, capsys):
    """A repo with no pin line, no Makefile among its owners, a local file, a missing owned file
    and no adapter's scripts: upgrade pins it, writes what is missing and says what it left."""
    root, _ = v1_repo
    config = root / ".repo-standard.yml"
    text = re.sub(r"(?m)^standard: \d+\n", "", config.read_text())
    text = text.replace("    - Makefile\n", "")
    config.write_text(text + "local:\n  .github/workflows/check.yml: the check builds an image\n")
    (root / ".github/workflows/borders.yml").unlink()
    (root / "scripts/select.py").unlink()
    assert main(["upgrade", "--to", str(VERSION), "--root", str(root), "--upstream", ""]) == 0
    said = capsys.readouterr().out.splitlines()
    assert config.read_text().startswith(f"standard: {VERSION}\n")
    for line in (
        "left .github/workflows/check.yml: local, the check builds an image",
        "wrote .github/workflows/borders.yml",
        "left .repo-standard.yml: name local.mk in `owners`, beside the Makefile",
        "left the adapters' scripts: the repo sets no stacks and holds none of them",
    ):
        assert line in said, said


def test_upgrade_in_process_runs_only_to_its_own_version(v1_repo, capsys):
    root, _ = v1_repo
    assert main(["upgrade", "--to", str(VERSION + 1), "--root", str(root), "--upstream", ""]) == 2
    assert f"run upgrade from the tool at repo-standard-v{VERSION + 1}" in capsys.readouterr().err


def test_a_write_that_fails_leaves_the_file_as_it_was_and_no_temporary_file(v1_repo, monkeypatch):
    root, _ = v1_repo
    before = snapshot(root)

    def refuse(source, target):
        raise OSError("the disk is full")

    monkeypatch.setattr("repo_standard.upgrade.os.replace", refuse)
    with pytest.raises(OSError, match="the disk is full"):
        upgrade_run(root, load(root), tracked(root), VERSION, None)
    assert snapshot(root) == before
