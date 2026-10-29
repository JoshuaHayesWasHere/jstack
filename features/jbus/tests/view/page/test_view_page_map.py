"""The homes map, `#/`, in the browser: a card for each project with something wrong or
something for the user, its root home first and each child home as a line under it, and every
other project as one line in a group of the quiet ones. A bar above says how many things wait
on the user and opens the triage tab.

The scene is the busy day of the budgets (`test_view_page_budgets.busy`): demo has the child
homes `ui` and `docs` (`browser.child_homes`), a failed CI run on the root and a hung crewmate
and a stalled row in `ui`.
"""

import json
from datetime import timedelta

import pytest

from view.page import browser
from view.page.browser import BROWSES, DESK, LAUNCH, MAP, PATIENCE, PHONE, clean, look
from view.page.test_view_page_budgets import SCENES
from view.scene import NOW, Served, out

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def mapped(scene, tmp_path, name="busy", screen=DESK, **how):
    seen, stack = browser.mapped(scene, tmp_path, SCENES[name], screen=screen, **how)
    assert seen["errors"] == []
    return seen, stack


def test_a_card_for_each_project_that_has_something_the_root_first_and_a_line_per_child_home(
    scene, tmp_path
):
    """demo has what is wrong, so it comes first. Its root is the card's first line, with the
    project's last act and its own, then each child home by name: `docs` with nothing open and
    no act kept, and `ui`, whose turn ended with its row out, and how old the home is. That
    row's stall and the crewmate that hung are the `ui` home's to fix, so they are drawn on
    their rows and not here. The failed run of CI, which no row owns
    and no root home is listed to fix, is a line under the root. bakery and pantry have
    something that waits on the user and come next."""
    seen, stack = mapped(scene, tmp_path)
    assert [one["project"] for one in seen["cards"]] == ["demo", "bakery", "pantry"]
    demo = seen["cards"][0]
    assert demo["href"] == "#/demo"
    assert "bad" in demo["tone"]
    root, docs, ui = demo["homes"]
    assert (root["home"], docs["home"], ui["home"]) == ("", "docs", "ui")
    assert root["health"] == "Working"
    assert "26 open" in root["text"] and "4 wait on you" in root["text"]
    assert "6 on default" in root["text"]
    assert "project last act " in root["text"] and " ago root " in root["text"]
    assert docs["text"] == "demo › docs 0 open no act kept 2d old"
    assert ui["text"].startswith("demo › ui Idle, work open 1 open")
    assert (ui["flags"], ui["age"]) == ([], "3d old")
    assert demo["wrong"] == ["tea-saucer check failed 30m"]
    bakery = seen["cards"][1]
    assert [one["home"] for one in bakery["homes"]] == [""]
    assert "1 waits on you" in bakery["homes"][0]["text"]
    assert {one["kind"] for one in stack["wrong"]} == {"ci"}


def test_a_project_with_nothing_wrong_and_nothing_for_the_user_is_one_line_among_the_quiet(
    scene, tmp_path
):
    seen, _ = mapped(scene, tmp_path)
    assert seen["quiet"] == [
        {"project": "cellar", "text": "cellar 3 open", "href": "#/cellar"},
        {"project": "dairy", "text": "dairy 2 open", "href": "#/dairy"},
        {"project": "larder", "text": "larder 0 open", "href": "#/larder"},
    ]
    assert seen["machine"] == []


def test_a_home_that_is_not_running_with_work_open_lifts_its_project_out_of_the_quiet(
    scene, tmp_path
):
    """A home whose thread ended while rows of it are open is nothing wrong, but its work
    does not move until somebody starts the home: its project is a card, not a quiet line."""

    def ended(nth, body):
        (cellar,) = [one for one in body["projects"] if one["name"] == "cellar"]
        cellar["homes"][0]["health"] = "ended"
        return body

    seen, _ = mapped(scene, tmp_path, alter=ended)
    assert "cellar" not in [one["project"] for one in seen["quiet"]]
    (cellar,) = [one for one in seen["cards"] if one["project"] == "cellar"]
    assert cellar["tone"] == "card op"
    assert cellar["homes"][0]["health"] == "Idle, work open"


def test_the_bar_counts_what_waits_on_the_user_and_opens_the_triage_tab(scene, tmp_path):
    """The bar is one line: no list of what waits is drawn on the map."""
    seen, stack = mapped(scene, tmp_path)
    assert seen["bar"]["count"] == str(len(stack["needs"])) == "6"
    assert seen["bar"]["text"].startswith("6 wait on you")
    assert "6 more on default" in seen["bar"]["text"]
    assert (seen["bar"]["go"], seen["bar"]["list"]) == ("#/triage", False)
    (tmp_path / "tapped").mkdir()
    how = {"tap": "#needs .go", "at": 5000, "budget": 8000}
    tapped, _ = browser.mapped(scene, tmp_path / "tapped", lambda scene: None, **how)
    assert tapped["hash"] == "#/triage"


