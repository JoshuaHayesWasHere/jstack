"""The board: each home of a project as one card, with its crews, reviewers and scouts, each on
a stage of the process with how long it has been on it, under the home's goal and its chain of
plan entries, and with what merged today and what is done apart at the foot.

The stages are `state.STAGES`, the eleven the pipeline names, and a crew is on the stage the
pipeline puts its row on: the Homes drawer and the board never disagree on where a row is. A
row the view cannot place is on no stage in either.
"""

import dataclasses

import jsettings
from jbus import queue
from jbus.view import state as built
from view.scene import (
    NOW,
    RACK,
    ROOT,
    SHELF,
    Scene,
    ago,
    homed,
    iso,
    kinds,
    logged,
    out,
    row,
)
from view.walk import runs, sources

STAGES = [one.key for one in built.STAGES]


def board(scene):
    """The board as the server builds it, which reads a pass's stamps in the user's zone."""
    found = dataclasses.replace(sources(scene), user=jsettings.load())
    return built.Read(found, scene.name, NOW, runs).asked("board")["data"]


def workers(said):
    return {
        (one["kind"], one["slug"]): one
        for home in said["homes"]
        for one in home["workers"] + home["merged"] + home["done"]
    }


def pipeline(scene):
    found = dataclasses.replace(sources(scene), user=jsettings.load())
    said = built.Read(found, scene.name, NOW, runs).asked("pipeline")["data"]
    return {one["slug"]: one["stage"] for one in said["rows"]}


def test_the_board_names_the_eleven_stages_of_the_one_table(scene):
    said = board(scene)
    assert [one["key"] for one in said["stages"]] == [
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
        "merged",
    ]
    assert [one["name"] for one in said["stages"]] == [one.name for one in built.STAGES]


def test_each_state_jbus_judges_puts_its_crew_on_the_pipelines_stage(scene):
    """A row of every value jbus judges, from `kinds`: each crew is on the stage the pipeline
    puts its row on. A row jbus judged merged while the queue does not count it as over is
    merged, and off the pipeline."""
    judged = kinds(scene)
    got = {slug: one["stage"] for (kind, slug), one in workers(board(scene)).items()}
    placed = pipeline(scene)
    assert {slug: got[slug] for slug in judged if slug in placed} == {
        slug: placed[slug] for slug in judged if slug in placed
    }
    assert {slug for slug in judged if slug not in placed} == {"fig-pip"}
    assert got["fig-pip"] == "merged"
    assert {got[slug] for slug in judged} == set(STAGES) - {"scout", "stacked"}


def test_a_hung_turn_on_an_open_pull_request_is_on_its_rows_one_stage(scene):
    """The step jbus gives a hung or waiting thread is running, whatever its pull request
    does: the crewmate has it, so the board puts it on crew, as the pipeline does, and says it
    is hung."""
    scene.queue(
        [
            row("oat-milk", "pr", pr="#13", value="hung", facts={"pull": "review"}),
            row("oat-bowl", "pr", pr="#11", value="closed", facts={"pull": "closed"}),
            row("oat-lid", "gate", pr="#15", value="asking", facts={"pull": "findings"}),
        ]
    )
    got = workers(board(scene))
    placed = pipeline(scene)
    assert (got["crew", "oat-milk"]["stage"], got["crew", "oat-milk"]["state"]) == ("crew", "Hung")
    assert got["crew", "oat-milk"]["tone"] == "bad"
    assert {slug: got["crew", slug]["stage"] for slug in placed} == placed


def test_a_row_jbus_has_not_judged_is_on_no_stage_as_on_the_pipeline(scene):
    """A row that `work.json` does not have is on no step the view knows: the pipeline lists
    it as unplaced, and the board puts it on no stage either. A merged or done row with no
    judgment is over, and off the board."""
    scene.queue([row(f"bun-{status}", status, pr="#40") for status in queue.STATUSES], judged=False)
    got = {slug: one for (_, slug), one in workers(board(scene)).items()}
    assert {slug for slug in got if slug.startswith("bun-")} == {
        "bun-queued",
        "bun-launched",
        "bun-running",
        "bun-waiting",
        "bun-failed",
        "bun-stale",
        "bun-gate",
        "bun-left",
        "bun-pr",
    }
    assert all(one["stage"] is None for slug, one in got.items() if slug.startswith("bun-"))
    assert not {slug for slug in pipeline(scene) if slug.startswith("bun-")}
    assert got["bun-pr"]["state"] == "Unknown"


