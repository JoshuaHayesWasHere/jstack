"""The board, jview's first screen: `#/` (and its alias `#/flow`) draws every open row of every
project in its stage, from `/panel/pipeline.json`.

The server's half of the board, `panels/pipeline/panel.py`, is ux-flow-model's. These tests serve
the board JSON from a fixture (`browser.boarded`), the shape the two halves pin, with 5, 27 and
80 rows. The 27 are the live rows of 2026-10-26 08:06 EDT that the mock was built from.

At 1440 by 900 the board is three headlines, a strip of the stages and a column of cards for
each stage. At 390 by 844 the headlines stack and each stage is a `<details>`. Each test reads
the headlines, picks a row, counts the cards it marks and the cards it dims, and presses Esc.
The page never runs wider than the screen, and axe finds no serious issue on it.
"""

from pathlib import Path

import pytest

from view.page.browser import (
    BOARDS,
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    WORDS,
    board,
    boarded,
    look,
)
from view.scene import Scene, Served

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 60)]


PROBE = (Path(__file__).parent / "pipeline.js").read_text()


AXE = (BOARDS / "axe.min.js").read_text() + "\n" + (BOARDS / "axe-run.js").read_text()


SIZES = {"5": 5, "27": 27, "80": 81}


SCREENS = {1440: DESK, 390: PHONE}


def shown(root, rows, screen, route="#/", pick="", tap="", script=PROBE, at=2000, **how):
    """What the probe found on the board the fixture `pipeline-<rows>.json` gives, with `pick`
    tapped once the page has drawn, and the board JSON."""
    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(root, patch)
        made = boarded(patch, rows)
        served = Served(scene)
        try:
            seen = look(
                scene,
                root,
                route=route,
                screen=screen,
                port=served.port,
                pick=pick,
                tap=tap,
                at=at,
                budget=9000,
                script=script,
                **how,
            )
        finally:
            served.close()
    return seen, made


def chain(made, slug):
    """The slugs a pick of `slug` marks: the row, what it waits on back to the head, and what
    waits on it, each as far as it goes."""
    rows = {(one["project"], one["slug"]): one for one in made["rows"]}
    me = next(one for one in made["rows"] if one["slug"] == slug)
    found = {(me["project"], slug)}
    for step in (
        lambda one: [(w["project"], w["slug"]) for w in one["waits_on"]],
        lambda one: [(one["project"], s) for s in one["waited_by"]],
    ):
        look = step(me)
        while look:
            key = look.pop()
            if key in rows and key not in found:
                found.add(key)
                look += step(rows[key])
    return found


def links(made, marked):
    return sum(
        1
        for one in made["rows"]
        if (one["project"], one["slug"]) in marked
        for w in one["waits_on"]
        if (w["project"], w["slug"]) in marked
    )


def a_middle(made):
    """A row that waits on another and has another waiting on it, or else one that waits."""
    rows = made["rows"]
    both = [one for one in rows if one["waits_on"] and one["waited_by"]]
    return (both or [one for one in rows if one["waits_on"]])[0]["slug"]


