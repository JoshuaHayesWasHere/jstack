"""The architect skill names files outside its own directory, by paths from the repo's root. When
the skill is linked, its block prints that root, and every file the skill names is under it."""

from skill_blocks import (
    home,
    prints_the_root_and_names_only_files_under_it,
    repo,
    says_it_is_no_link_into_the_repo,
)

__all__ = ["home", "repo"]


def test_a_linked_architect_prints_the_root_and_every_file_it_names_is_under_it(repo, home):
    prints_the_root_and_names_only_files_under_it("architect", repo, home)


def test_an_architect_that_is_no_link_into_the_repo_says_so(repo, home):
    says_it_is_no_link_into_the_repo("architect", repo, home)
