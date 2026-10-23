"""Homes: each task, thread and need of a project carries the home it belongs to, and the
summary has the project's homes, the root first, each with its open count and its waits.

A home is what `jbriefs.home_of` says of a brief's `Home:` line. The scene has the root and
two child homes, `pantry-shelf` by its name and `spice-rack` by its thread id, and a brief
that names `old-shelf`, a scope that has retired: jbriefs puts its row under the root, and the
row says which scope it named.
"""

from jbus.view import state as built
from view.scene import GATE, NOW, Scene, out
from view.walk import runs, sources

ROOT, SHELF, RACK, OLD = "", "pantry-shelf", "spice-rack", "old-shelf"
HOMES = {
    "tea-kettle": None,
    "tea-tray": OLD,
    "jam-jar": SHELF,
    "jam-lid": SHELF,
    "oat-milk": RACK,
    "oat-honey": "mcp:rack",
}


def homed(scene):
    """The scene's homes: the root's `home-id`, two child homes and a retired scope, and a
    brief for each slug of `HOMES` in the home's `tasks/`, with a `Home:` line where one is
    named. The child home `spice-rack` also has a gate with no default, which waits on the
    user, and a scout of its own."""
    (scene.home / "home-id").write_text("mcp:root\n")
    for name in (SHELF, RACK, OLD):
        (scene.home / name).mkdir()
    (scene.home / SHELF / "home-id").write_text("mcp:shelf\n")
    (scene.home / RACK / "home-id").write_text("mcp:rack\n")
    (scene.home / OLD / "handoff.md").write_text("Status: retired\n")
    gate = GATE.format(n=30, asked="which jar for the cloves?", status="open", default="")
    (scene.home / RACK / "gates.md").write_text(gate)
    for kind, slug, home in (
        *(("tasks", slug, home) for slug, home in HOMES.items()),
        ("scouts", "look", RACK),
    ):
        (scene.home / kind).mkdir(exist_ok=True)
        line = f"Home: {home}\n" if home else ""
        (scene.home / kind / f"{slug}.md").write_text(f"# {slug}: a made-up task\n{line}Task: x\n")
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar"),
            out("review: oat-milk"),
            out("scout: look", "waiting"),
            out("crew: tea-cups"),
            out("home: demo", id="mcp:root"),
            out("home: demo pantry-shelf", id="mcp:shelf"),
            out("a thread he opened"),
        ],
    )


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
    assert project["homes"] == want
    assert state["summary"]["homes"] == want
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
    assert project["homes"] == [
        {"name": ROOT, "open": project["open"], "waits": project["waits"]}
    ]
    assert {(one["home"], one["retired"]) for one in state["tasks"]} == {(ROOT, "")}
