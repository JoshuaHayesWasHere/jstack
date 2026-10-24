"""The homes map, `#/`, in the browser: a card for each project with something wrong or
something for the user, its root home first and each child home as a line under it, and every
other project as one line in a group of the quiet ones. A bar above says how many things wait
on the user and opens the triage tab.

The scene is the busy day of the budgets (`test_view_page_budgets.busy`): demo has the child
homes `ui` and `docs` (`browser.child_homes`), a failed CI run on the root and a hung crewmate
and a stalled row in `ui`.
"""

import json

import pytest

from view.page import browser
from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, clean, look
from view.page.test_view_page_budgets import SCENES
from view.scene import out

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def mapped(scene, tmp_path, name="busy", screen=DESK, **how):
    seen, stack = browser.mapped(scene, tmp_path, SCENES[name], screen=screen, **how)
    assert seen["errors"] == []
    return seen, stack


def test_a_card_for_each_project_that_has_something_the_root_first_and_a_line_per_child_home(
    scene, tmp_path
):
    """demo has what is wrong, so it comes first. Its root is the card's first line, then each
    child home by name: `docs` with nothing open, and `ui`, whose turn ended with its row out,
    that row's stall as a flag, and how old the home is. The crewmate that hung is a line under
    `ui`, the failed run of CI one under the root. bakery and pantry have something that waits
    on the user and come next."""
    seen, stack = mapped(scene, tmp_path)
    assert [one["project"] for one in seen["cards"]] == ["demo", "bakery", "pantry"]
    demo = seen["cards"][0]
    assert demo["href"] == "#/demo"
    assert "bad" in demo["tone"]
    root, docs, ui = demo["homes"]
    assert (root["home"], docs["home"], ui["home"]) == ("", "docs", "ui")
    assert root["health"] == "moving"
    assert "27 open" in root["text"] and "4 wait on you" in root["text"]
    assert "6 on default" in root["text"]
    assert docs["text"] == "demo › docs 0 open 2d old"
    assert ui["text"].startswith("demo › ui ended, work out 1 open")
    assert (ui["flags"], ui["age"]) == (["oat-saucer stalled"], "3d old")
    assert demo["wrong"] == [
        "tea-saucer check failed 30m",
        "crew: jam-jar its turn has written nothing, and may be hung, and 2 runs wait 25m",
    ]
    bakery = seen["cards"][1]
    assert [one["home"] for one in bakery["homes"]] == [""]
    assert "1 waits on you" in bakery["homes"][0]["text"]
    assert {one["kind"] for one in stack["wrong"]} == {"ci", "thread", "stall"}


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
    seen = look(scene, tmp_path, route="#/", screen=PHONE)
    clean(seen, PHONE)
    assert (seen["small"], seen["cut"]) == ([], [])


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
    wrote, and that word is the line of its wrong fact: no other line repeats it."""
    seen, stack = browser.mapped(scene, tmp_path, troubled_homes)
    assert seen["errors"] == []
    root, docs, ui = seen["cards"][0]["homes"]
    assert (root["health"], docs["health"], ui["health"]) == (
        "waits on a request",
        "quiet 12m",
        "hung 40m",
    )
    own = {
        f"{one['kind']}/{one['subj']}/{one['cause']}"
        for one in stack["wrong"]
        if one["subj"].startswith("home: ")
    }
    assert len(own) == 2 and own <= set(seen["wrong"])
    assert not any(line.startswith("home: ") for line in seen["cards"][0]["wrong"])
