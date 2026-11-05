"""The rows of a crew's router table that a block's output can deliver are delivered by it."""

import pytest

from crew_helpers import said


@pytest.mark.parametrize(
    "brief, then",
    [
        (
            "## Result\nStatus: done\nBranch: a   Pull request: none\n",
            ["telling-the-home", "no-pr-end"],
        ),
        ("## Result\nStatus: paused\nBranch: a   Pull request: none\n", ["telling-the-home"]),
        (
            "## Result\nStatus: done\nBranch: a   Pull request: https://e.test/1\n",
            ["stay-on-the-pr"],
        ),
    ],
)
def test_the_end_block_delivers_the_row_that_comes_next(tmp_path, brief, then):
    (line,) = said(tmp_path, "End", "tell the home", brief)
    for doc in then:
        assert f"{doc}.md" in line
