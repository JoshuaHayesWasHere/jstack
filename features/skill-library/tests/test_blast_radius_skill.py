"""The blast-radius skill's block: it prints the files a branch and its working tree changed,
and says so when there is no change to read."""

from skill_blocks import block, git, home, outside, repo, run

__all__ = ["home", "outside", "repo"]


def test_blast_radius_prints_the_files_a_branch_and_its_working_tree_changed(repo, home):
    git(repo, "checkout", "-q", "-b", "fix-login")
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "two")
    (repo / "a.txt").write_text("one\nand uncommitted\n")
    (repo / "c.txt").write_text("three\n")
    said = run(block("blast-radius", "merge-base"), repo, home)
    assert [line.split("|")[0].strip() for line in said[:2]] == ["a.txt", "b.txt"]
    assert said[2].strip().startswith("2 files changed")
    assert said[3:] == [" new, not added: c.txt"]


def test_blast_radius_reads_a_change_that_is_only_new_files(repo, home):
    (repo / "c.txt").write_text("three\n")
    assert run(block("blast-radius", "merge-base"), repo, home) == [" new, not added: c.txt"]


def test_blast_radius_says_so_when_there_is_no_change_to_read(repo, home, outside):
    body = block("blast-radius", "merge-base")
    assert run(body, repo, home) == ["no change to read: nothing differs from main"]
    assert run(body, outside, home) == [
        "no change to read: this is not a git repository with a branch main"
    ]
