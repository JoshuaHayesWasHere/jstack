"""The first screen of a project and the overview of every project: their words, the
header, the sidebar, and the overview's map of projects."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jbus import alert, queue
from view.days import DAYS, TODAY, lineup
from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    WORDS,
    clean,
    look,
    walked,
)
from view.scene import REQUEST, Served, ago, iso, item, said_by_him, stacked
from view.scene import row as queued

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


EVERY = 250


SHELL = 30


NEEDS = 220


MIDDLE = (900, 900)


def test_the_first_screen_of_a_project_of_todays_size_is_no_more_than_150_words(scene, tmp_path):
    """The test uses a desk's screen and makes it as high as the Needs you queue, `NEEDS`.
    Here that queue has the four rows of the scene. The In progress section starts below that
    queue, with a row for each of the other 23 open tasks."""
    open_rows = lineup(scene, TODAY)
    assert len(open_rows) == 27
    screen = (DESK[0], DESK[1] + NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    opened = clean(seen, screen)
    assert seen["font"] == 18
    assert seen["words"] <= WORDS, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert len([row for row in seen["prog"] if row["slug"] in open_rows]) == 23
    assert set(seen["first"]) <= opened
    assert {row["open"] for row in seen["prog"]} <= opened
    assert len(opened) >= 23 + 6


def test_a_task_in_needs_you_is_written_once_on_the_first_screen_of_a_project(scene, tmp_path):
    """A row of Needs you is the task's one row on the page: the row writes the task's slug,
    and In progress does not draw the task again. `state.json` says which task each need is
    about. The first 3 needs are shown and the screen writes each of their tasks once, in its
    row. The rest fold under one control that counts them, and In progress draws none of them."""
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
    now = seen["needs"]["now"]
    rows = [" ".join([one["what"], *one["why"], one["meta"]]) for one in now if one["seen"]]
    assert len(rows) == 3
    assert seen["needs"]["fold"] == {"text": f"+{len(now) - 3} more need you", "expanded": "false"}
    written = [slug for line in rows for slug in re.findall(r"[a-z0-9][a-z0-9._-]*", line)]
    drawn = [row["slug"] for row in seen["prog"] if row["seen"]]
    assert all(one["ahead"].startswith("Goes ahead: ") for one in now if one["seen"])
    first = [slug for slug in asked if slug in written]
    assert len(first) == 3
    assert {slug: written.count(slug) + drawn.count(slug) for slug in first} == dict.fromkeys(
        first, 1
    )
    assert [slug for slug in asked if slug in drawn] == []
    assert sorted({slug for slug in drawn if drawn.count(slug) > 1}) == []


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_the_control_under_the_first_3_needs_opens_the_inbox_each_with_its_default_and_action(
    scene, tmp_path, screen
):
    """The first screen shows the first 3 needs, each as its question and the line of what goes
    ahead, and folds the rest under one control. Tapped, it opens the whole inbox: every need is
    shown with what happens if you do nothing and its one action, and on a phone each link of a
    row, its title and its chips, takes a thumb."""
    lineup(scene, TODAY)
    screen = (screen[0], screen[1] + NEEDS)
    walk = ["look", "tap:#nfold [data-fold]", "look"]
    seen = look(scene, tmp_path, screen=screen, walk=walk, at=4000 + 500 * len(walk), budget=20000)
    clean(seen, screen)
    folded, opened = seen["walked"][0], seen["needs"]
    now = opened["now"]
    assert len(now) > 3
    assert opened["fold"] == {"text": "Show the first 3", "expanded": "true"}
    assert all(one["box"][2] > 0 for one in now), "no row is folded"
    assert all(one["ahead"].startswith("If you do nothing: ") for one in now)
    assert all(len([act for act in one["acts"] if act["fill"]]) == 1 for one in now)
    assert folded["changes"] < seen["walked"][1]["changes"]
    if screen[0] == PHONE[0]:
        assert seen["small"] == []


def test_the_inbox_opened_in_one_project_is_folded_in_the_next(scene, tmp_path):
    """Opening the inbox is for the project it was opened in. A route to another project shows
    that project's first screen: each need as its question and the line of what goes ahead."""
    lineup(scene, TODAY)
    stacked(scene)
    screen = (DESK[0], DESK[1] + NEEDS)
    walk = ["tap:#nfold [data-fold]", "hash:#/pantry", "look"]
    seen = look(scene, tmp_path, screen=screen, walk=walk, at=4000 + 500 * len(walk), budget=20000)
    assert seen["errors"] == []
    assert seen["walked"][-1]["hash"] == "#/pantry"
    now = seen["needs"]["now"]
    assert [one["what"] for one in now] == ["which tin?"]
    assert all(one["ahead"].startswith("Goes ahead: ") for one in now)


