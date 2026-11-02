"""These tests check the built part of `features/jbus/docs/jbus/`, and the length of every docs
page, each page under a `features/<name>/docs/`.

`LONG` names each page over the cap, by its path in the repo, until somebody splits the page. The
list only shrinks."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jbus import pages, wake
from testing.paths import REPO

READ_SET = ("features/*/docs/",)

CAP = 300
LONG = frozenset(
    {
        "features/jbus/docs/jbus/the-queue.md",
        "features/jinstall/docs/configuration.md",
        "features/jmerge/docs/jmerge.md",
    }
)


def over(root, allowed):
    """Return the pages under each `root/features/<name>/docs` that are over the cap and that
    `allowed` lacks, and the pages that `allowed` lists that are no longer over the cap."""
    lengths = {
        str(path.relative_to(root)): len(path.read_text().splitlines())
        for path in root.glob("features/*/docs/**/*.md")
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


def verbs_of(table):
    """The verbs of a table, by the words before their arguments."""
    return [re.match(r"\| `([^\[<`]*)", row)[1].strip() for row in table.splitlines()[2:]]


def test_each_table_of_verbs_is_sorted_so_a_new_verb_lands_in_its_own_place():
    page = (REPO / "features/jbus/docs/jbus/the-verbs.md").read_text()
    tables = re.findall(r"^\| Verb \|.*\n(?:\|.*\n)+", page, re.M)
    assert len(tables) == 3
    for table in tables:
        assert verbs_of(table) == sorted(verbs_of(table))


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
