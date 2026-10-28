"""The pipeline board: every open row of every project and home, placed in its stage, with the
chains its rows make and what holds the line, as `/panel/pipeline.json` answers it."""

import pytest

from view.days import t_moment
from view.scene import (
    CAPTURED,
    Scene,
    Served,
    ago,
    briefed,
    captured,
    et,
    iso,
    item,
    piped,
    row,
    stacked_pr,
)

KEYS = [
    "scout",
    "queued",
    "crew",
    "you",
    "review",
    "fix",
    "review2",
    "check",
    "stacked",
    "merge",
]


def board(scene, path="/panel/pipeline.json"):
    served = Served(scene)
    try:
        return served.json(path)
    finally:
        served.close()


def since(minutes):
    return iso(ago(minutes=minutes))


def at(slug, project, minutes):
    return {"slug": slug, "project": project, "since": since(minutes)}


def test_the_board_of_two_projects_and_three_homes_reads_every_field(scene):
    piped(scene)
    said = board(scene)
    assert said["panel"] == "pipeline"
    got = said["data"]
    assert got["at"] == iso(scene.now)
    assert [one["key"] for one in got["stages"]] == [*KEYS, "merged"]
    stages = {one["key"]: one for one in got["stages"]}
    assert stages["scout"] | {"oldest": None} == {
        "key": "scout",
        "name": "Scout",
        "count": 1,
        "still": 0,
        "oldest": None,
    }
    assert stages["scout"]["oldest"] == at("look", "demo", 45)
    assert {key: (one["count"], one["still"]) for key, one in stages.items()} == {
        "scout": (1, 0),
        "queued": (2, 2),
        "crew": (3, 0),
        "you": (2, 2),
        "review": (0, 0),
        "fix": (0, 0),
        "review2": (0, 0),
        "check": (1, 0),
        "stacked": (0, 0),
        "merge": (0, 0),
        "merged": (2, 0),
    }
    assert stages["queued"]["oldest"] == at("tea-cup", "demo", 25)
    assert stages["crew"]["oldest"] == at("tea-pot", "demo", 30)
    assert stages["you"]["oldest"] == at("oat-lid", "demo", 90)
    assert stages["review"]["oldest"] is None and stages["merged"]["oldest"] is None

    rows = {(one["project"], one["slug"]): one for one in got["rows"]}
    assert [(one["stage"], one["slug"]) for one in got["rows"]] == [
        ("scout", "look"),
        ("queued", "tea-cup"),
        ("queued", "tea-saucer"),
        ("crew", "tea-pot"),
        ("crew", "cleanup-ux-look-pr"),
        ("crew", "fig-jam"),
        ("you", "oat-lid"),
        ("you", "fig-tart"),
        ("check", "ux-look-pr"),
    ]
    assert rows["demo", "tea-pot"] == {
        "slug": "tea-pot",
        "project": "demo",
        "home": "jview",
        "stage": "crew",
        "since": since(30),
        "cause": "thread working",
        "cause_kind": "working",
        "cause_since": since(30),
        "moving": True,
        "waits_on": [],
        "waited_by": ["tea-cup"],
        "head": "tea-pot",
        "depth": 1,
        "wait": None,
    }
    assert rows["demo", "tea-cup"] | {"waits_on": None} == {
        "slug": "tea-cup",
        "project": "demo",
        "home": "jview",
        "stage": "queued",
        "since": since(25),
        "cause": "behind tea-pot",
        "cause_kind": "behind",
        "cause_since": since(25),
        "moving": False,
        "waits_on": None,
        "waited_by": ["tea-saucer"],
        "head": "tea-pot",
        "depth": 2,
        "wait": None,
    }
    assert rows["demo", "tea-cup"]["waits_on"] == [
        {"slug": "tea-pot", "project": "demo", "kind": "depends"}
    ]
    saucer = rows["demo", "tea-saucer"]
    assert (saucer["home"], saucer["head"], saucer["depth"], saucer["waited_by"]) == (
        "root",
        "tea-pot",
        3,
        [],
    )
    cleanup = rows["demo", "cleanup-ux-look-pr"]
    assert cleanup["home"] == "root"
    assert cleanup["waits_on"] == [{"slug": "ux-look-pr", "project": "demo", "kind": "merge_after"}]
    assert (cleanup["head"], cleanup["depth"]) == ("ux-look-pr", 2)
    look = rows["demo", "ux-look-pr"]
    assert (look["cause"], look["cause_since"], look["moving"], look["since"]) == (
        "check 1 of 4 running 3m",
        since(3),
        True,
        since(15),
    )
    assert look["waited_by"] == ["cleanup-ux-look-pr"]
    assert rows["demo", "oat-lid"]["home"] == "root"
    assert rows["demo", "oat-lid"]["cause"] == "asks you: which lid?"
    scout = rows["demo", "look"]
    assert (scout["home"], scout["since"], scout["moving"]) == ("jview", since(45), True)
    assert rows["pantry", "fig-tart"]["home"] == rows["pantry", "fig-jam"]["home"] == "root"

    assert got["unplaced"] == [
        {"slug": "bad-row", "project": "demo", "cause": "jmerge said: draft"}
    ]
    assert got["stuck"] == {"stage": "queued", "still": 2, "count": 2}
    assert got["longest_wait"] == {
        "slug": "oat-lid",
        "project": "demo",
        "stage": "you",
        "since": since(90),
        "cause": "asks you: which lid?",
    }
    assert got["longest"] == {
        "depth": 3,
        "head": "tea-pot",
        "head_project": "demo",
        "head_stage": "crew",
        "head_cause": "thread working",
        "chains": 2,
        "path": ["tea-pot", "tea-cup", "tea-saucer"],
    }


