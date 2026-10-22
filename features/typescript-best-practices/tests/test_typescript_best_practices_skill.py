"""The typescript-best-practices skill names files outside its own directory, by paths from the
repo's root. When the skill is linked, its block prints that root, and every file the skill
names is under it."""

from skill_blocks import (
    home,
    prints_the_root_and_names_only_files_under_it,
    repo,
    says_it_is_no_link_into_the_repo,
)

__all__ = ["home", "repo"]


def test_a_linked_typescript_best_practices_prints_the_root_and_names_files_under_it(repo, home):
    prints_the_root_and_names_only_files_under_it("typescript-best-practices", repo, home)


def test_a_typescript_best_practices_that_is_no_link_into_the_repo_says_so(repo, home):
    says_it_is_no_link_into_the_repo("typescript-best-practices", repo, home)