def test_folding_the_inbox_keeps_an_accept_that_is_counting_on_screen_with_its_undo(
    scene, tmp_path
):
    """An approval started on a row under the first 3 counts 10 seconds before it writes.
    Folding the inbox in that time leaves that row shown, so its Undo stays in reach."""
    lineup(scene, {"yours": 4}, merged=0, gates=0)
    screen = (DESK[0], DESK[1] + NEEDS)
    fold = "tap:#nfold [data-fold]"
    walk = [
        "look",
        fold,
        "tap:#nq > .nr:nth-child(n+4) [data-accept][aria-description]",
        fold,
        "look",
    ]
    seen = look(scene, tmp_path, screen=screen, walk=walk, at=4000 + 500 * len(walk), budget=20000)
    assert seen["errors"] == []
    counting = [one for one in seen["needs"]["now"] if one["acting"]]
    assert len(counting) == 1 and counting[0]["acting"].endswith("Undo")
    assert counting[0]["box"][2] > 0, "the row that counts is not folded away"
    assert seen["needs"]["fold"]["expanded"] == "false"


def test_the_overview_of_a_day_of_todays_size_is_no_more_than_250_words(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/homes")
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
    seen = look(scene, tmp_path, route="#/homes", at=33000, budget=40000)
    assert clean(seen) == set()
    stack = seen["stack"]
    assert (stack["shown"], stack["title"], stack["none"]) == (True, "All projects", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    needs = seen["needs"]
    assert needs["head"] == "4 wait on you oldest 50m · 1 more on default"
    assert (needs["now"], needs["fold"], needs["filled"]) == ([], None, 1)
    assert [row["project"] for row in stack["rows"]] == ["larder", "demo", "pantry"]
    assert all(row["seen"] and not row["quiet"] for row in stack["rows"])
    assert [(row["name"], row["counts"]) for row in stack["rows"]] == [
        ("larder", "0 open"),
        (
            "demo",
            "9 open · 3 wait on you · check: 0 failing, 1 running or queued, 0 passed"
            " · 1 on default",
        ),
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
    every = look(scene, tmp_path, route="#/homes")
    for seen in (one, every):
        clean(seen)
        assert seen["header"]["brand"] == "jbus view"
        assert re.fullmatch(r"Updated \d\d:\d\d · live", seen["header"]["read"]), seen["header"]
        assert seen["header"]["box"][:3] == [0, 0, DESK[0]]
    assert one["header"]["crumbs"] == [["All", "#/", ""], ["demo", "#/demo", "page"]]
    assert every["header"]["crumbs"] == [["All projects", "#/homes", "page"]]


def sidebar(scene):
    """The scene of the sidebar: three projects, and larder's bus with wakes that failed."""
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["larder"] = {"outbox": 0, "failed_wakes": 2, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)


@pytest.mark.parametrize("screen", [DESK, MIDDLE, PHONE])
@pytest.mark.parametrize("route", ["#/", "#/demo"])
def test_no_view_scrolls_sideways(scene, tmp_path, screen, route):
    """With wakes that wait and fail, nothing is wider than the screen."""
    lineup(scene, TODAY)
    sidebar(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["demo"] |= {"outbox": 12, "failed_wakes": 6}
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
        route="#/homes",
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
    seen = look(scene, tmp_path, route="#/homes")
    assert "attic" not in json.dumps(seen["stack"])
    seen = look(scene, tmp_path, route="#/%E0")
    assert seen["errors"] == [] and seen["stack"]["none"].startswith("No project named %E0 ")


def test_a_stopped_jbus_is_one_line_over_the_map_of_every_project(scene, tmp_path):
    """A quiet project is only as quiet as the last pass saw it, so a stopped jbus says so
    once, over the map, beside the banner and the header's word."""
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/homes")
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
    seen = look(scene, tmp_path, route="#/homes")
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


OVERVIEW = (Path(__file__).parent / "overview.js").read_text()


QUESTIONS = {
    "are we stalled, and why": ("glance:band", "slow:rail", "glance:act"),
    "where is all the work, every stage, every home": ("pipeline:matrix", "glance:open"),
    "what needs me right now": ("you:tile", "you:rail"),
    "what is blocking what": ("chains",),
    "how close are we to a milestone": ("milestones:nearest",),
    "how much got done today, or this week": ("glance:merged", "throughput:perday"),
    "what landed since I last looked": ("since:landed",),
    "why are N items sitting in check or review": ("slow:tile", "slow:rail"),
}
"""Each ranked question of `reports/jv-glance/ranking.md`, in its order, and the parts of the desk
overview that answer it. `chains` is the Chains line under the matrix."""


def planned(scene):
    """The T moment with a plan entry, `jv-build`, whose rows are 10 of the day's merged rows and
    4 of its rows in check, so the nearest milestone is 10 of 14."""
    rows = json.loads((scene.state / "queue.json").read_text())
    merged = [one for one in rows if one["status"] == "merged"][:10]
    checked = [one for one in rows if one["status"] == "pr"][:4]
    for one in merged + checked:
        one["entry"] = "jv-build"
    scene.write("queue.json", rows)
    (scene.home / "plan.md").write_text(
        "# demo: plan\n\n## jv-build: the monitoring overview\nStage: planned\n"
    )


def desk(scene, tmp_path, screen=DESK, script=OVERVIEW, **how):
    """What the probe of the desk overview, `OVERVIEW`, read of `#/`: each part with its box, its
    words and what in it is cut, once every part has drawn."""
    seen = look(
        scene, tmp_path, route="#/", screen=screen, script=script, at=8000, budget=12000, **how
    )
    assert seen["errors"] == []
    assert seen["scrollWidth"] == screen[0]
    return seen


def test_at_a_desk_every_ranked_question_is_answered_above_the_fold_of_the_t_moment(
    scene, tmp_path
):
    """At 1440 by 900 over the T moment, each part that answers a ranked question is drawn, says
    something, and ends above y=900, so every question is answered on the first screen."""
    DAYS["t"](scene)
    planned(scene)
    seen = desk(scene, tmp_path)
    parts = {one["name"]: one for one in seen["parts"]} | {"chains": seen["chains"]}
    for question, answers in QUESTIONS.items():
        for name in answers:
            part = parts.get(name)
            assert part, f"{question}: {name} is not drawn"
            assert part["text"] and not part["text"].startswith("Asking"), (question, name, part)
            assert 0 <= part["box"]["top"] < part["box"]["bottom"] <= DESK[1], (
                question,
                name,
                part,
            )
    said = {name: part["text"].lower() for name, part in parts.items()}
    assert said["glance:band"].startswith("moving")
    assert said["you:tile"].startswith("needs you 4")
    assert said["glance:open"].startswith("open 44")
    assert re.match(r"in check 28 \+ 8 stacked", said["slow:tile"])
    assert "18 failing · 2 running or queued · 6 passed · 2 no run" in said["slow:tile"]
    assert said["glance:merged"].startswith("merged today 27")
    assert "10 of 14" in said["milestones:nearest"]
    assert "jv-build" in said["milestones:nearest"]
    assert said["since:landed"].startswith("landed")


@pytest.mark.parametrize("day", list(DAYS))
def test_no_part_of_the_desk_cuts_its_words_without_a_title_or_a_way_to_open_them(
    scene, tmp_path, day
):
    DAYS[day](scene)
    seen = desk(scene, tmp_path)
    assert {one["name"]: one["cut"] for one in seen["parts"] if one["cut"]} == {}


PHONE_QUESTIONS = {
    "are we stalled, and why": ("glance:band",),
    "where is all the work, every stage, every home": ("pipeline:homes",),
    "what needs me right now": ("you:rail",),
}
"""The first 3 ranked questions, and the part of the phone's overview that answers each: the
verdict, Every home and Needs you."""


HL_BAR = {
    "failing": "failing",
    "waiting": "running",
    "passed": "passed",
    "norun": "no run",
    "other": "other stages",
}
"""Each kind of row in a home's bar, in the bar's order, and the word its legend has for it."""


PHONE_ORDER = (
    ("glance:band",),
    ("you:rail",),
    ("pipeline:homes",),
    ("glance:open", "slow:tile"),
    ("glance:act", "glance:merged"),
    ("slow:rail",),
    ("since:landed",),
    ("board",),
    ("throughput:perday",),
    ("milestones:nearest",),
    ("slow:machine",),
)
"""The overview at 390, top to bottom, a row of the screen to each tuple: the verdict, Needs you,
Every home, the KPIs two by two, Slowed by, Landed, the board's stage folds, 7 d, the milestone and
the machine (`reports/jv-glance/build/wire-390.png`). `board` is the board, `#pipeline`."""


@pytest.mark.parametrize("day", list(DAYS))
def test_on_a_phone_questions_1_to_3_are_answered_above_the_fold(scene, tmp_path, day):
    """At 390 by 844 the verdict, Needs you and Every home are drawn, say something, and end
    above y=844. The header keeps Triage, ? and, under the name, the time of the last read, and
    its menu button opens Homes, the project and light or dark, all inside the screen."""
    DAYS[day](scene)
    seen = desk(scene, tmp_path, screen=PHONE)
    parts = {one["name"]: one for one in seen["parts"]}
    for question, answers in PHONE_QUESTIONS.items():
        for name in answers:
            part = parts.get(name)
            assert part, f"{question}: {name} is not drawn"
            assert part["text"] and not part["text"].startswith("Asking"), (question, name, part)
            assert 0 <= part["box"]["top"] < part["box"]["bottom"] <= PHONE[1], (
                question,
                name,
                part["box"],
            )
    shut = {one["id"]: one for one in seen["header"]}
    assert shut["tri"]["text"].startswith("Triage"), shut["tri"]
    assert shut["helpme"]["label"].endswith("the key ?"), shut["helpme"]
    assert re.fullmatch(r'"live · \d\d:\d\d"', seen["stamp"]), seen["stamp"]
    assert shut["hmenu"]["expanded"] == "false", shut["hmenu"]
    assert [i for i, one in shut.items() if one["shown"]] == ["tri", "helpme", "hmenu"]
    opened = {one["id"]: one for one in seen["opened"]}
    assert opened["hmenu"]["expanded"] == "true", opened["hmenu"]
    assert [i for i, one in opened.items() if not one["shown"]] == ["readat"], opened
    for one in [shut["tri"], shut["helpme"], shut["hmenu"], *opened.values()]:
        assert 0 <= one["box"]["left"] and one["box"]["right"] <= PHONE[0], one


@pytest.mark.parametrize("day", list(DAYS))
def test_on_a_phone_the_overview_is_one_column_in_the_order_of_the_wireframe(scene, tmp_path, day):
    """Each row of `PHONE_ORDER` starts below the one before it ends, and the parts of a row share
    its top, left to right. The Needs you tile is not drawn: the list right under the verdict says
    it, and the KPIs are the other four."""
    DAYS[day](scene)
    planned(scene)
    seen = desk(scene, tmp_path, screen=PHONE)
    boxes = {one["name"]: one["box"] for one in seen["parts"]} | {"board": seen["board"]}
    assert "you:tile" not in boxes
    drawn = [name for row in PHONE_ORDER for name in row]
    assert [name for name in drawn if name not in boxes] == []
    assert sorted(boxes, key=lambda name: (boxes[name]["top"], boxes[name]["left"])) == drawn
    bottom = 0
    for row in PHONE_ORDER:
        tops = {boxes[name]["top"] for name in row}
        assert len(tops) == 1 and min(tops) >= bottom, (row, tops, bottom)
        lefts = [boxes[name]["left"] for name in row]
        assert lefts == sorted(lefts) and len(set(lefts)) == len(row), (row, lefts)
        bottom = max(boxes[name]["bottom"] for name in row)


def test_every_home_is_a_line_with_its_open_rows_its_check_and_its_last_act(scene, tmp_path):
    """Over the T moment, each home of the project is one line, the root first and then by its
    open rows: its name, its open count, a bar of its rows in check by outcome beside the rest,
    and how long ago it last acted, on one line. Each line opens the board's rows of that home,
    keyed by its project and its name, `#/?home=demo/root`. The legend names only the kinds a bar
    draws, each in its own paint."""
    DAYS["t"](scene)
    seen = desk(scene, tmp_path, screen=PHONE)
    homes = seen["homes"]
    assert [(one["home"], one["text"].split()[:2]) for one in homes] == [
        ("demo/root", ["root", "20"]),
        ("demo/jview", ["jview", "15"]),
        ("demo/flow", ["flow", "8"]),
        ("demo/macos", ["macos", "1"]),
    ]
    assert all(re.fullmatch(r"\d+m|\d+h\d\d|\d+d|none", one["ago"]["text"]) for one in homes), homes
    assert [one["ago"]["lines"] for one in homes] == [1] * len(homes), homes
    assert [one["href"] for one in homes] == [f"#/?home={one['home']}" for one in homes]
    assert all(one["box"]["bottom"] - one["box"]["top"] >= 44 for one in homes), homes
    drawn = {cls for one in homes for cls in one["bar"]}
    legend = seen["legend"]
    assert [one["cls"] for one in legend] == [cls for cls in HL_BAR if cls in drawn], legend
    assert [one["text"] for one in legend] == [HL_BAR[one["cls"]] for one in legend], legend
    paints = [one["paint"] for one in legend]
    assert len(set(paints)) == len(paints) and "rgba(0, 0, 0, 0) none" not in paints, legend


LATE_BOARD = """
window.fetch = (function (fetch) {
  return function (path, how) {
    if (String(path).indexOf("/panel/pipeline.json") !== 0) return fetch(path, how);
    var later = new Promise(function (done) { setTimeout(done, 2000); });
    return later.then(function () { return fetch(path, how); });
  };
})(window.fetch);
"""
"""The page's `/panel/pipeline.json` answers 2 s after it is asked, so every other part of the
overview has answered while the board is still being asked."""


def test_on_a_phone_the_probe_waits_for_every_home_when_the_board_answers_last(scene, tmp_path):
    """With the board the last to answer, the phone's probe still reads Every home with a line
    for each home, and not the empty part drawn before the board came."""
    DAYS["t"](scene)
    seen = desk(scene, tmp_path, screen=PHONE, script=LATE_BOARD + OVERVIEW)
    assert [one["home"] for one in seen["homes"]] == [
        "demo/root",
        "demo/jview",
        "demo/flow",
        "demo/macos",
    ]


@pytest.mark.parametrize("day", list(DAYS))
def test_no_part_of_the_phone_cuts_its_words_without_a_way_to_open_them(scene, tmp_path, day):
    """A phone has no pointer to hover a title with, so each part wraps its words or is a link
    or a button to the rest of them."""
    DAYS[day](scene)
    seen = desk(scene, tmp_path, screen=PHONE)
    assert {one["name"]: one["cut"] for one in seen["parts"] if one["cut"]} == {}


HEALTH = """
window.addEventListener("load", function () {
  var started = Date.now();
  (function wait() {
    var h = document.getElementById("health");
    if ((!h || !h.textContent.trim()) && Date.now() - started < window.__at) {
      setTimeout(wait, 200);
      return;
    }
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify({ text: h.textContent, display: getComputedStyle(h).display });
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  })();
});
"""
"""A probe of a project's Health line: its words and how it is laid out."""


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_every_home_leaves_a_projects_health_line_a_paragraph(scene, tmp_path, screen):
    """Every home's lines have a class of their own, so the project page's Health line keeps its
    look and is not laid out as one of them."""
    DAYS["t"](scene)
    seen = look(scene, tmp_path, script=HEALTH, at=8000, budget=12000, screen=screen)
    assert seen["text"].strip(), seen
    assert seen["display"] == "block", seen


KETTLE = "demo/approve:tea-kettle"
"""The one need of `one_to_approve`: the row tea-kettle, waiting for its go."""


def one_to_approve(scene):
    """One need, tea-kettle's approval, for a brief that is on disk, and no gate. It returns the
    sha of the brief, which an approval names."""
    scene.waiting(
        [item("approve", "approve:tea-kettle", "approve tea-kettle", slug="tea-kettle", hours=2)]
    )
    (scene.home / "gates.md").write_text("")
    brief = queue.brief_path(scene.state, "tea-kettle")
    brief.parent.mkdir(exist_ok=True)
    brief.write_text(REQUEST.format(slug="tea-kettle"))
    return queue.brief_sha(brief.read_text())[:12]


COUNTED = 24
"""Looks, each 0.5 s, that outlast the 10-second countdown and the write after it."""


def approved_and_undone(scene, tmp_path, route, screen):
    """Tap Approve on `route` and wait out its countdown, and, on a page of its own, tap Approve
    then Undo inside the window. It gives back what each of the two looks saw, and the brief's
    sha."""
    sha = one_to_approve(scene)
    accept, undo = f'main [data-accept="{KETTLE}"]', f'main [data-undo="{KETTLE}"]'
    walks = {
        "kept": ["look", f"tap:{accept}", *["look"] * COUNTED],
        "undone": ["look", f"tap:{accept}", "look", f"tap:{undo}", *["look"] * COUNTED],
    }
    seen = {
        name: look(
            scene,
            tmp_path / name,
            route=route,
            screen=screen,
            walk=walk,
            at=4000 + 500 * len(walk),
            budget=4000 + 500 * len(walk) + 4000,
        )
        for name, walk in walks.items()
    }
    for one in seen.values():
        assert one["errors"] == []
    return seen["kept"], seen["undone"], sha


def approves_once_and_undo_sends_nothing(kept, undone, sha):
    assert kept["walked"][0]["details"] == "Details", kept["walked"][0]
    counting = kept["walked"][1]["acc"]
    assert counting.startswith("Approving it in") and counting.endswith("Undo"), counting
    assert [one["path"].partition("?")[0] for one in kept["writes"]] == ["/panel/you/approve"]
    assert kept["writes"][0]["body"] == {"slug": "tea-kettle", "sha": sha}
    assert undone["writes"] == []
    assert undone["walked"][-1]["acc"] == "", undone["walked"][-1]
    assert undone["walked"][-1]["accept"] == "Approve"


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_approve_on_the_front_rail_approves_after_its_undo_window_and_undo_sends_nothing(
    scene, tmp_path, screen
):
    """The rail's Approve is the project page's: it counts 10 s with an Undo beside it, and only
    then posts the approval. An Undo tapped in the window posts nothing, and the Approve is back."""
    approves_once_and_undo_sends_nothing(*approved_and_undone(scene, tmp_path, "#/", screen))


def a_minute_on(nth, body):
    """Each answer of `/stack.json` a minute later than the last, so each poll draws the rail's
    list time anew and the rail is drawn again."""
    later = datetime.fromisoformat(body["at"]) + timedelta(minutes=nth)
    return body | {"at": later.isoformat()}


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_a_poll_that_draws_the_rail_again_keeps_the_focus_on_undo_and_the_countdown_its_number(
    scene, tmp_path, screen
):
    """A poll inside the countdown draws the rail again: the focus stays on the Undo that was
    tapped into view, and the countdown still says how many seconds are left."""
    one_to_approve(scene)
    walk = ["look", f'tap:main [data-accept="{KETTLE}"]', *["look"] * 14]
    seen = look(
        scene,
        tmp_path,
        route="#/",
        screen=screen,
        walk=walk,
        alter=a_minute_on,
        at=4000 + 500 * len(walk),
        budget=4000 + 500 * len(walk) + 4000,
    )
    assert seen["errors"] == []
    assert seen["asked"].count("/stack.json") >= 3, seen["asked"]
    for one in seen["walked"][1:]:
        assert re.fullmatch(r"Approving it in \d+ s · Undo", one["acc"]), one
        assert one["undo"] == KETTLE, one


SHOWN = """window.addEventListener("load", function () { setTimeout(function () {
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify({ head: document.getElementById("needs-h").textContent,
    open: [].filter.call(document.querySelectorAll("#needs a, #needs button"), function (el) {
      return el.checkVisibility();
    }).map(function (el) { return el.textContent.trim(); }) });
  document.body.appendChild(pre);
}, 3000); });"""
"""A probe of the head of Needs you: its words, and each link or button of it that is drawn."""


@pytest.mark.parametrize("route", ["#/demo", "#/homes"])
def test_nothing_needs_you_draws_no_button_to_open(scene, tmp_path, route):
    """With nothing waiting, the head of Needs you says so and offers nothing to open."""
    scene.waiting([])
    (scene.home / "gates.md").write_text("")
    seen = look(scene, tmp_path, route=route, script=SHOWN, at=4000, budget=6000)
    assert seen["head"].startswith(("Nothing needs you", "Nothing waits on you")), seen
    assert seen["open"] == [], seen


SAID = """window.addEventListener("load", function () { setTimeout(function () {
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify({ errors: [], text: document.body.innerText });
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, 4000); });"""
"""A probe of every word the page draws, once it has drawn."""


MERGED_TODAY = re.compile(r"merged today\W*(\d+)|(\d+) merged today", re.I)


DONE = re.compile(r"\b(\d+) done\b|\bDone (\d+)\b")


DONE_SAID = {"#/": [], "#/triage": [], "#/demo": [2], "#/demo/board": [1, 1, 2]}
"""The done counts each route draws over that day: the project page's 2 done work items, and on
the Homes board, drawn over the project page, the 1 done row the board still has, in its
summary and on its card."""


def merged_and_done(scene):
    """A day with 21 rows merged and 2 rows done, each with a work item done today: jam-jar's row
    says done, and oat-milk's the pass judged done while its row still says running."""
    rows = [queued(f"rye-{n}", "merged", pr=f"#{n + 1}") for n in range(21)]
    rows.append(queued("jam-jar", "done", thread="mcp:jam-jar"))
    rows.append(queued("oat-milk", "running", thread="mcp:oat-milk", value="done"))
    scene.queue(rows)
    scene.moves(*((f"rye-{n}", "pr", "merged", 3 + 11 * n) for n in range(21)))
    lines = []
    for at, slug in enumerate(("jam-jar", "oat-milk")):
        name = f"w{at + 1}"
        for step, verb in enumerate(("proposed", "approved", "launched", "done")):
            when = iso(ago(minutes=40 - 10 * step - at))
            lines.append(
                {"id": f"{name}.{step + 1}", "item": name, "at": when, "by": "Josh"}
                | {"where": "chat", "line": verb, "verb": verb, "project": "demo"}
                | ({"slug": slug} if verb == "proposed" else {})
            )
    (scene.state / "items.jsonl").write_text("".join(json.dumps(one) + "\n" for one in lines))
    (scene.home / "gates.md").write_text("")
    scene.waiting([])


@pytest.mark.parametrize("route", ["#/", "#/triage", "#/demo", "#/demo/board"])
def test_every_merged_today_reads_the_rows_jbus_merged_today(scene, tmp_path, route):
    """Over a day of 21 merged rows and 2 done work items, each "Merged today" on the overview's
    tile, Triage's calm line, the project page and the Homes board reads 21: done work is not a
    merge, and is counted apart as done."""
    merged_and_done(scene)
    seen = look(scene, tmp_path, route=route, script=SAID, at=4000, budget=8000)
    found = [int(one or two) for one, two in MERGED_TODAY.findall(seen["text"])]
    assert found, seen["text"]
    assert set(found) == {21}, (found, seen["text"])
    done = sorted(int(one or two) for one, two in DONE.findall(seen["text"]))
    assert done == DONE_SAID[route], (done, seen["text"])
