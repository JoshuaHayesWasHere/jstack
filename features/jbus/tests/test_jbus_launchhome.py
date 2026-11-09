"""`jbus.launchhome.homed` puts the queued brief's `Home:` line in the copy a launch writes, and
leaves a copy as it is where the brief names no home or the copy names one already.
`jbus.launchhome.unhomed` says why a row whose brief names no child home may not launch."""

import pytest

from jbus.launchhome import homed, unhomed

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


@pytest.mark.parametrize(("line", "said"), [("", "no home"), ("Home: root\n", "root")])
def test_a_brief_that_names_no_child_home_says_why_and_how_to_give_it_one(line, said):
    why, move = unhomed("alpha", f"# alpha: a task\n{line}Task: x\n")
    assert why == f"its brief names {said}, and the root home owns no row"
    assert move == "jbus queue move alpha --home uncategorized, or the row's scope"


def test_a_brief_that_names_a_child_home_launches():
    assert unhomed("alpha", QUEUED) == ("", "")