def age(made, since):
    from datetime import datetime

    at = datetime.fromisoformat(made["at"].replace("Z", "+00:00"))
    then = datetime.fromisoformat(since.replace("Z", "+00:00"))
    m = int((at - then).total_seconds() // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h{m % 60:02d}" if m < 2880 else f"{m // 1440}d"


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    seen = {}

    def view(rows, wide):
        if (rows, wide) not in seen:
            root = tmp_path_factory.mktemp(f"board-{rows}-{wide}")
            seen[rows, wide] = shown(root, rows, SCREENS[wide], pick=a_middle(board(rows)))
        return seen[rows, wide]

    return view


EVERY = [pytest.param(rows, wide, id=f"{rows}-{wide}") for rows in SIZES for wide in SCREENS]


@pytest.mark.parametrize(("rows", "wide"), EVERY)
def test_the_board_is_the_first_screen_and_runs_no_wider_than_the_screen(views, rows, wide):
    seen, made = views(rows, wide)
    assert seen["errors"] == []
    first = seen["before"]
    assert first["shown"] and not first["map"], first
    assert first["layout"] == ("columns" if wide == 1440 else "details")
    assert first["wide"]["page"] == first["wide"]["width"] == wide, first["wide"]
    assert first["wide"]["board"] <= first["wide"]["inside"], first["wide"]
    cards = sorted(c["slug"] for s in first["stages"] for c in s["cards"])
    assert cards == sorted(one["slug"] for one in made["rows"])
    assert len(cards) + len(made["unplaced"]) == SIZES[rows]
    for one in made["unplaced"]:
        assert one["slug"] in first["unplaced"] and one["cause"] in first["unplaced"]


@pytest.mark.parametrize(("rows", "wide"), EVERY)
def test_the_three_headlines_name_the_stuck_stage_the_longest_wait_and_the_longest_chain(
    views, rows, wide
):
    seen, made = views(rows, wide)
    heads = {one["key"]: one for one in seen["before"]["heads"]}
    assert list(heads) == ["stuck", "wait", "chain"]
    name = {one["key"]: one["name"] for one in made["stages"]}
    stuck, wait, longest = made["stuck"], made["longest_wait"], made["longest"]
    assert heads["stuck"]["text"].lower().startswith("most stuck")
    assert heads["stuck"]["value"] == (
        f"{name[stuck['stage']]}: {stuck['still']} of {stuck['count']} not moving"
    )
    assert heads["wait"]["text"].lower().startswith("waiting longest")
    assert heads["wait"]["value"] == (
        f"{wait['slug']}: {age(made, wait['since'])} in {name[wait['stage']]}"
    )
    assert wait["cause"] in heads["wait"]["text"]
    assert heads["chain"]["text"].lower().startswith("longest chain")
    assert heads["chain"]["value"].startswith(f"{longest['depth']} deep")
    assert longest["head"] in heads["chain"]["text"]
    assert longest["head_cause"] in heads["chain"]["text"]
    tops = [one["top"] for one in heads.values()]
    lefts = [one["left"] for one in heads.values()]
    if wide == 1440:
        assert len(set(tops)) == 1 and lefts == sorted(lefts), heads
    else:
        assert len(set(lefts)) == 1 and tops == sorted(tops) and len(set(tops)) == 3, heads


@pytest.mark.parametrize(("rows", "wide"), EVERY)
def test_each_stage_shows_its_count_and_oldest_and_the_stuck_one_is_outlined(views, rows, wide):
    seen, made = views(rows, wide)
    first = seen["before"]
    keys = [one["key"] for one in made["stages"]]
    assert [one["key"] for one in first["stages"]] == keys
    stuck = made["stuck"]["stage"]
    assert [one["key"] for one in first["stages"] if one["hot"]] == [stuck]
    for stage, drawn in zip(made["stages"], first["stages"], strict=True):
        assert drawn["head"].startswith(f"{stage['name']} {stage['count']}"), drawn["head"]
        if stage["oldest"] and stage["key"] != "merged":
            assert age(made, stage["oldest"]["since"]) in drawn["head"], drawn["head"]
        mine = [one for one in made["rows"] if one["stage"] == stage["key"]]
        cards = drawn["cards"]
        assert sorted(c["slug"] for c in cards) == sorted(one["slug"] for one in mine)
        still = {one["slug"] for one in mine if not one["moving"]}
        assert [c["slug"] in still for c in cards] == sorted(
            (c["slug"] in still for c in cards), reverse=True
        ), "not moving first"
        assert all(("still" in c["cls"].split()) == (c["slug"] in still) for c in cards)
        for c, one in ((c, next(o for o in mine if o["slug"] == c["slug"])) for c in cards):
            assert one["home"] in c["text"] and one["cause"] in c["text"], c
            assert age(made, one["since"]) in c["text"], c
    if wide == 1440:
        strip = {one["key"]: one for one in first["strip"]}
        assert list(strip) == keys
        assert [k for k, one in strip.items() if one["hot"]] == [stuck]
        for stage in made["stages"]:
            assert strip[stage["key"]]["text"].startswith(f"{stage['name']} {stage['count']}")
            if stage["still"]:
                assert f"{stage['still']} not moving" in strip[stage["key"]]["text"]
    else:
        assert [one["key"] for one in first["stages"] if one["open"]] == [stuck]


@pytest.mark.parametrize(("rows", "wide"), EVERY)
def test_a_pick_marks_its_chain_links_it_and_dims_the_rest_and_esc_clears_it(views, rows, wide):
    seen, made = views(rows, wide)
    slug = a_middle(made)
    marked = chain(made, slug)
    picked = seen["picked"]
    assert picked["picked"] == [slug]
    assert picked["marked"] == sorted(s for _, s in marked)
    assert len(marked) > 1
    assert picked["dimmed"] == len(made["rows"]) - len(marked)
    assert picked["links"] == links(made, marked) > 0
    assert f"pick={slug}" in picked["hash"]
    after = seen["after"]
    assert (after["marked"], after["dimmed"], after["links"]) == ([], 0, 0)
    assert "pick=" not in after["hash"] and after["shown"]


@pytest.mark.parametrize("wide", list(SCREENS))
def test_a_pick_in_the_address_marks_its_chain_on_the_first_draw(tmp_path, wide):
    made = board("80")
    slug = a_middle(made)
    seen, _ = shown(tmp_path, "80", SCREENS[wide], route=f"#/?pick={slug}")
    first = seen["before"]
    assert first["picked"] == [slug]
    assert first["marked"] == sorted(s for _, s in chain(made, slug))


def test_home_chips_count_and_filter_and_the_choice_is_in_the_address(tmp_path):
    made = board("27")
    seen, _ = shown(
        tmp_path / "jview",
        "27",
        DESK,
        route="#/flow?home=jview&still=1",
        tap='[data-bhome="macos"]',
    )
    first = seen["before"]
    homes = {}
    for one in made["rows"]:
        homes[one["home"]] = homes.get(one["home"], 0) + 1
    chips = [one["text"] for one in first["chips"]]
    assert chips[0] == f"All homes {len(made['rows'])}"
    assert sorted(chips[1:-1]) == sorted(f"{home} {n}" for home, n in homes.items())
    still = sum(1 for one in made["rows"] if one["home"] == "jview" and not one["moving"])
    assert chips[-1] == f"Not moving only {still}"
    pressed = [one["text"] for one in first["chips"] if one["pressed"] == "true"]
    assert pressed == [f"jview {homes['jview']}", f"Not moving only {still}"]
    cards = sorted(c["slug"] for s in first["stages"] for c in s["cards"])
    assert cards == sorted(
        one["slug"] for one in made["rows"] if one["home"] == "jview" and not one["moving"]
    )
    after = seen["after"]
    assert "home=macos" in after["hash"] and "still=1" in after["hash"]
    cards = sorted(c["slug"] for s in after["stages"] for c in s["cards"])
    assert cards == sorted(
        one["slug"] for one in made["rows"] if one["home"] == "macos" and not one["moving"]
    )


@pytest.mark.parametrize("where", ["homes", "board"])
def test_a_drawer_opened_over_the_homes_map_or_a_filtered_board_closes_back_to_it(tmp_path, where):
    """A drawer keeps the view it opened over: closing it comes back to `#/homes`, or to the
    board with its home, its filter and its pick."""
    route = "#/homes" if where == "homes" else f"#/?home=jview&still=1&pick={a_middle(board('27'))}"
    seen, _ = shown(
        tmp_path, "27", DESK, route=route, script="", walk=["open:help", "close"], at=4000
    )
    assert seen["errors"] == []
    opened, closed = seen["walked"]
    joined = route + ("&" if "?" in route else "?") + "open=help"
    assert opened["open"] and opened["hash"] == joined, opened["hash"]
    assert (closed["open"], closed["hash"]) == (False, route)


@pytest.mark.parametrize("where", ["homes", "board"])
def test_a_link_with_a_drawer_open_over_the_homes_map_or_a_filtered_board_loads_as_it_says(
    tmp_path, where
):
    """A link to a drawer over `#/homes`, or over a filtered board, loads with the drawer open
    over that view, and closing it comes back to the view the link named."""
    route = "#/homes" if where == "homes" else f"#/?home=jview&still=1&pick={a_middle(board('27'))}"
    link = route + ("&" if "?" in route else "?") + "open=help"
    seen, _ = shown(tmp_path, "27", DESK, route=link, script="", walk=["wait", "close"], at=4000)
    assert seen["errors"] == []
    loaded, closed = seen["walked"]
    assert (loaded["open"], loaded["hash"]) == (True, link)
    assert (closed["open"], closed["hash"]) == (False, route)


def test_a_chip_that_has_the_focus_filters_the_board_and_keeps_the_focus(tmp_path):
    """A click focuses a chip before it filters, as a pointer does: the board draws again and
    gives the focus back to the same chip."""
    chip = '[data-bhome="jview"]'
    seen, _ = shown(tmp_path, "27", DESK, script="", walk=[f"focus:{chip}", f"tap:{chip}"], at=4000)
    assert seen["errors"] == []
    assert seen["walked"][-1]["hash"] == "#/?home=jview"
    assert seen["walked"][-1]["focus"] == "ph-jview"


def test_the_homes_map_moved_to_its_own_tab(tmp_path):
    seen, _ = shown(tmp_path, "5", DESK, route="#/homes")
    first = seen["before"]
    assert first["map"] and not first["shown"]
    assert first["homes"] == {"hidden": False, "current": "page"}


@pytest.mark.parametrize("wide", [1440, 900, 390])
def test_the_headlines_and_the_strip_are_150_words_at_most_with_the_cards_apart(tmp_path, wide):
    """The first screen's budget of jv-budgets (#337), for the board: the cards are counted
    apart, as the dots of "Later" were. On a phone the header with its Homes tab stays one
    line."""
    seen, _ = shown(tmp_path, "80", (wide, 900 if wide > 390 else 844))
    first = seen["before"]
    assert first["words"]["heads"] > 0, first["words"]
    assert first["words"]["heads"] + first["words"]["strip"] <= WORDS, first["words"]
    assert first["homes"] == {"hidden": False, "current": ""}
    if wide == 390:
        assert first["header"] <= 56, first["header"]


@pytest.mark.parametrize("wide", list(SCREENS))
def test_axe_finds_no_serious_issue_on_the_board_with_a_pick(tmp_path, wide):
    made = board("80")
    seen, _ = shown(tmp_path, "80", SCREENS[wide], route=f"#/?pick={a_middle(made)}", script=AXE)
    assert seen["errors"] == []
    assert seen["violations"] == [], seen["violations"]
    assert seen["rings"] == [], seen["rings"]
