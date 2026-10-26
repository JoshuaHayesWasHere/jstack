"""The pipeline board: every open row of every project and home, placed in its stage, with the
chains its rows make and what holds the line, as `/panel/pipeline.json` answers it."""

import pytest

from view.scene import CAPTURED, Scene, Served, ago, captured, iso, piped, row

KEYS = ["scout", "queued", "crew", "you", "review", "fix", "review2", "check", "merge", "train"]


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
        "merge": (0, 0),
        "train": (1, 1),
        "merged": (1, 0),
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
        ("train", "mac-a"),
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
    }
    assert rows["demo", "tea-cup"]["waits_on"] == [
        {"slug": "tea-pot", "project": "demo", "kind": "depends"}
    ]
    saucer = rows["demo", "tea-saucer"]
    assert (saucer["home"], saucer["head"], saucer["depth"], saucer["waited_by"]) == (
        "jview",
        "tea-pot",
        3,
        [],
    )
    cleanup = rows["demo", "cleanup-ux-look-pr"]
    assert cleanup["home"] == "jview"
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
    assert rows["demo", "oat-lid"]["cause"] == "asks you: a gate the Chef has"
    train = rows["demo", "mac-a"]
    assert (train["stage"], train["since"], train["moving"], train["cause_kind"]) == (
        "train",
        since(50),
        False,
        "train",
    )
    assert "train/mac" in train["cause"]
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
        "cause": "asks you: a gate the Chef has",
    }
    assert got["longest"] == {
        "depth": 3,
        "head": "tea-pot",
        "head_project": "demo",
        "head_stage": "crew",
        "head_cause": "thread working",
        "chains": 2,
    }


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
    check = next(one for one in got["stages"] if one["key"] == "check")
    assert (check["count"], check["still"]) == (12, 8)
    assert got["stuck"] == {"stage": "check", "still": 8, "count": 12}
    assert got["longest"] | {"chains": None} == {
        "depth": 2,
        "head": "mac-tree-spec-timeout",
        "head_project": CAPTURED,
        "head_stage": "crew",
        "head_cause": "thread working",
        "chains": None,
    }
    assert got["longest_wait"]["slug"] == "bl-lands"
    rows = {one["slug"]: one for one in got["rows"]}
    assert rows["cleanup-ux-look-pr"]["home"] == "jview"
    assert rows["mac-sync-main-7"]["home"] == "macos"


@pytest.mark.parametrize(
    ("status", "value", "stage"),
    [
        ("queued", "ready", "queued"),
        ("running", "working", "crew"),
        ("running", "hung", "you"),
        ("gate", "asking", "you"),
        ("pr", "hold", "you"),
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
