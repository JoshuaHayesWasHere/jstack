"""One stage vocabulary: `/state.json`, `/stack.json`, the board and each
task name the same eleven stages, in the order of the process, and each open row is on one of
them, the same in each.

The names are the board's, with its second review called "Re-review". The browser's half,
what the project page and help draw from these, is
`page/test_view_page_one_stage.py`.
"""

import dataclasses

import jsettings
from jbus.view import state as built
from view.scene import NOW, homed
from view.walk import runs, sources

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


def read(scene):
    return built.Read(
        dataclasses.replace(sources(scene), user=jsettings.load()), scene.name, NOW, runs
    )


def test_every_answer_names_the_same_eleven_stages(scene):
    homed(scene)
    said = read(scene)
    answer = said.answer()
    assert [one["name"] for one in answer["process"]] == NAMES
    assert [one["note"] for one in answer["process"]] == [one.note for one in built.STAGES]
    assert all(one["note"] for one in answer["process"])
    assert [one["name"] for one in said.asked("pipeline")["data"]["stages"]] == NAMES
    stack = built.stack(sources(scene), NOW, runs)
    assert [one["name"] for one in stack["process"]] == NAMES


def test_an_open_row_is_on_one_stage_in_the_board_and_its_task(scene):
    homed(scene)
    said = read(scene)
    tasks = {one["slug"]: one["stage"] for one in said.answer()["tasks"]}
    board = {one["slug"]: one["stage"] for one in said.asked("pipeline")["data"]["rows"]}
    assert set(board) <= set(tasks)
    assert {slug: tasks[slug] for slug in board} == board
    assert {"tea-cups", "jam-jar", "oat-milk"} <= set(board)
