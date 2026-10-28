"""The glossary, the keys and axe over every view."""

import pytest

from testing.paths import REPO
from view.days import TODAY, lineup
from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    a_day_of_threads,
    gated,
    look,
)
from view.scene import stacked

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


@pytest.mark.parametrize(("route", "help"), [("#/demo", "#/demo/help"), ("#/", "#/help")])
def test_the_question_mark_key_opens_the_glossary_and_esc_goes_back(scene, tmp_path, route, help):
    lineup(scene, TODAY)
    walk = ["key:?:", "key:?:", "esc", "tap:#helpme", "look"]
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    opened, twice, esc, tapped, _ = seen["walked"]
    assert (opened["hash"], opened["open"], opened["title"]) == (
        help,
        True,
        "Every term on the page",
    )
    assert twice["hash"] == help and twice["back"] == "", "a second ? opens no second glossary"
    assert (esc["hash"], esc["open"]) == (route, False)
    assert (tapped["hash"], tapped["open"]) == (help, True)


def test_a_link_to_the_glossary_opens_it_cold_over_every_project(scene, tmp_path):
    lineup(scene, TODAY)
    seen = look(scene, tmp_path, route="#/help", walk=["look"], at=4500, budget=12000)
    assert seen["errors"] == []
    (first,) = seen["walked"]
    assert (first["hash"], first["open"], first["title"]) == (
        "#/help",
        True,
        "Every term on the page",
    )
    assert first["crumbs"] == [["All", "#/"], ["Every term on the page", "#/help"]]
    assert "Step 2 of 11: a crewmate thread has the task" in first["said"], "notes come cold too"
    assert "Needs you What only you can move" in first["said"]
    assert seen["board"]["shown"], "the glossary is over the board of every project"


AXE = REPO / "features" / "jbus" / "tests" / "fixtures" / "jbus-view"


AXE = (AXE / "axe.min.js").read_text() + "\n" + (AXE / "axe-run.js").read_text()


def every_kind(scene):
    """A day with something of each kind on it: today's line, two projects beside it, every
    role of thread at work, and three gates to answer."""
    lineup(scene, TODAY)
    stacked(scene)
    a_day_of_threads(scene)
    gated(scene)


def a_day(scene, day):
    """The scene of a day, and how long the page runs before axe does. `busy` has every
    kind. `stopped` has a jbus whose timer is not active, so half the page does not change.
    `gone` has a server that stopped answering after its first answer."""
    if day == "busy":
        every_kind(scene)
    if day == "stopped":
        scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    return {"at": 40000, "budget": 100000, "dark_after": 1} if day == "gone" else {"at": 3000}


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    ("route", "day", "screen"),
    [
        ("#/", "busy", DESK),
        ("#/demo", "busy", DESK),
        ("#/help", "busy", DESK),
        ("#/no-such-pot", "busy", DESK),
        ("#/", "stopped", DESK),
        ("#/demo", "stopped", DESK),
        ("#/", "gone", DESK),
        ("#/demo", "gone", DESK),
        ("#/triage", "busy", DESK),
        ("#/", "busy", PHONE),
        ("#/demo", "busy", PHONE),
        ("#/help", "busy", PHONE),
        ("#/triage", "busy", PHONE),
        ("#/no-such-pot", "busy", PHONE),
    ],
)
def test_axe_finds_no_wcag_22_aa_failure_in_any_view_or_drawer(
    scene, tmp_path, route, day, screen, theme
):
    """axe runs in the page over the view, then over every drawer the view or a drawer
    opens, and finds no failure of WCAG 2.2 at level A or AA, and nothing else it calls serious.
    Each route runs at a desk, 1440 wide, and on a phone, 390 wide. Each thing
    that takes the focus draws a ring when it has it."""
    when = {"budget": 60000, "screen": screen} | a_day(scene, day)
    seen = look(scene, tmp_path, route=route, fragment=f"theme={theme}", script=AXE, **when)
    assert seen["theme"] == theme
    assert seen["errors"] == []
    assert seen["violations"] == []
    assert seen["rings"] == []
    if (route, day) == ("#/demo", "busy"):
        kinds = {where.split(":")[0] for where in seen["looked"]}
        assert {"task", "gate", "you", "thread"} <= kinds


@pytest.mark.parametrize("route", ["#/", "#/demo"])
def test_the_first_tab_stop_is_a_skip_link_that_shows_when_focused_and_lands_on_the_view(
    scene, tmp_path, route
):
    every_kind(scene)
    seen = look(scene, tmp_path, route=route, script=AXE, at=3000, budget=60000)
    assert seen["skip"] == {
        "cls": "skip",
        "text": "Skip to the view",
        "href": "#main",
        "seen": True,
    }
    walk = ["tap:.skip", "look"]
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    tapped, _ = seen["walked"]
    assert (tapped["hash"], tapped["open"], tapped["focus"]) == (route, False, "main")


def test_g_a_goes_to_every_project_and_g_p_to_each_next_one_in_turn(scene, tmp_path):
    every_kind(scene)
    walk = ["key:g:", "key:p:", "key:g:", "key:p:", "key:g:", "key:p:", "key:g:", "key:p:"]
    walk += ["key:g:", "key:a:", "key:p:", "key:a:", "key:?:", "key:g:", "key:a:", "look"]
    seen = look(scene, tmp_path, route="#/demo", walk=walk, at=4000 + 500 * len(walk), budget=20000)
    assert seen["errors"] == []
    hashes = [step["hash"] for step in seen["walked"]]
    assert hashes[1::2][:4] == ["#/larder", "#/pantry", "#/demo", "#/larder"]
    assert hashes[9] == "#/", "g a is All"
    assert hashes[11] == "#/", "p or a alone, with no g before it, does nothing"
    assert seen["walked"][12]["open"] and hashes[12] == "#/help"
    assert hashes[14] == "#/" and not seen["walked"][14]["open"], "g a from a drawer is All"


def test_no_key_fires_while_typing_in_a_field_and_esc_there_leaves_it_first(scene, tmp_path):
    number = gated(scene)[1]
    lineup(scene, TODAY)
    field = "#gwords"
    walk = [f"open:gate:{number}", f"key:g:{field}", f"key:a:{field}", f"key:g:{field}"]
    walk += [f"key:p:{field}", f"key:?:{field}", f"key:Escape:{field}", "esc"]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=16000)
    assert seen["errors"] == []
    gate = f"#/demo/gate/{number}"
    steps = seen["walked"]
    assert [step["hash"] for step in steps[:7]] == [gate] * 7
    assert all(step["open"] for step in steps[:7])
    assert steps[5]["title"] == steps[0]["title"], "? in a field opens no glossary"
    assert steps[6]["focus"] != "gwords", "the first Esc leaves the field and keeps the drawer"
    assert (steps[7]["hash"], steps[7]["open"]) == ("#/demo", False)


def test_a_tick_is_no_field_so_esc_on_it_goes_back_and_g_a_goes_to_every_project(scene, tmp_path):
    gated(scene)
    lineup(scene, TODAY)
    tick = "#dw [data-tick]"
    walk = ["open:you:gate", f"key:Escape:{tick}", "open:you:gate", f"key:g:{tick}", "key:a:"]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=14000)
    assert seen["errors"] == []
    opened, esc, _, _, keyed = seen["walked"]
    assert (opened["hash"], opened["open"]) == ("#/demo/you/gate", True)
    assert (esc["hash"], esc["open"]) == ("#/demo", False)
    assert (keyed["hash"], keyed["open"]) == ("#/", False)
