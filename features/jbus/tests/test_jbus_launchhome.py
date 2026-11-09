"""`jbus.launchhome.homed` puts the queued brief's `Home:` line in the copy a launch writes, and
leaves a copy as it is where the brief names no home or the copy names one already."""

import pytest

from jbus.launchhome import homed

QUEUED = "# alpha: a task\nHome: flow\nTask: x\n"


@pytest.mark.parametrize(
    ("text", "brief"),
    [("# alpha: a task\nTask: x\n", "# alpha: a task\nTask: x\n"), ("Home: sc\n", QUEUED)],
    ids=["the brief names no home", "the copy names one already"],
)
def test_a_copy_is_left_as_it_is(text, brief):
    assert homed(text, brief) == text


def test_the_line_goes_last_in_the_head_of_a_copy_that_ends_with_no_newline():
    assert homed("# alpha: a task\nTask: x", QUEUED) == "# alpha: a task\nTask: x\nHome: flow\n"
