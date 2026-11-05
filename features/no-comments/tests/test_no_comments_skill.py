"""The no-comments skill names files outside its own directory, by paths from the repo's root.
When the skill is linked, its block prints that root, and every file the skill names is under
it."""

from skill_blocks import (
    home,
    prints_the_root_and_names_only_files_under_it,
    repo,
)

__all__ = ["home", "repo"]


def test_a_linked_no_comments_prints_the_root_and_every_file_it_names_is_under_it(repo, home):
    prints_the_root_and_names_only_files_under_it("no-comments", repo, home)
