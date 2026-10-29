"""The Milestones panel: each plan entry of each home, counted as `jbus plan` counts them, and
drawn as a chain of steps toward its outcome."""

from jbus import plan, queue
from view.scene import row, table

PLAN = """# demo: plan

## tea-set: a whole tea set, seven pieces
Stage: planned
Done when:
- every piece is on the shelf

## tea-pot: a pot to pour from
Stage: planned

## rye-loaf: a loaf of rye
Stage: planned

## tea-cosy: a cosy for the pot
Stage: proposed
"""
SCOPED = "# demo, pantry: plan\n\n## jam-shelf: a shelf of jam\nStage: planned\n"


def sandbox(scene):
    """A plan whose entry `tea-set` has seven rows: four merged, one at a pull request, one
    running, and one queued behind the running one. The entry `tea-pot` has a row whose thread
    hung, and one that waits on a row of `tea-set`."""
    rows = [row(f"tea-{n}", "merged", pr=f"#{n}", entry="tea-set") for n in range(1, 5)]
    rows += [
        row("tea-5", "pr", pr="#5", checks="pending", why="wait: check has not passed"),
        row("tea-6", "running", thread="mcp:0006"),
        row("tea-7", depends=["tea-6"], why="depends on tea-6"),
    ]
    for one in rows[4:]:
        one["entry"] = "tea-set"
    rows += [
        row("pot-1", depends=["tea-6"], why="depends on tea-6", entry="tea-pot"),
        row("pot-2", "running", thread="mcp:0008", value="hung", entry="tea-pot"),
    ]
    scene.queue(table() + rows)
    (scene.home / "plan.md").write_text(PLAN)
    (scene.home / "pantry").mkdir()
    (scene.home / "pantry" / "home-id").write_text("mcp:pantry\n")
    (scene.home / "pantry" / "plan.md").write_text(SCOPED)


def milestones(served):
    return served.json("/panel/milestones.json?project=demo")["data"]["milestones"]


def test_an_entry_with_four_of_seven_merged_counts_four_of_seven_as_jbus_plan_does(scene, served):
    sandbox(scene)
    said = milestones(served)
    root, pantry = said["homes"]
    assert (root["name"], root["plan"], pantry["name"], pantry["plan"]) == (
        "",
        "read",
        "pantry",
        "read",
    )
    tea = next(one for one in root["entries"] if one["slug"] == "tea-set")
    assert (tea["over"], tea["total"]) == (4, 7)
    assert tea["finished"] == [{"word": "merged", "count": 4}]
    assert tea["pulls"] == [{"pr": "#5", "word": "pr"}]
    assert tea["rest"] == [{"word": "queued", "count": 1}, {"word": "running", "count": 1}]
    rows = queue.load(scene.state)
    printed = {
        line.split(" | ")[0]: line.split(" | ")[2] for line in plan.shown(PLAN, rows).splitlines()
    }
    assert tea["status"] == printed["tea-set"] == "4 of 7 merged, #5 at pr, 1 queued, 1 running"
    cosy = next(one for one in root["entries"] if one["slug"] == "tea-cosy")
    assert (cosy["total"], cosy["status"], cosy["steps"]) == (0, "proposed", [])
    rye = next(one for one in root["entries"] if one["slug"] == "rye-loaf")
    assert (rye["over"], rye["total"], rye["status"]) == (1, 1, "its row finished: close it")
    assert [one["slug"] for one in pantry["entries"]] == ["jam-shelf"]


def entry(served, slug):
    return next(one for one in milestones(served)["homes"][0]["entries"] if one["slug"] == slug)


def test_the_steps_run_in_their_order_with_a_mark_each_and_a_blocked_row_says_on_what(
    scene, served
):
    sandbox(scene)
    tea = entry(served, "tea-set")
    steps = [(one["slug"], one["mark"], one["pr"], one["by"]) for one in tea["steps"]]
    assert steps == [
        *((f"tea-{n}", "merged", f"#{n}", "") for n in range(1, 5)),
        ("tea-5", "waiting", "#5", ""),
        ("tea-6", "working", "", ""),
        ("tea-7", "blocked", "", "tea-6"),
    ]
    assert tea["holder"]["slug"] == "tea-7"
    assert (tea["holder"]["mark"], tea["holder"]["by"]) == ("blocked", "tea-6")
    assert tea["waits_on"] == []


def test_a_stuck_step_holds_its_chain_and_a_step_behind_another_chain_names_it(scene, served):
    sandbox(scene)
    pot = entry(served, "tea-pot")
    assert [(one["slug"], one["mark"]) for one in pot["steps"]] == [
        ("pot-2", "stuck"),
        ("pot-1", "blocked"),
    ]
    assert pot["holder"]["slug"] == "pot-2" and pot["holder"]["mark"] == "stuck"
    assert pot["holder"]["say"]
    assert pot["waits_on"] == [{"milestone": "tea-set", "slug": "tea-6", "mark": "working"}]


def test_a_home_with_no_plan_says_so(scene, served):
    said = milestones(served)
    assert said == {"homes": [{"name": "", "plan": "missing", "entries": []}]}
