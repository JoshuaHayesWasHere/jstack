"""The Result has no `Noticed` line: a fault outside the task is a queued row or nothing.

The template is the one copy of the Result's shape, and the crew skill's stop block renders it by
hand, so both are read as a crewmate's Result would be."""

from test_crew_needs_go import queued, start
from testing.paths import REPO

TEMPLATE = REPO / "features" / "crew" / "templates" / "result.md"


def labels(text):
    """The label of each line of a Result: the words before its first colon."""
    return [line.split(":")[0] for line in text.splitlines() if ":" in line]


def test_the_result_template_has_no_noticed_line():
    found = labels(TEMPLATE.read_text())
    assert "Left" in found
    assert not [label for label in found if label.startswith("Noticed")]


def test_the_result_the_stop_block_writes_has_only_the_template_s_lines(kitchen):
    queued(kitchen, approve=False)
    _, brief = start(kitchen)
    result = brief.partition("## Result\n")[2]
    written = [label for label in labels(result) if not label.startswith("- ")]
    assert "Status" in written
    assert set(written) <= set(labels(TEMPLATE.read_text()))
