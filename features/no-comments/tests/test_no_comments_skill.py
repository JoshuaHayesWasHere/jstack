"""The no-comments skill names files outside its own directory. When the skill is linked, its block
prints the repo's root, and every file the skill names from there is under that root."""

from skill_blocks import (
    home,
    prints_the_root_and_names_only_files_under_it,
    repo,
    says_it_is_no_link_into_the_repo,
)

__all__ = ["home", "repo"]


def test_a_linked_no_comments_prints_the_root_and_every_file_it_names_is_under_it(repo, home):
    prints_the_root_and_names_only_files_under_it("no-comments", repo, home)


def test_a_no_comments_that_is_no_link_into_the_repo_says_so(repo, home):
    says_it_is_no_link_into_the_repo("no-comments", repo, home)
