"""jmerge reads whether a row is over from jbus (`jmerge.bus.over`, which jbus answers with
`jbus.work.over`), and holds the pull request of a row that is over.

The tests run the real `jmerge` as `test_jmerge_order.py` runs it: `alpha` (#7) and `beta` (#8)
are open on one reviewed head, and the queue is the project's `queue.json`."""

import pytest

from jmerge import ready
from test_jmerge_order import BETA_URL, merged_numbers, queue_of, row, two
from test_home_merge import URL

__all__ = ["two"]


@pytest.mark.parametrize("over", ["done", "merged"])
def test_jmerge_holds_the_pull_request_of_a_row_that_is_over(two, over):
    queue_of(two.home, [row("alpha", status=over, pr="#7"), row("beta", pr="#8")])
    said = two.run()
    assert said[0] == f"hold 7 {URL}: {ready.ROW_OVER.format(status=over)}"
    assert merged_numbers(said) == [8]


def test_a_merge_after_child_waits_until_its_parent_is_over(two):
    path = queue_of(
        two.home,
        [row("alpha", status="running"), row("beta", pr="#8", merge_after=["alpha"])],
    )
    said = two.run("--check")
    assert said[1] == f"wait 8 {BETA_URL}: merges after alpha (no pull request yet), not merged yet"
    table = path.read_text().replace('"running"', '"done"')
    path.write_text(table)
    assert two.run("--check")[1].startswith("ready 8 ")