def test_a_row_merged_into_an_integration_branch_is_done_and_has_no_card(scene):
    """mac-a merged into `release/mac`, which has not landed on main: for the queue it is done
    as rye-loaf, merged into main, is. Neither has a card, the board has no stage for an
    integration branch, and both count in today's merges."""
    piped(scene)
    got = board(scene)["data"]
    keys = [one["key"] for one in got["stages"]]
    assert keys == [*KEYS, "merged"]
    assert not {"mac-a", "rye-loaf"} & {one["slug"] for one in got["rows"]}
    assert not {"mac-a", "rye-loaf"} & {one["slug"] for one in got["unplaced"]}
    assert next(one for one in got["stages"] if one["key"] == "merged")["count"] == 2


def test_one_project_gives_its_own_rows_and_the_stack_leaves_the_board_out(scene):
    piped(scene)
    one = board(scene, "/panel/pipeline.json?project=pantry")["data"]
    assert {(row["project"], row["slug"]) for row in one["rows"]} == {
        ("pantry", "fig-jam"),
        ("pantry", "fig-tart"),
    }
    assert one["longest"]["depth"] == 1 and one["longest"]["chains"] == 0
    stack = board(scene, "/stack.json")
    assert not {"pipeline", "stages", "rows", "unplaced", "stuck", "longest"} & set(stack)


def test_the_scouts_capture_is_stuck_in_check_and_its_longest_chain_is_two_deep(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch, name=CAPTURED)
    captured(scene)
    got = board(scene)["data"]
    assert len(got["rows"]) + len(got["unplaced"]) == 27
    assert {one["slug"] for one in got["unplaced"]} == {
        "bl-macos-ci-required",
        "cleanup-ux-telemetry-pr",
    }
    stages = {one["key"]: (one["count"], one["still"]) for one in got["stages"]}
    assert (stages["check"], stages["stacked"]) == ((10, 6), (2, 2))
    assert got["stuck"] == {"stage": "check", "still": 6, "count": 10}
    assert {one["slug"] for one in got["rows"] if one["stage"] == "stacked"} == {
        "cleanup-ux-homes-board-pr",
        "cleanup-ux-asks-count",
    }
    assert got["longest"] | {"chains": None} == {
        "depth": 2,
        "head": "mac-tree-spec-timeout",
        "head_project": CAPTURED,
        "head_stage": "crew",
        "head_cause": "thread working",
        "chains": None,
        "path": ["mac-tree-spec-timeout", "mac-sync-main-7"],
    }
    assert got["longest_wait"]["slug"] == "bl-lands"
    rows = {one["slug"]: one for one in got["rows"]}
    assert rows["cleanup-ux-look-pr"]["home"] == "root"
    assert rows["mac-sync-main-7"]["home"] == "macos"


