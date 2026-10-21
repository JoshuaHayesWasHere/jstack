"""The first screen of a project and the overview of every project: their words, the
header, the sidebar and the rows."""

import json
import re

import pytest

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
from view.scene import a_noticed, said_by_him, stacked

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


EVERY = 250


SHELL = 30


NEEDS = 220


MIDDLE = (900, 900)


def test_the_first_screen_of_a_project_of_todays_size_is_no_more_than_150_words(scene, tmp_path):
    """The screen is a desk's, as high as the Needs you queue, `NEEDS`, here with the four rows
    of the scene: In progress, with a row for each of the 28 open tasks, starts below it."""
    open_rows = lineup(scene, TODAY)
    assert len(open_rows) == 28
    screen = (DESK[0], DESK[1] + NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    opened = clean(seen, screen)
    assert seen["font"] == 18
    assert seen["words"] <= WORDS, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert len([row for row in seen["prog"] if row["slug"] in open_rows]) == 28
    assert set(seen["first"]) <= opened
    assert {f"task:{slug}" for slug in open_rows} <= opened
    assert len(opened) >= 28 + 6


def test_the_overview_of_a_day_of_todays_size_is_no_more_than_250_words(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert [row["project"] for row in seen["stack"]["rows"]] == ["demo", "larder", "pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert all(row["seen"] for row in seen["stack"]["rows"])


def test_a_bare_link_shows_every_project_once_from_one_request_a_poll(scene, tmp_path):
    """The machine as one word, one Needs you queue across the projects, oldest first, and a
    row for each project: a name, a dot, what is broken, and two counts. The page asks
    `/stack.json` and nothing
    else, once a poll, and a poll that changed nothing draws nothing again."""
    stacked(scene)
    seen = look(scene, tmp_path, route="#/", at=33000, budget=40000)
    assert clean(seen) == set()
    stack = seen["stack"]
    assert (stack["shown"], stack["title"], stack["none"]) == (True, "All projects", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    needs = seen["needs"]
    assert needs["head"] == "4 Needs you"
    assert [(one["key"], one["what"], one["acts"][0]["text"]) for one in needs["now"]] == [
        ("demo/row:jam-lid", "which lid?", "Fix brief"),
        ("pantry/row:fig-tart", "which tin?", "Fix brief"),
        ("demo/#14", "Pull request #14", "Review merge"),
        ("demo/approve:tea-kettle", "tea-kettle", "Approve launch"),
    ]
    assert [one["acts"][0]["href"] for one in needs["now"]] == [
        "#/demo/you/row/jam-lid",
        "#/pantry/you/row/fig-tart",
        "#/demo/you/hold/14",
        "#/demo/you/approve/tea-kettle",
    ]
    assert [one["meta"] for one in needs["now"]] == [
        "demo · waiting 50m",
        "pantry · waiting 40m",
        "demo · waiting 12m · merge to main",
        "demo · new · unblocks tea-cups",
    ]
    assert [(one["what"], one["acts"][0]["text"]) for one in needs["soon"]] == [
        ("tea or coffee?", "Answer")
    ]
    assert needs["filled"] == 0
    assert [row["project"] for row in stack["rows"]] == ["demo", "larder", "pantry"]
    assert all(row["seen"] for row in stack["rows"])
    assert [(row["name"], row["counts"]) for row in stack["rows"]] == [
        ("demo", ["9 open", "1 merged today"]),
        ("larder", ["0 open", "0 merged today"]),
        ("pantry", ["2 open", "1 merged today"]),
    ]
    assert stack["rows"][0]["why"] == "" and stack["rows"][1]["why"].startswith("CI not read")
    assert [row["href"] for row in stack["rows"]] == ["#/demo", "#/larder", "#/pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    polls = [asked for asked in seen["asked"] if asked not in ("/", "/favicon.ico", "/font.woff2")]
    assert len(polls) == 3 and set(polls) == {"/stack.json"}
    drawn = [change["at"] for change in seen["changes"] if change["part"].startswith("rows:")]
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
    """With a top-level webhook that holds events, nothing is wider than the screen."""
    lineup(scene, TODAY)
    sidebar(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["demo"] |= {"outbox": 12, "failed_wakes": 6}
    status["projects"]["demo"]["top_level"] = {"outbox": 10, "failed_wakes": 3, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)
    seen = look(scene, tmp_path, route=route, screen=screen)
    clean(seen, screen)
    assert seen["cut"] == []


def test_a_project_page_asks_its_state_each_poll_and_every_project_once_a_minute(scene, tmp_path):
    """The switcher names every project, so a project's page asks `/stack.json` too: once when
    it opens and then once a minute, beside its own `/state.json` each poll."""
    stacked(scene)
    seen = look(scene, tmp_path, at=63000, budget=70000)
    asked = [one.partition("?")[0] for one in seen["asked"]]
    assert (asked.count("/state.json"), asked.count("/stack.json")) == (5, 2)
    assert [one[0] for one in seen["header"]["pick"]] == ["", "demo", "larder", "pantry"]


def test_a_row_opens_its_project_and_an_old_link_opens_it_too(scene, tmp_path):
    stacked(scene)
    seen = look(
        scene,
        tmp_path,
        route="#/",
        tap='#rows a[href="#/pantry"]',
        at=6000,
        budget=9000,
    )
    clean(seen)
    assert seen["hash"] == "#/pantry"
    assert (seen["stack"]["shown"], seen["needs"]["head"]) == (False, "1 Needs you")
    assert {row["slug"] for row in seen["prog"]} == {"fig-jam", "fig-tart"}
    seen = look(scene, tmp_path, route="?project=pantry")
    clean(seen)
    assert (seen["hash"], seen["needs"]["head"]) == ("#/pantry", "1 Needs you")
    assert [asked.partition("?")[0] for asked in seen["asked"]].count("/stack.json") == 1


def test_a_link_to_no_project_draws_the_machine_with_its_own_word_on_jbus(scene, tmp_path):
    """No project's read is in hand there, so the machine is the one /stack.json read, and
    whether jbus passes is its word, whatever the page drew before."""
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/hydra")
    assert seen["errors"] == []
    assert seen["header"]["machine"]["text"] == "jbus stopped"


def test_a_link_to_a_project_that_is_not_there_says_so_and_reads_no_retired_one(scene, tmp_path):
    stacked(scene)
    seen = look(scene, tmp_path, route="#/hydra")
    assert seen["errors"] == [] and "gone" not in seen["body"]
    assert seen["stack"]["none"] == (
        "No project named hydra jbus looks after no project of that name: a retired project "
        "is not shown. Every project"
    )
    assert seen["first"] == []
    seen = look(scene, tmp_path, route="#/")
    assert "hydra" not in json.dumps(seen["stack"])
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


def test_a_stopped_jbus_makes_every_project_row_red_with_its_reason(scene, tmp_path):
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    rows = seen["stack"]["rows"]
    assert [row["name"] for row in rows] == ["demo", "larder", "pantry"]
    assert all(row["why"].startswith("jbus stopped") and "bad" in row["dot"] for row in rows)


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
    """The drawer of what waits on you heads each kind with its label, in the page's order; the
    threads drawer counts each role in its words; Help says what each role is, on a project
    and on the page of every project."""
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
