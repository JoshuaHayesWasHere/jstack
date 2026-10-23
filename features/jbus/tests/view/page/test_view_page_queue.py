"""The queue on the page: a drawer's one state, the flow, and the threads."""

import json

import pytest

from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    WORDS,
    a_day_of_threads,
    clean,
    look,
    slugs,
    walked,
)
from view.scene import NAMES, item, kinds, row

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


FLOWS = {5: (3, 2), 25: (6, 5, 4, 3, 2, 2, 2, 1), 60: (20, 14, 8, 6, 4, 3, 2, 2, 1)}


def flowing(scene, sizes):
    """A queue with the given number of rows in each wave, in the queue's order. They are
    behind a row at a gate, and beside a row that runs. The first row of wave 1 waits on the
    row at the gate. Each of the other rows waits on the row in the same place in the wave
    before. Every second row also waits on the next row of that wave before. It gives back the
    rows of each wave."""
    names = slugs()
    gate, runs = next(names), next(names)
    rows = [
        row(gate, "gate", why="a gate the Chef has", priority=0),
        row(runs, "running", thread="mcp:1", priority=0),
    ]
    waves = []
    for many in sizes:
        before, wave = (waves[-1] if waves else []), []
        for at in range(many):
            depends = [before[(at + more) % len(before)] for more in range(1 + at % 2) if before]
            if (len(waves), at) == (1, 0):
                depends = [gate]
            wave.append(next(names))
            rows.append(row(wave[-1], depends=list(dict.fromkeys(depends)), priority=len(rows)))
        waves.append(wave)
    scene.queue(rows)
    scene.moves((runs, "launched", "running", 5))
    scene.merge_log()
    scene.waiting([item("row", f"row:{gate}", f"gate {gate}: which way?", slug=gate, minutes=9)])
    return waves


def test_a_drawer_says_one_state_and_the_line_names_what_blocks_a_task(scene, tmp_path):
    expected = kinds(scene)
    findings = "wait: its findings are not handled: the Result has no Fixed line"
    chain = [
        row("nut-shell", "pr", pr="#41", why=findings),
        row("nut-meat", depends=["nut-shell"], why="depends on nut-shell"),
        row("nut-oil", depends=["nut-meat"], why="depends on nut-meat"),
    ]
    chain[1]["approval"] = {
        "basis": "rule",
        "ref": "6",
        "words": "A follow-up needs no new approval.",
        "said_at": "",
        "said_in": "",
        "checked": True,
        "follows": "nut-shell",
        "ran_by": {"session": "a-session", "directory": "/home/user/repos/demo"},
        "ran_at": "2026-10-12 09:00 ET",
    }
    scene.queue(json.loads((scene.state / "queue.json").read_text()) + chain)
    seen = look(scene, tmp_path, pick="fig-sap")
    opened = clean(seen)
    drawers = {one["target"]: one["said"] for one in seen["opened"]}
    by_rule = (
        "rule 6, follow-up of nut-shell; run 2026-10-12 09:00 ET by the demo home; you did not "
        "speak of this row by rule 6"
    )
    assert by_rule in drawers["task:nut-meat"]
    assert "by rule" not in drawers["task:nut-shell"]
    rows = {row["slug"]: row for row in seen["prog"]}
    assert {"fig-pip", "fig-tree", "nut-oil"} & set(rows) == {"nut-oil"}
    assert (rows["nut-shell"]["state"], rows["nut-shell"]["open"]) == ("Findings", "task:nut-shell")
    assert rows["nut-meat"]["chips"] == ["behind nut-shell"]
    assert rows["fig-sap"]["chips"] == ["behind fig-tart"]
    assert seen["flow"]["chain"] == "3 deep, behind nut-shell (Findings)"
    way = seen["picked"]
    assert (way["picked"], way["up"], way["down"]) == (["fig-sap"], ["fig-tart"], [])
    assert way["said"] == (
        "fig-sap waits on 1 row here and on fig-pip (Merged), and 0 rows wait on it."
    )
    now = {one["target"].removeprefix("task:"): one["now"] for one in seen["opened"]}
    assert {f"task:{slug}" for slug in expected} <= opened
    assert [one["acts"][0]["text"] for one in seen["needs"]["now"]].count("Close it") == 2
    for slug, kind in expected.items():
        name = "Ended, not closed" if slug in ("fig-burr", "fig-rind") else NAMES[kind]
        assert now[slug].startswith(f"NOW: {name.upper()} "), now[slug]
        assert "This step" not in now[slug] and " or " not in now[slug], now[slug]
        assert "the row disagrees" not in now[slug], now[slug]
    assert "launch" not in now["fig-pip"] + now["fig-stalk"]
    assert "pull request #21 is merged" in now["fig-pip"]
    assert "waits for a slot" in now["fig-jam"]
    assert "Blocked by nut-shell Findings" in now["nut-meat"]
    assert "2 tasks wait behind it: nut-meat, nut-oil" in now["nut-shell"]
    assert "2 tasks wait behind it: fig-sap, fig-stem" in now["fig-pip"]
    assert "Blocked by fig-tart Running" in now["fig-sap"]
    assert "task:fig-pip" in seen["links"]
    assert seen["words"] <= WORDS, seen["words"]


@pytest.mark.parametrize(("screen", "columns"), [(DESK, 9), (PHONE, 1)])
def test_the_drawer_of_the_queue_as_a_flow_marks_the_way_of_the_row_picked(
    scene, tmp_path, screen, columns
):
    waves = flowing(scene, FLOWS[25])
    seen = look(scene, tmp_path, budget=9000, screen=screen, pick="tea-ladle")
    clean(seen, screen)
    drawer, picked = seen["flow"], seen["picked"]
    assert drawer["title"] == "The queue as a flow"
    assert drawer["chain"] == "8 deep, behind your gate on tea-kettle"
    assert drawer["columns"] == [
        ["OUT 2", ["jam-kettle", "tea-kettle"]],
        ["READY 6", waves[0]],
        ["NEXT 5", waves[1]],
        *([f"WAVE {at + 2} {len(wave)}", wave] for at, wave in enumerate(waves[2:])),
    ]
    assert drawer["lefts"] == columns
    assert drawer["borders"] == ["solid"]
    assert (drawer["picked"], drawer["up"], drawer["down"], drawer["dim"]) == ([], [], [], 0)
    assert drawer["said"] == "Pick a row to mark what it waits on and what waits on it."
    assert picked["picked"] == ["tea-ladle"]
    assert picked["up"] == ["tea-kettle", "mint-kettle", "rye-saucer", "leek-saucer"]
    assert picked["down"] == ["oat-ladle", "rye-ladle", "fig-ladle", "plum-ladle", "kale-ladle"]
    assert picked["dim"] == 27 - 10
    assert picked["said"] == "tea-ladle waits on 4 rows here, and 5 rows wait on it."
    assert seen["taps"] == [[], ["kale-ladle"], ["kale-ladle"], ["tea-ladle"]]
    assert picked["box"] == drawer["box"]
    if screen == PHONE:
        assert picked["box"] == [0, 0, *PHONE]


def test_a_thread_is_a_link_that_opens_cold_with_the_way_back_to_its_project(scene, tmp_path):
    a_day_of_threads(scene)
    (first,) = walked(scene, tmp_path, "#/demo/thread/scout/look", ["look"])
    assert (first["open"], first["hash"], first["title"]) == (
        True,
        "#/demo/thread/scout/look",
        "look",
    )
    assert first["crumbs"] == [
        ["All", "#/"],
        ["demo", "#/demo"],
        ["look", "#/demo/thread/scout/look"],
    ]