@pytest.mark.parametrize(
    ("status", "value", "stage"),
    [
        ("queued", "ready", "queued"),
        ("running", "working", "crew"),
        ("running", "hung", "crew"),
        ("gate", "asking", "crew"),
        ("pr", "hold", "merge"),
        ("pr", "result", "review"),
        ("pr", "review", "review"),
        ("pr", "findings", "fix"),
        ("pr", "second", "review2"),
        ("pr", "check", "check"),
        ("pr", "proof", "merge"),
        ("pr", "rebase", "merge"),
        ("pr", "unknown", None),
    ],
)
def test_a_row_is_placed_by_its_step(scene, status, value, stage):
    scene.queue([row("one-row", status, value=value, pr="#5" if status == "pr" else "")])
    got = board(scene)["data"]
    placed = {one["slug"]: one["stage"] for one in got["rows"]}
    unplaced = {one["slug"] for one in got["unplaced"]}
    assert placed.get("one-row") == stage
    assert ("one-row" in unplaced) == (stage is None)


def test_needs_you_is_the_rows_jbus_lists_and_counts_every_need_of_the_you_panel(scene):
    """The stage holds a row jbus's list names, at any step, and none it leaves out, as a gate
    on its default. Its count is the You panel's, a need that names no row too."""
    scene.queue(
        [
            row("oat-lid", "pr", pr="#5", value="result"),
            row("oat-cup", "gate", why="a gate on its default"),
        ]
    )
    scene.waiting(
        [
            item("left", "left:oat-lid", "left oat-lid: a step only you can take", slug="oat-lid"),
            item("config", "config:wakes", "config: wakes are off"),
        ]
    )
    got = board(scene)["data"]
    placed = {one["slug"]: one["stage"] for one in got["rows"]}
    assert (placed["oat-lid"], placed["oat-cup"]) == ("you", "crew")
    served = Served(scene)
    try:
        mine = served.json("/state.json?project=demo")["needs"]
    finally:
        served.close()
    stage = next(one for one in got["stages"] if one["key"] == "you")
    assert stage["count"] == len(mine) == 2


def test_the_rows_of_a_loop_share_one_depth_and_head_and_a_row_behind_it_is_one_deeper(scene):
    scene.queue(
        [
            row("loop-a", depends=["loop-b"], since=et(ago(minutes=30))),
            row("loop-b", depends=["loop-a"], since=et(ago(minutes=20))),
            row("loop-c", depends=["loop-b"], since=et(ago(minutes=10))),
        ]
    )
    rows = {one["slug"]: one for one in board(scene)["data"]["rows"]}
    assert {slug: (one["depth"], one["head"]) for slug, one in rows.items()} == {
        "loop-a": (1, "loop-a"),
        "loop-b": (1, "loop-a"),
        "loop-c": (2, "loop-a"),
    }


def test_the_longest_chain_runs_through_a_loop_in_its_middle_back_to_its_head(scene):
    """loop-a and loop-b wait on each other, and loop-a on the head: the path from loop-c, the
    deepest, takes both rows of the loop on its way back, and claims no link that is not."""
    scene.queue(
        [
            row("head-x", since=et(ago(minutes=40))),
            row("loop-a", depends=["loop-b", "head-x"], since=et(ago(minutes=30))),
            row("loop-b", depends=["loop-a"], since=et(ago(minutes=20))),
            row("loop-c", depends=["loop-b"], since=et(ago(minutes=10))),
        ]
    )
    longest = board(scene)["data"]["longest"]
    assert (longest["depth"], longest["head"]) == (3, "head-x")
    assert longest["path"] == ["head-x", "loop-a", "loop-b", "loop-c"]


