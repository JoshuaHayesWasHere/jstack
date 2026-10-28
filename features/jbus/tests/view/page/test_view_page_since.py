"""The Landed since you looked card of `#/`, in the browser: a first visit names what merged over
what jbus kept and keeps the time of the visit, and a visit after three merges and a stall
names the three, newest first, and the row newly stuck. The time is all the page keeps, in the
browser's own storage, and it sends it nowhere."""

import re

import json
from pathlib import Path

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, look
from view.scene import NOW, ago, free_port, row
from view.test_view_since import quiet
from view.test_view_wrong import STALL, idle

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]

SINCE = (Path(__file__).parent / "since.js").read_text()
KEY = "jbus.since.looked"


def stamp(moment):
    """A time as the page keeps it: milliseconds since the epoch, as a string."""
    return str(int(moment.timestamp() * 1000))


def visited(scene, tmp_path, port, screen):
    seen = look(scene, tmp_path, route="#/", script=SINCE, at_port=port, screen=screen)
    assert seen["errors"] == []
    return seen


def three_merges_and_a_stall(scene):
    scene.moves(
        ("tea-pot", "pr", "merged", 30),
        ("tea-cup", "pr", "merged", 20),
        ("tea-urn", "pr", "merged", 10),
    )
    scene.queue(
        [
            row("jam-jar", "running", thread="mcp:0000"),
            row("oat-spoon", "pr", pr="#12", checks="passed", why="wait: it has no review yet"),
        ]
    )
    scene.events(("stall", "quiet", "oat-spoon", STALL, 6))
    scene.write("expedite.json", {"oat-spoon": idle(12)})


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["1440", "390"])
def test_a_revisit_after_three_merges_and_a_stall_says_so_and_keeps_only_the_time(
    scene, tmp_path, screen
):
    port = free_port()
    scene.now = ago(minutes=40)
    quiet(scene)
    first = visited(scene, tmp_path, port, screen)
    assert "your first look" in first["since"], "a first visit has no look to compare with"
    assert first["kept"] == {KEY: stamp(ago(minutes=40))}

    three_merges_and_a_stall(scene)
    scene.now = NOW
    again = visited(scene, tmp_path, port, screen)
    assert again["since"].lower().startswith("landed since you looked 3 ")
    assert re.search(r"tea-urn .*tea-cup .*tea-pot ", again["since"]), "newest first"
    assert "you looked 40m ago" in again["since"]
    assert re.search(r"Stuck oat-spoon ?\.", again["since"])
    assert ["oat-spoon", "#/demo/task/oat-spoon"] in again["links"]
    assert again["kept"] == {KEY: stamp(NOW)}, "the time of the visit, and nothing else"
    left, _, wide, _ = again["box"]
    assert left >= 0 and left + wide <= again["wide"]
    for seen in (first, again):
        sent = json.dumps([seen["writes"], seen["counted"], seen["asked"]])
        assert stamp(ago(minutes=40)) not in sent and stamp(NOW) not in sent
        assert KEY not in sent
