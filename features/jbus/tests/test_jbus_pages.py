"""These tests check the built part of `features/jbus/docs/jbus/`, and the length of every docs
page.

`LONG` names each page over the cap, by its path under docs/, until somebody splits the page. The
list only shrinks."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jbus import pages, wake
from testing.paths import REPO

CAP = 300
LONG = frozenset()


def over(root, allowed):
    """Return the pages under `root/docs` that are over the cap and that `allowed` lacks, and the
    pages that `allowed` lists that are no longer over the cap."""
    lengths = {
        str(path.relative_to(root / "docs")): len(path.read_text().splitlines())
        for path in (root / "docs").glob("**/*.md")
    }
    long = {name for name, lines in lengths.items() if lines > CAP}
    return [f"{name}: {lengths[name]} lines" for name in sorted(long - allowed)] + [
        f"{name}: under {CAP}, take it off the list" for name in sorted(allowed - long)
    ]


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
    assert "| `quiet` | `a-new-kind`, `act`, `cancelled`, `clock`, " in said


def test_no_docs_page_is_over_the_cap_unless_listed_and_a_listed_one_is():
    assert over(REPO, LONG) == []


def test_a_page_over_the_cap_and_a_listed_page_under_it_are_found(tmp_path):
    docs = tmp_path / "features" / "a-feature" / "docs"
    (docs / "deep").mkdir(parents=True)
    (docs / "long.md").write_text("line\n" * (CAP + 1))
    (docs / "deep" / "short.md").write_text("line\n" * CAP)
    long = "features/a-feature/docs/long.md"
    short = "features/a-feature/docs/deep/short.md"
    assert over(tmp_path, frozenset()) == [f"{long}: {CAP + 1} lines"]
    assert over(tmp_path, frozenset({long, short})) == [
        f"{short}: under {CAP}, take it off the list"
    ]
