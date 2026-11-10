"""`jbus queue add` refuses a brief whose `Done when:` item lands in a file the brief may not
change: the item says the file with an `(in `<path>`)` marker, and a file outside `Where:` or
under `Do not touch:` is a fault (`jbriefs.parse.lands`). An item with no marker is warned of
and still queued. The invariant it pins is #1177's: two goals that needed
.github/workflows/check.yml and testing/tests/test_check_command.py, outside its Where, were
approved, held "not met" by its review, and cleared only by the user's waiver."""

from pathlib import Path

import pytest

from jbriefs import parse

FIXTURE = Path(__file__).parent / "fixtures" / "ci2m-select-graph-cache.md"

BRIEF = (
    '# alpha: a task\nTask: "do alpha"\nDone when:\n- `make check` passes {marker}\n'
    "Proves it: `make check`\nSize: S\nWhere: `src/alpha/`, `docs/alpha.md`\n"
    "Do not touch: `src/alpha/vendor/`, jmerge\nPull request: open one when done\n"
    "Review: review\nPlaybook: feature\nSkills: tdd\n"
)
REMEDY = (
    'move the line to a follow-up brief with a "Follows: alpha" line and queue it with '
    "jbus queue add, where it is approved on this row's go"
)


def lint(marker):
    text = BRIEF.format(marker=marker)
    return parse.faults(text), parse.warnings(text, "")


def test_a_goal_that_lands_outside_where_is_refused():
    faults, _ = lint("(in `.github/workflows/check.yml`)")
    assert faults == [
        "brief's Done when 1 lands in .github/workflows/check.yml, outside Where "
        f"(src/alpha, docs/alpha.md): widen Where to it, or {REMEDY}"
    ]


@pytest.mark.parametrize(
    "marker",
    ["(in `src/alpha/cli.py`)", "(in `docs/alpha.md`)", "(in `src/alpha/a.py`, `docs/alpha.md`)"],
)
def test_a_goal_that_lands_in_a_file_where_covers_is_queued(marker):
    assert parse.covers(parse.where(BRIEF), "src/alpha/cli.py")
    assert lint(marker) == ([], [])


def test_a_goal_that_lands_under_do_not_touch_is_refused():
    faults, _ = lint("(in `src/alpha/vendor/lib.py`)")
    assert faults == [
        "brief's Done when 1 lands in src/alpha/vendor/lib.py, under Do not touch "
        f"(src/alpha/vendor): take it off Do not touch, or {REMEDY}"
    ]


def test_one_file_outside_among_several_is_refused():
    (fault,) = lint("(in `src/alpha/a.py`, `scripts/b.py`)")[0]
    assert fault.startswith("brief's Done when 1 lands in scripts/b.py, outside Where")


def test_a_goal_that_lands_in_no_file_is_queued():
    assert lint("(in none)") == ([], [])


@pytest.mark.parametrize("marker", ["", "(in CI)", "(in `src/alpha/a.py`) and more"])
def test_a_goal_with_no_marker_is_warned_of_and_still_queued(marker):
    faults, warned = lint(marker)
    assert faults == []
    assert warned == [
        "brief's Done when: has 1 of 1 items that say no file they land in, the first: "
        f"{f'`make check` passes {marker}'.strip()} (end each with (in `<path>`), the file the "
        "goal needs changed, or (in none))"
    ]


def test_1177s_goals_outside_where_are_refused_with_the_follow_up_to_queue():
    """The head of ci2m-select-graph-cache's brief, as the home queued it, with the files its
    review named for lines 3 and 4: the first of them is the fault."""
    faults = parse.faults(FIXTURE.read_text())
    assert (
        "brief's Done when 3 lands in .github/workflows/check.yml, outside Where "
        "(scripts/select_tests.py): widen Where to it, or move the line to a follow-up brief "
        'with a "Follows: ci2m-select-graph-cache" line and queue it with jbus queue add, '
        "where it is approved on this row's go"
    ) in faults
