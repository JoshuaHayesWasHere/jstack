"""Homes: each task, thread and need of a project carries the home it belongs to, and the
summary has the project's homes, the root first, each with its open count and its waits.

A home is what `jbriefs.home_of` says of a brief's `Home:` line. The scene has the root and
two child homes, `pantry-shelf` by its name and `spice-rack` by its thread id, and a brief
that names `old-shelf`, a scope that has retired: jbriefs puts its row under the root, and the
row says which scope it named.
"""

import pytest

from jbus.view import state as built
from view.scene import IN_CHECK, NOW, OLD, RACK, ROOT, SHELF, Scene, ago, homed, in_check, iso, out
from view.walk import runs, sources


def answers(scene):
    found = sources(scene)
    return built.stack(found, NOW, runs), built.build(found, scene.name, NOW, runs)


def test_each_task_carries_its_home_from_its_briefs_home_line(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    _, state = answers(scene)
    got = {one["slug"]: (one["home"], one["retired"]) for one in state["tasks"]}
    assert got == {
        "tea-kettle": (ROOT, ""),
        "tea-cups": (ROOT, ""),
        "tea-tray": (ROOT, OLD),
        "jam-jar": (SHELF, ""),
        "jam-lid": (SHELF, ""),
        "oat-bowl": (ROOT, ""),
        "oat-spoon": (ROOT, ""),
        "oat-milk": (RACK, ""),
        "oat-honey": (RACK, ""),
    }


def test_each_thread_carries_its_home_where_it_has_one(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    _, state = answers(scene)
    got = {one["title"]: (one["home"], one["retired"]) for one in state["threads"]}
    assert got == {
        "crew: jam-jar": (SHELF, ""),
        "review: oat-milk": (RACK, ""),
        "scout: look": (RACK, ""),
        "crew: tea-cups": (ROOT, ""),
        "home: demo": (ROOT, ""),
        "home: demo pantry-shelf": (SHELF, ""),
        "a thread he opened": (None, ""),
    }


def test_the_summary_groups_the_project_by_home_the_root_first(tmp_path, monkeypatch):
    """The root has its five open tasks, the retired scope's among them, and the approval of
    tea-kettle. Each child home has its two tasks. `pantry-shelf` waits on the user for the
    gate of jam-lid, and `spice-rack` for the held pull request of oat-honey and the gate of
    its own `gates.md`. The counts add up to the project's."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    stack, state = answers(scene)
    want = [
        {"name": ROOT, "open": 5, "waits": 1},
        {"name": SHELF, "open": 2, "waits": 1},
        {"name": RACK, "open": 2, "waits": 2},
    ]
    (project,) = stack["projects"]
    assert [
        {key: one[key] for key in ("name", "open", "waits")} for one in project["homes"]
    ] == want
    assert state["summary"]["homes"] == project["homes"]
    assert sum(one["open"] for one in want) == project["open"]
    assert sum(one["waits"] for one in want) == project["waits"] == len(stack["needs"])
    needs = {one["key"]: one["home"] for one in stack["needs"]}
    assert sorted(needs.values()) == sorted([ROOT, SHELF, RACK, RACK])
    assert needs["approve:tea-kettle"] == ROOT
    assert needs["row:jam-lid"] == SHELF


def test_a_project_with_no_child_home_has_the_root_alone(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stack, state = answers(scene)
    (project,) = stack["projects"]
    (root,) = project["homes"]
    assert (root["name"], root["open"], root["waits"]) == (ROOT, project["open"], project["waits"])
    assert {(one["home"], one["retired"]) for one in state["tasks"]} == {(ROOT, "")}


def healths(scene):
    stack, _ = answers(scene)
    (project,) = stack["projects"]
    return {one["name"]: (one["health"], one["since"]) for one in project["homes"]}


def test_each_home_says_how_its_own_thread_is_and_since_when_it_hung_or_went_quiet(
    tmp_path, monkeypatch
):
    """A home's health is its own thread's: moving while a turn writes, waiting while it waits
    on a request, quiet or hung with the time it last wrote, ended where its turn ended with a
    task of its own open, and at rest where it ended with nothing open. A home no thread of the
    last pass is, `spice-rack` here, has none: a repo may run with no home at all. Where the
    pass left no list of threads, no home's health is known."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    assert healths(scene) == {ROOT: ("moving", None), SHELF: ("moving", None), RACK: ("none", None)}
    for live, minutes, health in (("hung", 25, "hung"), ("quiet", 12, "quiet")):
        scene.passed(
            20,
            threads=[
                out("home: demo", "waiting", id="mcp:root"),
                out("home: demo pantry-shelf", live, minutes=minutes, id="mcp:shelf"),
            ],
        )
        wrote = iso(ago(minutes=minutes))
        assert healths(scene) == {
            ROOT: ("waiting", None),
            SHELF: (health, wrote),
            RACK: ("none", None),
        }
    scene.passed(
        20,
        threads=[
            out("home: demo", "ended", "completed", id="mcp:root"),
            out("home: demo pantry-shelf", "ended", "completed", id="mcp:shelf"),
        ],
    )
    assert healths(scene)[ROOT] == ("ended", None)
    for slug in ("jam-jar", "jam-lid"):
        (scene.home / "tasks" / f"{slug}.md").write_text(f"# {slug}\nHome: {RACK}\nTask: x\n")
    assert healths(scene)[SHELF] == ("rest", None)
    scene.passed(20, threads=None)
    assert set(healths(scene).values()) == {("unknown", None)}


def test_a_home_with_two_threads_is_the_one_that_is_out(tmp_path, monkeypatch):
    """A handoff leaves the old home's thread beside the new one's for a while: the home is
    the thread that is out, whatever order the pass listed them in."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    (scene.home / SHELF / "handoff.md").write_text("Was home: mcp:shelf-old\n")
    scene.passed(
        20,
        threads=[
            out("home: demo pantry-shelf", "moving", id="mcp:shelf"),
            out("home: demo pantry-shelf", "ended", "completed", id="mcp:shelf-old"),
        ],
    )
    assert healths(scene)[SHELF] == ("moving", None)


@pytest.mark.parametrize(
    ("plan", "started"),
    [
        (
            "# demo, pantry-shelf: plan\n\nGoal (2026-10-09, the user): jars on the shelf\n",
            "2026-10-09",
        ),
        ("# pantry-shelf home: plan\n\nScope: jars on the shelf\n", None),
        (None, None),
    ],
)
def test_a_child_home_is_as_old_as_the_goal_line_that_made_its_scope(
    tmp_path, monkeypatch, plan, started
):
    """The block that makes a scope writes its `plan.md` with the goal and the day as its first
    lines. A plan with no such line, or no plan, gives no start: nothing kept says. The root is
    no scope and has none."""
    scene = Scene(tmp_path, monkeypatch)
    homed(scene)
    if plan is not None:
        (scene.home / SHELF / "plan.md").write_text(
            plan + "\n## a later entry\nGoal (2026-10-11, x): y\n"
        )
    stack, _ = answers(scene)
    (project,) = stack["projects"]
    got = {one["name"]: one["started"] for one in project["homes"]}
    assert got == {ROOT: None, SHELF: started, RACK: None}


def test_each_home_counts_its_rows_in_check_as_failing_running_or_queued_and_passed(
    tmp_path, monkeypatch
):
    """pie-1 to pie-3 are pantry-shelf's: two red and one that passed. The root has the rest:
    one red, one running, and one with no check reported yet, which waits for a runner."""
    scene = Scene(tmp_path, monkeypatch)
    in_check(scene, ["failed", "failed", "passed", "failed", "pending", "none"])
    (scene.home / SHELF).mkdir()
    (scene.home / SHELF / "home-id").write_text("mcp:shelf\n")
    (scene.home / "tasks").mkdir(exist_ok=True)
    for slug, _, _ in IN_CHECK[:3]:
        brief = f"# {slug}: a made-up task\nHome: {SHELF}\nTask: x\n"
        (scene.home / "tasks" / f"{slug}.md").write_text(brief)
    stack, state = answers(scene)
    (project,) = stack["projects"]
    assert {one["name"]: one["in_check"] for one in project["homes"]} == {
        ROOT: {"failing": 1, "waiting": 2, "passed": 0, "stacked": 0},
        SHELF: {"failing": 2, "waiting": 0, "passed": 1, "stacked": 0},
    }
    assert state["summary"]["homes"] == project["homes"]
