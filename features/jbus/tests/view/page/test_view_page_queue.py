"""The queue on the page: a drawer's one state, and the threads."""

import json

import pytest

from view.page.browser import (
    BROWSES,
    LAUNCH,
    PATIENCE,
    WORDS,
    a_day_of_threads,
    clean,
    look,
    walked,
)
from view.scene import NAMES, kinds, row

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


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
    seen = look(scene, tmp_path)
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
    now = {one["target"].removeprefix("task:"): one["now"] for one in seen["opened"]}
    assert {f"task:{slug}" for slug in expected} <= opened
    left = [one for one in seen["needs"]["now"] if one["key"].partition("/")[2].startswith("left:")]
    assert len(left) == 3, "each task left over is one need of the one list"
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
