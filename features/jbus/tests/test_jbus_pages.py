"""These tests check the built part of `features/jbus/docs/jbus/`."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import jbus
from jbus import pages, wake
from testing.paths import REPO


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Make a copy of the folder, with this test in it."""
    folder = Path(pages.EVENTS_PAGE).parent
    shutil.copytree(REPO / folder, tmp_path / folder)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def text(root):
    return {path: path.read_bytes() for path in sorted((root / "docs").glob("**/*.md"))}


def test_the_committed_pages_have_what_the_tree_has():
    ran = subprocess.run(
        [sys.executable, "-m", "jbus.pages", "--check"], cwd=REPO, capture_output=True, text=True
    )
    assert (ran.returncode, ran.stderr) == (0, ""), ran.stdout


def test_a_kind_added_to_an_events_without_the_table_is_behind(tree, monkeypatch, capsys):
    monkeypatch.setattr(wake, "LOUDNESS", {**wake.LOUDNESS, "a-new-kind": "quiet"})
    assert pages.main(["--check"]) == 1
    assert f"behind: {pages.EVENTS_PAGE}: run" in capsys.readouterr().out
    assert pages.main([]) == 0
    said = (tree / pages.EVENTS_PAGE).read_text()
    assert "- `a-new-kind`\n- `act`\n- `alert`\n" in said


def committed(root, message):
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, "commit", "-qm", message], cwd=root, check=True)
    said = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return said.stdout.strip()


def test_two_rows_that_each_add_a_kind_merge_with_no_conflict(tree, monkeypatch):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tree, check=True)
    start = committed(tree, "start")
    heads = []
    for kind in ("a-new-kind", "zz-new-kind"):
        subprocess.run(["git", "checkout", "-q", "-B", kind, start], cwd=tree, check=True)
        with monkeypatch.context() as patched:
            patched.setattr(wake, "LOUDNESS", {**wake.LOUDNESS, kind: "quiet"})
            assert pages.main([]) == 0
        heads.append(committed(tree, kind))
    merged = subprocess.run(
        ["git", "merge-tree", "--write-tree", *heads], cwd=tree, capture_output=True, text=True
    )
    assert merged.returncode == 0, merged.stdout
    both = {**wake.LOUDNESS, "a-new-kind": "quiet", "zz-new-kind": "quiet"}
    monkeypatch.setattr(wake, "LOUDNESS", both)
    page = subprocess.run(
        ["git", "show", f"{merged.stdout.strip()}:{pages.EVENTS_PAGE}"],
        cwd=tree,
        capture_output=True,
        text=True,
    )
    assert page.stdout == pages.build(tree)[pages.EVENTS_PAGE]


REACHING = """from jbus import verbs, zz_helper

VERBS = (verbs.Verb("zz-reach", "a verb that finds its project", verbs.nothing, zz_helper.run),)
"""
HELPER = """from jbus import verbs


def run(args, config):
    return verbs.here(config, args.project) and 0
"""
FREE = """from jbus import verbs


def _run(args, config):
    return len(verbs.piped("zz-free", "its lines"))


VERBS = (verbs.Verb("zz-free", "a verb that takes no project", verbs.nothing, _run),)
"""


def verb_module(folder, name, source):
    folder.mkdir(exist_ok=True)
    (folder / f"{name}.py").write_text(source)


def part(text, name):
    return re.search(rf"<!-- built: {name} -->\n(.*?)<!-- built: end -->", text, re.S)[1]


def test_a_verb_added_in_a_module_lands_in_its_lists_with_no_edit_of_the_page(
    tree, monkeypatch, capsys
):
    extra = tree / "extra"
    verb_module(extra, "zz_helper", HELPER)
    verb_module(extra, "zz_reach", REACHING)
    verb_module(extra, "zz_free", FREE)
    monkeypatch.setattr(pages, "PATHS", [*jbus.__path__, str(extra)])
    assert pages.main(["--check"]) == 1
    assert f"behind: {pages.VERBS_PAGE}: run" in capsys.readouterr().out
    assert pages.main([]) == 0
    said = (tree / pages.VERBS_PAGE).read_text()
    assert "- `jbus wakes`\n- `jbus zz-reach`\n" in part(said, "here")
    assert "- `jbus word`\n- `jbus zz-free`\n" in part(said, "none")
    assert "- `jbus told`\n- `jbus zz-free`\n" in part(said, "piped")
    assert "zz-reach" not in part(said, "none") + part(said, "piped")
    assert "zz-free" not in part(said, "here")


def test_two_rows_that_each_add_a_verb_module_merge_with_no_conflict(tree, monkeypatch):
    extra = tree / "extra"
    monkeypatch.setattr(pages, "PATHS", [*jbus.__path__, str(extra)])
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tree, check=True)
    start = committed(tree, "start")
    added = {"aa_free": FREE.replace("zz-free", "aa-free"), "zz_free": FREE}
    heads = []
    for name, source in added.items():
        subprocess.run(["git", "checkout", "-q", "-B", name, start], cwd=tree, check=True)
        shutil.rmtree(extra, ignore_errors=True)
        verb_module(extra, name, source)
        assert pages.main([]) == 0
        heads.append(committed(tree, name))
    merged = subprocess.run(
        ["git", "merge-tree", "--write-tree", *heads], cwd=tree, capture_output=True, text=True
    )
    assert merged.returncode == 0, merged.stdout
    for name, source in added.items():
        verb_module(extra, name, source)
    page = subprocess.run(
        ["git", "show", f"{merged.stdout.strip()}:{pages.VERBS_PAGE}"],
        cwd=tree,
        capture_output=True,
        text=True,
    )
    assert page.stdout == pages.build(tree)[pages.VERBS_PAGE]
    assert "- `jbus aa-free`\n" in page.stdout and "- `jbus zz-free`\n" in page.stdout
