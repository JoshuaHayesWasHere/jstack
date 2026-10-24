"""The first screen of a project and the overview of every project: their words, the
header, the sidebar, and the overview's map of projects."""

import json
import re

import pytest

from jbus import alert
from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    TODAY,
    WORDS,
    clean,
    lineup,
    look,
    walked,
)
from view.scene import Served, a_noticed, ago, iso, said_by_him, stacked

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


EVERY = 250


SHELL = 30


NEEDS = 220


MIDDLE = (900, 900)


def test_the_first_screen_of_a_project_of_todays_size_is_no_more_than_150_words(scene, tmp_path):
    """The test uses a desk's screen and makes it as high as the Needs you queue, `NEEDS`.
    Here that queue has the four rows of the scene. The In progress section starts below that
    queue, with a row for each of the other 24 open tasks."""
    open_rows = lineup(scene, TODAY)
    assert len(open_rows) == 28
    screen = (DESK[0], DESK[1] + NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    opened = clean(seen, screen)
    assert seen["font"] == 18
    assert seen["words"] <= WORDS, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert len([row for row in seen["prog"] if row["slug"] in open_rows]) == 24
    assert set(seen["first"]) <= opened
    assert {row["open"] for row in seen["prog"]} <= opened
    assert len(opened) >= 24 + 6


def test_a_task_in_needs_you_is_written_once_on_the_first_screen_of_a_project(scene, tmp_path):
    """A row of Needs you is the task's one row on the page: the row writes the task's slug,
    and In progress does not draw the task again. `state.json` says which task each need is
    about, and the screen is counted for each: once, in its row of Needs you."""
    open_rows = lineup(scene, TODAY)
    served = Served(scene)
    try:
        state = served.json(f"/state.json?project={scene.name}")
    finally:
        served.close()
    asked = sorted(one["slug"] for one in state["needs"] if one["slug"] in open_rows)
    assert len(asked) == 4
    screen = (DESK[0], DESK[1] + NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    clean(seen, screen)
    rows = [" ".join([one["what"], *one["why"], one["meta"]]) for one in seen["needs"]["now"]]
    assert len([one for one in seen["needs"]["now"] if one["seen"]]) == 4
    written = [slug for line in rows for slug in re.findall(r"[a-z0-9][a-z0-9._-]*", line)]
    drawn = [row["slug"] for row in seen["prog"] if row["seen"]]
    assert {slug: written.count(slug) + drawn.count(slug) for slug in asked} == dict.fromkeys(
        asked, 1
    )
    assert sorted({slug for slug in drawn if drawn.count(slug) > 1}) == []


def test_the_overview_of_a_day_of_todays_size_is_no_more_than_250_words(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert [row["project"] for row in seen["stack"]["rows"]] == ["larder", "demo", "pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert all(row["seen"] for row in seen["stack"]["rows"])


def test_a_bare_link_shows_every_project_once_from_one_request_a_poll(scene, tmp_path):
    """The overview has the machine as one word, one bar of what waits on the user across the
    projects, and a card for each project. larder's CI could not be read, so it is first, and
    demo and pantry have what waits on the user. The bar draws no list of what waits: it opens
    the triage tab. The page asks `/stack.json` and nothing else, once a poll. After a poll
    that changed nothing, the page draws nothing again."""
    stacked(scene)
    seen = look(scene, tmp_path, route="#/", at=33000, budget=40000)
    assert clean(seen) == set()
    stack = seen["stack"]
    assert (stack["shown"], stack["title"], stack["none"]) == (True, "All projects", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    needs = seen["needs"]
    assert needs["head"] == "4 wait on you oldest 50m · 1 more on default"
    assert (needs["now"], needs["soon"], needs["filled"]) == ([], [], 1)
    assert [row["project"] for row in stack["rows"]] == ["larder", "demo", "pantry"]
    assert all(row["seen"] and not row["quiet"] for row in stack["rows"])
    assert [(row["name"], row["counts"]) for row in stack["rows"]] == [
        ("larder", "0 open"),
        ("demo", "9 open · 3 wait on you · 1 on default"),
        ("pantry", "2 open · 1 waits on you"),
    ]
    assert stack["rows"][0]["why"] == "CI could not be read, GitHub cannot be read"
    assert stack["rows"][1]["why"] == stack["rows"][2]["why"] == ""
    assert [row["href"] for row in stack["rows"]] == ["#/larder", "#/demo", "#/pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    polls = [asked for asked in seen["asked"] if asked not in ("/", "/favicon.ico", "/font.woff2")]
    assert len(polls) == 9 and set(polls) == {"/stack.json"}
    drawn = [change["at"] for change in seen["changes"] if change["part"].startswith("map-c:")]
    assert drawn and [one for one in seen["changes"] if one["at"] > max(drawn) + 1000] == []
    assert seen["marked"] == 1


def test_the_header_says_the_name_where_you_are_and_the_time_of_the_last_read(scene, tmp_path):
    stacked(scene)
    one = look(scene, tmp_path)
    every = look(scene, tmp_path, route="#/")
    for seen in (one, every):
        clean(seen)
        assert seen["header"]["brand"] == "jbus view"
        assert re.fullmatch(r"Updated \d\d:\d\d · live", seen["header"]["read"]), seen["header"]
        assert seen["header"]["box"][:3] == [0, 0, DESK[0]]
    assert one["header"]["crumbs"] == [["All", "#/", ""], ["demo", "#/demo", "page"]]
    assert every["header"]["crumbs"] == [["All projects", "#/", "page"]]


def sidebar(scene):
    """The scene of the sidebar: three projects, and larder's bus with wakes that failed."""
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["larder"] = {"outbox": 0, "failed_wakes": 2, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)


@pytest.mark.parametrize("screen", [DESK, MIDDLE, PHONE])
@pytest.mark.parametrize("route", ["#/", "#/demo"])
def test_no_view_scrolls_sideways(scene, tmp_path, screen, route):
    """With a top-level webhook that has events, nothing is wider than the screen."""
    lineup(scene, TODAY)
    sidebar(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["demo"] |= {"outbox": 12, "failed_wakes": 6}
    status["projects"]["demo"]["top_level"] = {"outbox": 10, "failed_wakes": 3, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)
    seen = look(scene, tmp_path, route=route, screen=screen)
    clean(seen, screen)
    assert seen["cut"] == []


def test_a_project_page_asks_one_thing_each_poll_and_every_project_once_a_minute(scene, tmp_path):
    """The page polls every 5 seconds and sends one request for each poll. The switcher names
    every project, so a project's page asks `/stack.json` too: once beside its first read, and
    then once a minute in place of its own `/state.json`."""
    stacked(scene)
    seen = look(scene, tmp_path, at=63000, budget=70000)
    asked = [one.partition("?")[0] for one in seen["asked"]]
    assert (asked.count("/state.json"), asked.count("/stack.json")) == (14, 2)
    assert [one[0] for one in seen["header"]["pick"]] == ["", "demo", "larder", "pantry"]


def test_a_row_opens_its_project_and_an_old_link_opens_it_too(scene, tmp_path):
    stacked(scene)
    seen = look(
        scene,
        tmp_path,
        route="#/",
        tap='#stack a[href="#/pantry"]',
        at=6000,
        budget=9000,
    )
    clean(seen)
    assert seen["hash"] == "#/pantry"
    assert (seen["stack"]["shown"], seen["needs"]["head"]) == (False, "1 Needs you")
    assert {row["slug"] for row in seen["prog"]} == {"fig-jam"}, "fig-tart is in Needs you"
    seen = look(scene, tmp_path, route="?project=pantry")
    clean(seen)
    assert (seen["hash"], seen["needs"]["head"]) == ("#/pantry", "1 Needs you")
    assert [asked.partition("?")[0] for asked in seen["asked"]].count("/stack.json") == 1


def test_a_link_to_no_project_draws_the_machine_with_its_own_word_on_jbus(scene, tmp_path):
    """On that route the page reads no project, so all it knows of the machine comes from
    its one read of /stack.json. That read alone says whether jbus passes, whatever the page
    drew before."""
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/attic")
    assert seen["errors"] == []
    assert seen["header"]["machine"]["text"] == "jbus stopped"


def test_a_link_to_a_project_that_is_not_there_says_so_and_reads_no_retired_one(scene, tmp_path):
    stacked(scene)
    seen = look(scene, tmp_path, route="#/attic")
    assert seen["errors"] == [] and "gone" not in seen["body"]
    assert seen["stack"]["none"] == (
        "No project named attic jbus looks after no project of that name: a retired project "
        "is not shown. Every project"
    )
    assert seen["first"] == []
    seen = look(scene, tmp_path, route="#/")
    assert "attic" not in json.dumps(seen["stack"])
    seen = look(scene, tmp_path, route="#/%E0")
    assert seen["errors"] == [] and seen["stack"]["none"].startswith("No project named %E0 ")


def test_the_new_noticed_lines_are_a_count_beside_the_queue_that_opens_their_panel(scene, tmp_path):
    lineup(scene, TODAY)
    a_noticed(
        scene,
        *((slug, "new", 5 + at, {}) for at, slug in enumerate(("tea-kettle", "jam-kettle"))),
        ("oat-kettle", "dropped", 400, {"why": "from before the list", "by": "jbus"}),
    )
    seen = look(scene, tmp_path)
    opened = clean(seen)
    tile = seen["needs"]["extra"][-1]
    assert (tile["text"], tile["open"]) == ("2 noticed, not counted", "noticed")
    assert not any("noticed" in one["what"] for one in seen["needs"]["now"] + seen["needs"]["soon"])
    assert "noticed" in opened
    drawer = {one["target"]: one for one in seen["opened"]}["noticed"]
    assert drawer["title"] == "2 new lines of 3, newest first"
    assert seen["words"] <= WORDS, seen["words"]

    a_noticed(scene, ("oat-kettle", "dropped", 400, {"why": "from before the list"}))
    seen = look(scene, tmp_path)
    assert seen["needs"]["extra"] == []
    assert seen["words"] <= WORDS, seen["words"]


def test_a_stopped_jbus_is_one_line_over_the_map_of_every_project(scene, tmp_path):
    """A quiet project is only as quiet as the last pass saw it, so a stopped jbus says so
    once, over the map, beside the banner and the header's word."""
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert seen["stack"]["machine"] == ["jbus stopped, so this is as its last pass left it"]
    assert seen["header"]["machine"]["text"] == "jbus stopped"
    assert seen["banner"].startswith("jbus has not passed")
    assert {row["name"] for row in seen["stack"]["rows"]} == {"demo", "larder", "pantry"}


def test_passes_that_fail_and_a_red_main_are_on_the_first_screen(scene, tmp_path):
    """While passes raise, the header counts them where it said the last pass, and a red main
    names its tip on its project's card, with how long ago, as every wrong line does. Nothing
    waits on the user but a gate that takes its default, so pantry is quiet."""
    stacked(scene)
    for project in ("demo", "pantry"):
        scene.write("waiting-on-user.json", [], scene.state_dir / project)
        state = scene.state_dir / project
        work = json.loads((state / "work.json").read_text())
        held = {one.get("slug") for one in work["work"] if one.get("who") == "user"}
        work["work"] = [one for one in work["work"] if one.get("slug") not in held]
        rows = json.loads((state / "queue.json").read_text())
        scene.write("queue.json", [one for one in rows if one["slug"] not in held], state)
        scene.write("work.json", work, state)
    streak = {"key": alert.PASS, "count": 3, "since": iso(ago(minutes=3)), "alerted": True}
    scene.write("streaks.json", {alert.PASS: streak}, scene.state_dir)
    red = "badc0de" + "1" * 33
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": red, "check": "failed"})
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert seen["needs"]["head"] == "Nothing waits on you · 3 passes failed · 1 on default"
    assert seen["header"]["machine"]["text"] == "3 passes failed"
    rows = {row["name"]: (row["why"], row["quiet"]) for row in seen["stack"]["rows"]}
    assert rows == {
        "demo": ("main red at badc0de 12m", False),
        "larder": ("CI could not be read, GitHub cannot be read", False),
        "pantry": ("", True),
    }


KIND_HEADINGS = (
    "Tasks at a gate",
    "Left over by tasks that ended",
    "Pull requests jmerge holds for your word",
    "Rows to approve",
    "Open gates",
)
ROLE_WORDS = (
    "The thread that does a task's one brief, in its own worktree",
    "A thread that researches one request, read-only",
    "A fresh thread that reads a task's pull request",
    "The thread that plans the project's work",
    "A thread whose title names no role",
)


def test_the_drawers_name_the_kinds_and_roles_as_state_json_gives_them(scene, tmp_path):
    """The drawer of what waits on you heads each kind with its label, in the page's order.
    The threads drawer shows a count for each role, in the drawer's own words. Help says what
    each role is, on a project and on the page of every project."""
    said_by_him(scene)
    you, threads, help_ = walked(
        scene, tmp_path, "#/demo/you", ["look", "hash:#/demo/threads/scout", "hash:#/demo/help"]
    )
    places = [you["said"].lower().find(heading.lower()) for heading in KIND_HEADINGS]
    assert -1 not in places and places == sorted(places), you["said"]
    assert threads["title"] == "0 scouts out"
    assert "all 0 crews 0 scouts 0 reviewers 0" in threads["said"]
    assert all(word in help_["said"] for word in ROLE_WORDS), help_["said"]
    (overview,) = walked(scene, tmp_path, "#/help", ["look"])
    assert all(word in overview["said"] for word in ROLE_WORDS), overview["said"]
