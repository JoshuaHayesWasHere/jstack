"""One stage vocabulary on every screen: the board's stages, as `/panel/pipeline.json` gives
them, are the names the project page and help say, and a row is on one stage
in each of them.

The names are the board's eleven, with its second review called "Re-review", short enough
that the board's column heads keep their one line at a desk. Help lists them from the one
table, in order, and no two of its entries share a name.
"""

from pathlib import Path

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, look
from view.scene import homed

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]

NAMES = [
    "Scout",
    "Queued",
    "Crew",
    "Needs you",
    "Review",
    "Fix",
    "Re-review",
    "Check",
    "Stacked",
    "Merge",
    "Merged",
]

PROBE = (Path(__file__).parent / "one_stage.js").read_text()


def seen(scene, tmp_path, route):
    return look(scene, tmp_path, at=2500, route=route, screen=DESK, script=PROBE)


@pytest.fixture
def screens(scene, tmp_path):
    homed(scene)
    found = {}
    for name, route in (("page", "#/demo"), ("help", "#/demo/help")):
        found[name] = seen(scene, tmp_path / name, route)
        assert found[name]["errors"] == []
    return found


def test_the_project_page_and_help_name_the_boards_stages(screens):
    board = screens["page"]["pipeline"]
    assert board["stages"] == NAMES
    assert screens["help"]["help_stages"] == NAMES
    rows = [
        one for one in screens["page"]["rows"] if not one["key"].startswith(("item:", "thread:"))
    ]
    assert rows
    assert {one["stage"] for one in rows} <= set(NAMES)


def test_a_row_is_on_one_stage_on_every_screen(screens):
    board = screens["page"]["pipeline"]
    name = dict(zip(board["keys"], board["stages"], strict=True))
    on_board = {one["slug"]: name[one["stage"]] for one in board["rows"]}
    on_page = {one["key"]: one["stage"] for one in screens["page"]["rows"]}
    both = set(on_board) & set(on_page)
    assert len(both) >= 3
    for slug in both:
        assert on_board[slug] == on_page[slug], slug


def test_no_two_entries_of_help_share_a_name(screens):
    names = screens["help"]["help"]
    assert len(names) > 40
    assert sorted({one for one in names if names.count(one) > 1}) == []