def test_a_stacked_pull_request_leaves_check_for_stacked_whatever_its_own_checks_say(scene):
    """`bun-top` and `bun-lid` merge after `bun-base`, so they are in Stacked, though one's
    checks passed and the other's failed. `bun-pot` passed and waits for `jmerge` in Check.
    Every row in either stage says what it waits on, and no other row does."""
    stacked_pr(scene, row("oat-pan", "running", thread="mcp:pan"))
    got = board(scene)["data"]
    stages = {one["key"]: one["count"] for one in got["stages"]}
    assert (stages["check"], stages["stacked"]) == (1, 2)
    rows = {one["slug"]: (one["stage"], one["wait"]) for one in got["rows"]}
    assert rows == {
        "bun-top": ("stacked", "stacked"),
        "bun-lid": ("stacked", "stacked"),
        "bun-pot": ("check", "passed"),
        "oat-pan": ("crew", None),
    }


def cells(home):
    """A home's cells that hold a row: the count, how many are an hour old or more, and each
    outcome its rows wait on that one row has."""
    return {
        key: (one["count"], one["old"], {wait: n for wait, n in one["waits"].items() if n})
        for key, one in home["cells"].items()
        if one["count"]
    }


def test_the_t_moments_matrix_has_a_line_for_every_home_an_empty_one_too(scene):
    """The T moment over the root, jview, flow and macos, as build/wire-1440.png draws it, and
    `infra`, a scope with no open row, which has its line all the same: each home's open rows,
    its last act, and a cell per stage with its rows, the ones an hour old or more and what the
    rows in check and stacked wait on. The longest chain is two deep, a stacked row behind the
    first failing check, and 6 stacked rows merge after 6 parents whose checks failed."""
    t_moment(scene)
    briefed(scene, infra_only="infra")
    (scene.home / "tasks" / "infra-only.md").unlink()
    got = board(scene)["data"]
    homes = {one["name"]: one for one in got["homes"]}
    assert [(one["name"], one["open"]) for one in got["homes"]] == [
        ("root", 20),
        ("jview", 15),
        ("flow", 8),
        ("macos", 1),
        ("infra", 0),
    ]
    assert {one["project"] for one in got["homes"]} == {"demo"}
    assert cells(homes["root"]) == {
        "crew": (4, 0, {}),
        "you": (2, 0, {}),
        "review2": (1, 0, {}),
        "check": (7, 5, {"failing": 5, "passed": 2}),
        "stacked": (6, 4, {"stacked": 6}),
    }
    assert cells(homes["jview"]) == {
        "you": (1, 0, {}),
        "review2": (1, 0, {}),
        "check": (13, 10, {"failing": 7, "waiting": 2, "passed": 4}),
    }
    assert cells(homes["flow"]) == {"check": (8, 6, {"failing": 6})}
    assert cells(homes["macos"]) == {"you": (1, 0, {})}
    assert cells(homes["infra"]) == {}
    assert set(homes["infra"]["cells"]) == set(KEYS)
    assert homes["infra"]["last"] is None
    assert homes["macos"]["last"] == {
        "at": iso(ago(minutes=10)),
        "what": "hold 103 https://github.com/acme/demo/pull/103: needs user, touches "
        "skills/crew/SKILL.md",
    }
    oldest = homes["root"]["cells"]["stacked"]["oldest"]
    assert (oldest["slug"], oldest["project"]) == ("oat-platter", "demo")
    rows = {one["slug"]: one for one in got["rows"]}
    for home in got["homes"]:
        for key, cell in home["cells"].items():
            mine = [
                one for one in rows.values() if (one["home"], one["stage"]) == (home["name"], key)
            ]
            assert cell["count"] == len(mine)
    assert got["longest"]["path"] == ["fig-saucer", "oat-platter"]
    assert rows["oat-platter"]["waits_on"][0]["slug"] == "fig-saucer"
    assert got["stacked"] == {
        "rows": 6,
        "parents": 6,
        "waits": {"failing": 6, "waiting": 0, "passed": 0, "stacked": 0},
    }
