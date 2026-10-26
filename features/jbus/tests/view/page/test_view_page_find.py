"""The Find drawer in the browser: tapped from the first screen, typed into, at 1440 and 390."""

from pathlib import Path

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, look
from view.scene import ago, row, table

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


FIND = (Path(__file__).parent / "find.js").read_text()


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_typing_part_of_a_title_finds_a_merged_row_with_no_sideways_scroll(scene, tmp_path, screen):
    scene.queue([*table(), row("rye-crust-with-a-long-slug-that-has-to-wrap", "merged", pr="#5")])
    scene.moves(
        ("rye-loaf", "pr", "merged", 40),
        ("rye-crust-with-a-long-slug-that-has-to-wrap", "pr", "merged", 3 * 24 * 60),
    )
    (scene.state / "briefs").mkdir()
    (scene.state / "briefs" / "rye-loaf.md").write_text("# rye-loaf: bake the rye loaf\n")
    (scene.state / "briefs" / "rye-crust-with-a-long-slug-that-has-to-wrap.md").write_text(
        "# rye-crust-with-a-long-slug-that-has-to-wrap: the crust, not the loaf\n"
    )
    script = 'window.__type = "rye LOAF";' + FIND
    seen = look(scene, tmp_path, at=5000, budget=9000, screen=screen, script=script)
    assert seen["errors"] == []
    assert (seen["hash"], seen["open"], seen["title"]) == ("#/demo/find", True, "Find a task")
    assert seen["focus"] == "find-q", "the box has the focus when the drawer opens"
    assert seen["said"] == "2 matches."
    stamp = ago(minutes=3 * 24 * 60).astimezone()
    assert seen["found"] == [
        f"rye-loaf bake the rye loaf Merged #9 merged {ago(minutes=40).astimezone():%H:%M}",
        "rye-crust-with-a-long-slug-that-has-to-wrap the crust, not the loaf Merged #5 merged "
        f"{stamp:%m-%d %H:%M}",
    ]
    assert seen["cut"] == []
    assert seen["wide"][0] <= seen["wide"][1]
    assert seen["page"] == [screen[0], screen[0]]
