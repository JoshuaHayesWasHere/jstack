"""The built parts of `docs/jbus.md` and `docs/jbus/`, and the length of every docs page."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jbus import pages, wake

REPO = Path(__file__).parent.parent
CAP = 300
# A page over the cap, by its path under docs/, until it is split. The list only shrinks.
LONG = frozenset()


def over(root, allowed):
    """The pages under `root/docs` over the cap that `allowed` lacks, and those it lists that
    are not over it any more."""
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
    """A copy of the two pages and the folder, with this test in it."""
    shutil.copytree(REPO / pages.FOLDER, tmp_path / pages.FOLDER)
    shutil.copy(REPO / pages.INDEX, tmp_path / pages.INDEX)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def text(root):
    return {path: path.read_bytes() for path in sorted((root / "docs").glob("**/*.md"))}


def test_the_committed_pages_have_what_the_tree_has():
    ran = subprocess.run(
        [sys.executable, "-m", "jbus.pages", "--check"], cwd=REPO, capture_output=True, text=True
    )
    assert (ran.returncode, ran.stderr) == (0, ""), ran.stdout


def test_a_page_added_removed_or_renamed_without_the_index_is_behind(tree, capsys):
    folder = tree / pages.FOLDER
    for change in (
        lambda: (folder / "a-new-page.md").write_text("# A new page\n\nIts words.\n"),
        lambda: (folder / "the-plan.md").unlink(),
        lambda: (folder / "the-queue.md").rename(folder / "the-queues.md"),
    ):
        assert pages.main(["--check"]) == 0
        change()
        before = text(tree)
        assert pages.main(["--check"]) == 1
        assert text(tree) == before
        assert "behind: docs/jbus.md: run" in capsys.readouterr().out
        assert pages.main([]) == 0
        assert pages.main(["--check"]) == 0


def test_the_index_is_a_line_a_page_by_its_heading(tree):
    (tree / pages.FOLDER / "a-new-page.md").write_text("# A new page\n\nIts words.\n")
    pages.main([])
    said = (tree / pages.INDEX).read_text()
    assert "- [A new page](jbus/a-new-page.md)\n" in said
    assert "- [The plan](jbus/the-plan.md)\n" in said
    built = said.split("<!-- built: pages -->\n")[1].split("<!-- built: end -->")[0]
    assert built.count("\n") == len(list((tree / pages.FOLDER).glob("*.md")))
    assert said.startswith((REPO / pages.INDEX).read_text().split("<!-- built:")[0])


def test_a_kind_added_to_an_events_without_the_table_is_behind(tree, monkeypatch, capsys):
    monkeypatch.setattr(wake, "LOUDNESS", {**wake.LOUDNESS, "a-new-kind": "quiet"})
    assert pages.main(["--check"]) == 1
    assert f"behind: {pages.EVENTS_PAGE}: run" in capsys.readouterr().out
    assert pages.main([]) == 0
    said = (tree / pages.EVENTS_PAGE).read_text()
    assert "| `quiet` | `a-new-kind`, `condition`, " in said


def test_a_page_with_no_heading_is_refused(tree, capsys):
    (tree / pages.FOLDER / "no-heading.md").write_text("Words with no heading.\n")
    before = text(tree)
    assert pages.main([]) == 2
    assert "no-heading.md: its first line is not `# <heading>`" in capsys.readouterr().err
    assert text(tree) == before


def test_no_docs_page_is_over_the_cap_unless_listed_and_a_listed_one_is():
    assert over(REPO, LONG) == []


def test_a_page_over_the_cap_and_a_listed_page_under_it_are_found(tmp_path):
    (tmp_path / "docs" / "deep").mkdir(parents=True)
    (tmp_path / "docs" / "long.md").write_text("line\n" * (CAP + 1))
    (tmp_path / "docs" / "deep" / "short.md").write_text("line\n" * CAP)
    assert over(tmp_path, frozenset()) == [f"long.md: {CAP + 1} lines"]
    assert over(tmp_path, frozenset({"long.md", "deep/short.md"})) == [
        f"deep/short.md: under {CAP}, take it off the list"
    ]