def test_each_home_is_one_card_with_its_crews_reviewers_and_scouts(tmp_path, monkeypatch):
    """The root first, then each child home by name, each with the workers that are its own.
    A reviewer at work is in review, and a scout that has not reported is on scout."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    said = board(scene)
    assert [one["name"] for one in said["homes"]] == [ROOT, SHELF, RACK]
    got = {
        one["name"]: sorted(
            (w["kind"], w["slug"], w["stage"]) for w in one["workers"] + one["merged"]
        )
        for one in said["homes"]
    }
    assert got == {
        ROOT: [
            ("crew", "oat-bowl", "merge"),
            ("crew", "oat-spoon", "review2"),
            ("crew", "rye-loaf", "merged"),
            ("crew", "tea-cups", "queued"),
            ("crew", "tea-kettle", "you"),
            ("crew", "tea-tray", "queued"),
        ],
        SHELF: [("crew", "jam-jar", "crew"), ("crew", "jam-lid", "you")],
        RACK: [
            ("crew", "oat-honey", "you"),
            ("crew", "oat-milk", "check"),
            ("reviewer", "oat-milk", "review"),
            ("scout", "look", "scout"),
        ],
    }
    heads = {one["name"]: (one["open"], one["waits"], one["health"]) for one in said["homes"]}
    assert heads == {ROOT: (5, 1, "moving"), SHELF: (2, 1, "moving"), RACK: (2, 2, "none")}


def test_a_scout_with_no_row_is_on_scout_until_its_home_settles_it(scene):
    (scene.home / "scouts").mkdir()
    (scene.home / "scouts" / "look.md").write_text("# look: x\n\n## Report\nStatus: done\n")
    (scene.home / "scouts" / "peek.md").write_text("# peek: x\n\n## Report\nStatus: blocked\n")
    scene.passed(20, threads=[out("scout: look", "ended", "idle"), out("scout: peek", "ended")])
    got = workers(board(scene))
    assert (got["scout", "look"]["stage"], got["scout", "look"]["state"]) == ("scout", "Reported")
    assert (got["scout", "peek"]["stage"], got["scout", "peek"]["tone"]) == ("scout", "ask")


def test_a_reviewer_whose_turn_ended_is_where_its_task_is_and_leaves_with_it(scene):
    """A reviewer that ended its turn is on its task's stage, for as long as its task has been
    on it: its thread was made an hour ago, the task came to its stage 5 minutes ago. Once the
    task merged, or is gone from the queue, the reviewer is off the board: only the crew counts
    as merged."""
    waits = "check has not passed"
    scene.queue(
        [
            row("oat-milk", "pr", pr="#13", why=f"wait: {waits}"),
            row("rye-loaf", "merged", pr="#9"),
        ]
    )
    scene.merge_log(logged(5, "wait", 13, waits))
    scene.passed(
        20,
        threads=[
            out("review: oat-milk", "ended", "idle"),
            out("review: rye-loaf", "ended", "idle"),
            out("review: long-gone", "ended", "idle"),
        ],
    )
    said = board(scene)
    got = workers(said)
    assert got["reviewer", "oat-milk"]["stage"] == got["crew", "oat-milk"]["stage"]
    assert got["reviewer", "oat-milk"]["since"] == iso(ago(minutes=5))
    assert got["crew", "oat-milk"]["since"] == iso(ago(minutes=5))
    assert ("reviewer", "rye-loaf") not in got
    assert ("reviewer", "long-gone") not in got
    merged = [(one["kind"], one["slug"]) for home in said["homes"] for one in home["merged"]]
    assert merged == [("crew", "rye-loaf")]


def test_the_time_on_a_stage_starts_when_the_row_came_to_that_stage(scene):
    """oat-milk came to review 30 minutes ago and to its second pass 10 minutes ago: the second
    pass is a stage of its own, so it has been on it for 10 minutes."""
    second = "the rebase changed the content after its review; scoped review of a..b c..d"
    scene.queue([row("oat-milk", "pr", pr="#13", why=f"wait: {second}")])
    scene.merge_log(
        logged(50, "wait", 13, "check has not passed"),
        logged(30, "wait", 13, "it has no review yet"),
        logged(10, "wait", 13, second),
    )
    got = workers(board(scene))["crew", "oat-milk"]
    assert (got["stage"], got["since"]) == ("review2", iso(ago(minutes=10)))


PLAN = """# demo: plan

Goal (2026-10-01, the user): every kettle boils on time
Vision: not the goal line

## oat-bowl: a bowl for the oats
Stage: building

## rye-loaf: a loaf for the table
Stage: building

## tea-kettle: a kettle that boils
Stage: planned

## next-pot: a pot for later
Stage: planned

## old-pan: a pan nobody wants yet
Stage: parked
"""


def test_each_card_has_its_goal_and_its_chain_of_plan_entries_in_plan_order(tmp_path, monkeypatch):
    """The root's goal is its plan's `Goal` line, and a child home with only a `Scope:` line
    has that. Each entry of the plan is a step of the chain: merged where every row of it is
    over, working with its open pull requests, queued where its rows wait to start, and as its
    `Stage:` says where it has no row. A home with no plan has no goal and no chain."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    (scene.home / "plan.md").write_text(PLAN)
    (scene.home / RACK / "plan.md").write_text("# rack: plan\n\nScope: spices in a rack\n")
    cards = {one["name"]: one for one in board(scene)["homes"]}
    assert cards[ROOT]["goal"] == "every kettle boils on time"
    assert [(one["slug"], one["mark"], one["prs"]) for one in cards[ROOT]["chain"]] == [
        ("oat-bowl", "working", ["#11"]),
        ("rye-loaf", "merged", []),
        ("tea-kettle", "queued", []),
        ("next-pot", "planned", []),
        ("old-pan", "parked", []),
    ]
    assert cards[ROOT]["chain"][0]["line"] == "a bowl for the oats"
    assert (cards[RACK]["goal"], cards[RACK]["chain"]) == ("spices in a rack", [])
    assert (cards[SHELF]["goal"], cards[SHELF]["chain"]) == ("", [])


def test_what_merged_today_is_at_the_foot_of_its_homes_card(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    cards = {one["name"]: one for one in board(scene)["homes"]}
    assert [(one["slug"], one["pr"], one["since"]) for one in cards[ROOT]["merged"]] == [
        ("rye-loaf", "#9", iso(ago(minutes=40)))
    ]
    assert all(one["stage"] != "merged" for card in cards.values() for one in card["workers"])
    assert cards[SHELF]["merged"] == cards[RACK]["merged"] == []
