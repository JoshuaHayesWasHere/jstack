"""The board: each home of a project as one card, with its crews, reviewers and scouts, each on
one of seven stages with how long it has been on it, under the home's goal and its chain of plan
entries, and with what merged today apart at the foot.

A stage is where a worker is along the process: briefed, running, PR open, in review, fixing,
green, merged. The current stage is the one in progress, so a pull request at `check` is on
green, working toward it. Each stage comes from what jbus judged, and no worker shows as
unknown: a row that `work.json` does not have takes its stage from its row's status.
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

STAGES = ["briefed", "running", "pr", "review", "fixing", "green", "merged"]


def board(scene):
    """The board as the server builds it, which reads a pass's stamps in the user's zone."""
    found = dataclasses.replace(sources(scene), user=jsettings.load())
    return built.Read(found, scene.name, NOW, runs).asked("board")["data"]


def workers(said):
    return {
        (one["kind"], one["slug"]): one
        for home in said["homes"]
        for one in home["workers"] + home["merged"]
    }


def test_the_board_names_the_seven_stages_in_the_order_of_the_process(scene):
    said = board(scene)
    assert [one["key"] for one in said["stages"]] == STAGES
    assert [one["name"] for one in said["stages"]] == [
        "Briefed",
        "Running",
        "PR open",
        "In review",
        "Fixing",
        "Green",
        "Merged",
    ]


def test_each_state_jbus_judges_puts_its_crew_on_one_stage(scene):
    """A row of every value jbus judges, from `kinds`. A gate, a hung turn or a leftover sits
    where its pull request is, and with none it is still running. A row jbus judged merged
    while the queue does not count it as over is merged."""
    judged = kinds(scene)
    got = {slug: one["stage"] for (kind, slug), one in workers(board(scene)).items()}
    want = {
        "fig-seed": "briefed",
        "fig-leaf": "briefed",
        "fig-jam": "briefed",
        "fig-husk": "briefed",
        "fig-stem": "briefed",
        "fig-sap": "briefed",
        "fig-fly": "briefed",
        "fig-bud": "running",
        "fig-tart": "running",
        "fig-dew": "running",
        "fig-wasp": "running",
        "fig-moth": "running",
        "fig-stalk": "running",
        "fig-root": "running",
        "fig-twig": "running",
        "fig-vine": "running",
        "fig-burr": "running",
        "fig-result": "pr",
        "fig-review": "review",
        "fig-second": "review",
        "fig-proof": "review",
        "fig-findings": "fixing",
        "fig-rebase": "fixing",
        "fig-check": "green",
        "fig-hold": "green",
        "fig-pip": "merged",
        "fig-rind": "merged",
    }
    assert {slug: got[slug] for slug in judged} == {slug: want[slug] for slug in judged}
    assert {slug: stage for slug, stage in got.items() if slug.startswith("fig-")} == want


def test_a_hung_turn_on_an_open_pull_request_stays_on_its_pull_requests_stage(scene):
    """The step jbus gives a hung or waiting thread is running, whatever its pull request
    does: the board puts it where its pull request is, and says it is hung."""
    scene.queue(
        [
            row("oat-milk", "pr", pr="#13", value="hung", facts={"pull": "review"}),
            row("oat-bowl", "pr", pr="#11", value="closed", facts={"pull": "closed"}),
            row("oat-lid", "gate", pr="#15", value="asking", facts={"pull": "findings"}),
        ]
    )
    got = workers(board(scene))
    assert (got["crew", "oat-milk"]["stage"], got["crew", "oat-milk"]["state"]) == (
        "review",
        "Hung",
    )
    assert got["crew", "oat-milk"]["tone"] == "bad"
    assert (got["crew", "oat-bowl"]["stage"], got["crew", "oat-bowl"]["state"]) == ("pr", "Closed")
    assert got["crew", "oat-lid"]["stage"] == "fixing"


def test_a_row_jbus_has_not_judged_takes_its_stage_from_its_status(scene):
    """Every status a row can have puts it on a stage: none is unknown. A merged or done row
    with no judgment is over, and off the board."""
    scene.queue([row(f"bun-{status}", status, pr="#40") for status in queue.STATUSES], judged=False)
    got = {slug: one for (_, slug), one in workers(board(scene)).items()}
    stages = {slug: one["stage"] for slug, one in got.items()}
    assert stages == {
        "bun-queued": "briefed",
        "bun-launched": "running",
        "bun-running": "running",
        "bun-waiting": "running",
        "bun-failed": "running",
        "bun-stale": "running",
        "bun-gate": "running",
        "bun-left": "running",
        "bun-pr": "pr",
    } | {slug: stages[slug] for slug in stages if not slug.startswith("bun-")}
    assert all(one["stage"] in STAGES for one in got.values())
    assert got["bun-pr"]["state"] == "Unknown"


def test_each_home_is_one_card_with_its_crews_reviewers_and_scouts(tmp_path, monkeypatch):
    """The root first, then each child home by name, each with the workers that are its own.
    A reviewer at work is in review, and a scout that has not reported is running."""
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
            ("crew", "oat-bowl", "fixing"),
            ("crew", "oat-spoon", "review"),
            ("crew", "rye-loaf", "merged"),
            ("crew", "tea-cups", "briefed"),
            ("crew", "tea-kettle", "briefed"),
            ("crew", "tea-tray", "briefed"),
        ],
        SHELF: [("crew", "jam-jar", "running"), ("crew", "jam-lid", "running")],
        RACK: [
            ("crew", "oat-honey", "green"),
            ("crew", "oat-milk", "green"),
            ("reviewer", "oat-milk", "review"),
            ("scout", "look", "running"),
        ],
    }
    heads = {one["name"]: (one["open"], one["waits"], one["health"]) for one in said["homes"]}
    assert heads == {ROOT: (5, 1, "moving"), SHELF: (2, 1, "moving"), RACK: (2, 2, "none")}


def test_a_scout_that_reported_is_green_until_its_home_settles_it(scene):
    (scene.home / "scouts").mkdir()
    (scene.home / "scouts" / "look.md").write_text("# look: x\n\n## Report\nStatus: done\n")
    (scene.home / "scouts" / "peek.md").write_text("# peek: x\n\n## Report\nStatus: blocked\n")
    scene.passed(20, threads=[out("scout: look", "ended", "idle"), out("scout: peek", "ended")])
    got = workers(board(scene))
    assert (got["scout", "look"]["stage"], got["scout", "look"]["state"]) == ("green", "Reported")
    assert (got["scout", "peek"]["stage"], got["scout", "peek"]["tone"]) == ("running", "ask")


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


def test_the_time_on_a_stage_spans_the_steps_inside_it(scene):
    """oat-milk came to review 30 minutes ago and to its second pass 10 minutes ago: both are
    in review, so it has been in review for 30 minutes. A step outside the stage before that
    does not count."""
    second = "the rebase changed the content after its review; scoped review of a..b c..d"
    scene.queue([row("oat-milk", "pr", pr="#13", why=f"wait: {second}")])
    scene.merge_log(
        logged(50, "wait", 13, "check has not passed"),
        logged(30, "wait", 13, "it has no review yet"),
        logged(10, "wait", 13, second),
    )
    got = workers(board(scene))["crew", "oat-milk"]
    assert (got["stage"], got["since"]) == ("review", iso(ago(minutes=30)))


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