def test_a_card_opens_its_projects_root_home_page_with_a_group_per_child_home(scene, tmp_path):
    seen, _ = mapped(scene, tmp_path, tap='#map-c [data-key="demo"] .cn', at=6000, budget=9000)
    assert seen["hash"] == "#/demo", seen
    assert [head.split(" ")[0] for head in seen["groups"]] == ["root", "docs", "ui"]


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_with_nothing_wrong_a_card_is_only_for_what_waits_and_the_rest_is_quiet(
    scene, tmp_path, screen
):
    """The calm scene: nothing is wrong, so no card, line or flag says so. A card is only for
    a project with something for the user, and every other project is quiet."""
    seen, stack = mapped(scene, tmp_path, "calm", screen=screen)
    assert stack["wrong"] == []
    asks = {one["project"] for one in stack["needs"] + stack["proceeds"]}
    assert [one["project"] for one in seen["cards"]] == sorted(asks) == ["demo", "pantry"]
    assert [one["wrong"] for one in seen["cards"]] == [[], []]
    assert seen["machine"] == [] and seen["wrong"] == []
    quiet = sorted(one["name"] for one in stack["projects"] if one["name"] not in asks)
    assert [one["project"] for one in seen["quiet"]] == quiet


def test_on_a_phone_every_target_of_the_map_takes_a_thumb_and_nothing_is_cut(scene, tmp_path):
    SCENES["busy"](scene)
    seen = look(scene, tmp_path, route="#/homes", screen=PHONE)
    clean(seen, PHONE)
    assert (seen["small"], seen["cut"]) == ([], [])


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_no_panel_card_is_drawn_over_the_homes_map(scene, tmp_path, screen):
    """The panels' parts of the desk, the glance band and its tiles, what needs you, what slows
    us, on a phone a line for every home, what landed since the user looked, merges per day and
    the nearest milestone, are the overview's: `#/` draws each of them, and `#/homes` draws none,
    only its map and the matrix above it."""
    SCENES["busy"](scene)
    looked = f"window.__looked = {int((NOW - timedelta(hours=2)).timestamp() * 1000)};"
    served = Served(scene)
    try:
        seen = {
            route: look(
                scene, tmp_path, route=route, script=looked + MAP, screen=screen, port=served.port
            )
            for route in ("#/", "#/homes")
        }
    finally:
        served.close()
    assert [one["errors"] for one in seen.values()] == [[], []]
    drawn = ["glance", "milestones", "since", "slow", "throughput", "you"]
    drawn += ["pipeline"] if screen == PHONE else []
    assert sorted(seen["#/"]["panels"]) == sorted(drawn)
    assert seen["#/homes"]["map"] and seen["#/homes"]["cards"]
    assert seen["#/homes"]["panels"] == []


def troubled_homes(scene):
    """The busy day, with the root's thread waiting on a request, `ui`'s hung for 40 minutes
    and `docs`'s quiet for 12."""
    SCENES["busy"](scene)
    record = json.loads((scene.state_dir / "pass.json").read_text())
    listed = record["projects"][scene.name]["threads"]
    listed[:] = [one for one in listed if one["role"] != "home"] + [
        out("home: demo", "waiting", minutes=3),
        out("home: demo ui", "hung", minutes=40, id="mcp:ui"),
        out("home: demo docs", "quiet", minutes=12, id="mcp:docs"),
    ]
    scene.write("pass.json", record, scene.state_dir)


def test_a_home_whose_thread_hung_or_went_quiet_says_so_with_its_age_as_a_wrong_fact(
    scene, tmp_path
):
    """A home's own thread that hung or went quiet is its health word, with how long since it
    wrote, and that word is the line of its wrong fact: no other line repeats it. The screen is
    tall enough to show the map's lines under the matrix."""
    seen, stack = browser.mapped(scene, tmp_path, troubled_homes, screen=(DESK[0], 1800))
    assert seen["errors"] == []
    root, docs, ui = seen["cards"][0]["homes"]
    assert (root["health"], docs["health"], ui["health"]) == (
        "Waiting on you",
        "Quiet 12m",
        "Hung 40m",
    )
    own = {
        f"{one['kind']}/{one['subj']}/{one['cause']}"
        for one in stack["wrong"]
        if one["subj"].startswith("home: ")
    }
    assert len(own) == 2 and own <= set(seen["wrong"])
    assert not any(line.startswith("home: ") for line in seen["cards"][0]["wrong"])
