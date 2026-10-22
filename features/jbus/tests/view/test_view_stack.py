"""The stack: the machine once, and a summary of each project, from one request."""

import json

from jbus import questions
from jbus.view import state as built
from jbus.view.panels.checks import panel as checks_panel
from jbus.view.panels.room import panel as room_panel
from view.scene import NOW, Scene, Served, a_noticed, asks, iso, kept, stacked


def test_the_stack_is_the_machine_once_and_a_summary_of_each_project(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    a_noticed(scene, ("tea-kettle", "new", 5, {}), ("jam-jar", "dropped", 9, {}))
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert stack["at"] == iso(NOW)
    assert [one["key"] for one in stack["steps"]] == [
        *(one["key"] for one in demo["steps"]),
        "unknown",
    ]
    assert list(stack["machine"]) == ["jbus", "room", "runners", "runners_read", "unwell"]
    assert stack["machine"]["unwell"] == []
    assert stack["machine"]["jbus"]["stopped"] is False
    assert stack["machine"]["jbus"]["status"] == {
        "last_pass": demo["jbus"]["status"]["last_pass"],
        "token_expires": demo["jbus"]["status"]["token_expires"],
        "streaks": {},
        "homes_off_bus": [],
        "scratch": [],
    }
    same = {key: one for key, one in demo["room"].items() if key != "tmp"}
    assert {key: one for key, one in stack["machine"]["room"].items() if key != "tmp"} == same
    assert stack["machine"]["runners"] == demo["checks"]["runners"]
    assert [one["name"] for one in stack["projects"]] == ["demo", "larder", "pantry"]
    by = {one["name"]: one for one in stack["projects"]}
    assert by["larder"]["health"]["blind"] == 1
    assert by["larder"] == {
        "name": "larder",
        "repo": "",
        "broken": [
            {"what": "CI not read", "open": "checks"},
            {"what": "13 sources unread", "open": "pulse"},
        ],
        "unplaced": [],
        "waits": 0,
        "noticed": 0,
        "open": 0,
        "steps": {},
        "merged": 0,
        "threads": None,
        "health": {
            "checks": {"running": 0, "waiting": 0, "failed": 0, "error": "the repo is not known"},
            "bus": {"outbox": 0, "failed_wakes": 0, "last_error": ""},
            "threads": None,
            "blind": 1,
            "unwell": [
                {"name": name, "state": "missing"}
                for name in (
                    "work.json",
                    "waiting-on-user.json",
                    "transitions.jsonl",
                    "events.jsonl",
                    "main.json",
                    "checks.json",
                    "stall.json",
                    "wake.json",
                    "sent.json",
                    "merge.log",
                )
            ]
            + [{"name": "GitHub", "state": "unreadable"}]
            + [{"name": name, "state": "missing"} for name in ("ci.jsonl", "ci-prs.jsonl")],
        },
    }
    pantry = by["pantry"]
    assert (pantry["repo"], pantry["waits"], pantry["noticed"]) == ("acme/pantry", 1, 0)
    assert "waiting" not in pantry
    assert (pantry["open"], pantry["steps"], pantry["merged"]) == (2, {"running": 1, "gate": 1}, 1)
    assert pantry["health"]["checks"] == {"running": 1, "waiting": 0, "failed": 0, "error": ""}
    shown = by["demo"]
    assert (shown["repo"], shown["waits"], shown["noticed"]) == ("acme/demo", 3, 1)
    assert shown["waits"] == len(demo["needs"]), "the gate of a home's file has its default"
    assert len(demo["waiting"]) == 4 and [one["kind"] for one in demo["proceeds"]] == ["gate"]
    steps = [one["step"] for one in demo["tasks"]]
    assert shown["steps"] == {key: steps.count(key) for key in built.STEP if key in steps}
    assert shown["steps"] == {
        "queued": 3,
        "running": 1,
        "gate": 1,
        "second": 1,
        "check": 1,
        "rebase": 1,
        "hold": 1,
    }
    assert (shown["open"], shown["merged"]) == (9, len(demo["merged"]))
    assert shown["health"]["bus"] == {"outbox": 2, "failed_wakes": 0, "last_error": ""}
    assert shown["health"]["threads"] == 0
    assert "attic" not in json.dumps(stack)


def test_the_homes_off_the_bus_are_the_machines_and_on_no_projects_row(tmp_path, monkeypatch):
    """The machine lists, as names, the homes the last pass found with no project. It leaves
    out a name that is no string."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["homes_off_bus"] = ["firstmate", "LittleRamPantries", {"name": "not a name"}]
    scene.write("status.json", status, scene.state_dir)
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    off = ["firstmate", "LittleRamPantries"]
    assert stack["machine"]["jbus"]["status"]["homes_off_bus"] == off
    assert demo["jbus"]["status"]["homes_off_bus"] == off
    assert all("homes_off_bus" not in json.dumps(one) for one in stack["projects"])


def test_a_scratch_home_is_on_the_machine_with_its_thread_and_has_no_lane(tmp_path, monkeypatch):
    """A scratch home is on the machine row with its home thread. It has no queue, so the
    words that jbus keeps for it place it in no project's lane."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["scratch"] = {"scratch": {"project_id": "mcp:no-project", "home_thread": "mcp:t"}}
    scene.write("status.json", status, scene.state_dir)
    (scene.state_dir / "scratch").mkdir()
    scene.write("words.json", [], scene.state_dir / "scratch")
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    shown = [{"name": "scratch", "home_thread": "mcp:t"}]
    assert stack["machine"]["jbus"]["status"]["scratch"] == shown
    assert demo["jbus"]["status"]["scratch"] == shown
    assert "scratch" not in [one["name"] for one in stack["projects"]]


def test_a_fault_of_the_machine_is_said_once_on_the_machine_and_on_no_projects_row(
    tmp_path, monkeypatch
):
    """The room check does not run, and the view cannot read `status.json`. The machine says
    both. Each project's page still lists them, and no row of the overview counts them."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    room = scene.bin / "room.sh"
    room.write_text("LOAD=200\nCPU=40\nMEMORY=6\nPRESSURE=10\nSLOTS=85\nCUSHION=85\nexit 3\n")
    monkeypatch.setattr(room_panel, "ROOM", room)
    (scene.state_dir / "status.json").write_text("{not json")
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert stack["machine"]["room"]["answer"] == "unknown"
    assert stack["machine"]["unwell"] == [{"name": "status.json", "state": "unreadable"}]
    assert "the room check did not run" in [one["line"] for one in demo["blind"]]
    assert {"name": "status.json", "by": "jbus"} | {"state": "unreadable"} in [
        {key: one[key] for key in ("name", "by", "state")} for one in demo["sources"]
    ]
    by = {one["name"]: one["health"] for one in stack["projects"]}
    assert (by["demo"]["blind"], by["demo"]["unwell"]) == (1, [])
    assert by["larder"]["blind"] == 1
    assert all(
        "status.json" not in [one["name"] for one in health["unwell"]] for health in by.values()
    )


def test_the_stack_runs_the_machines_checks_once_however_many_projects(tmp_path, monkeypatch):
    """For an answer of `/stack.json`, the server asks systemd, the room script and the
    runner units once, with three projects as with one. It asks GitHub for the runs once
    for each repo, then keeps them: a second answer within the minute asks GitHub nothing."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    calls = scene.root / "machine.calls"
    scene.script(
        "systemctl",
        f'printf "systemctl %s\\n" "$2" >> {calls}\n'
        'case "$2" in\n'
        f"list-units) cat {scene.root}/runners.json ;;\n"
        f"*) cat {scene.root}/systemctl.txt ;;\nesac\n",
    )
    room = scene.bin / "room.sh"
    limits = "LOAD=200\nCPU=40\nMEMORY=6\nPRESSURE=10\nSLOTS=85\nCUSHION=85\n"
    room.write_text(f'{limits}echo room >> {calls}\necho "go: there is room"\n')
    monkeypatch.setattr(room_panel, "ROOM", room)
    served = Served(scene)
    try:
        served.json("/stack.json")
        assert sorted(calls.read_text().splitlines()) == [
            "room",
            "systemctl list-units",
            "systemctl show",
        ]
        runs = [one for one in scene.asked() if "actions/runs" in one]
        assert sorted(runs) == [
            "api repos/acme/demo/actions/runs?per_page=40",
            "api repos/acme/pantry/actions/runs?per_page=40",
        ]
        calls.write_text("")
        served.json("/stack.json")
        assert len(calls.read_text().splitlines()) == 3
        assert len([one for one in scene.asked() if "actions/runs" in one]) == 2
    finally:
        served.close()


def test_the_checks_are_told_apart_once_by_the_server_for_the_card_and_the_overview():
    def run(branch, state, name="check"):
        return {"branch": branch, "state": state, "name": name}

    runs = [
        run("a", "failure"),
        run("a", "success"),
        run("b", "failure"),
        run("b", "timed_out", "lint"),
        run("c", "in_progress"),
        run("d", "queued"),
        run("d", "requested", "lint"),
    ]
    assert checks_panel.tally(runs) == {"running": [4], "waiting": [5, 6], "failed": [2]}


def test_the_runs_that_ended_badly_are_counted_by_the_server_in_githubs_words(scene, served):
    scene.github(
        runs=[
            ("a", "completed", "failure"),
            ("a", "completed", "timed_out", "lint"),
            ("b", "completed", "startup_failure"),
            ("b", "completed", "cancelled"),
            ("c", "completed", "success"),
            ("c", "in_progress", None),
        ]
    )
    assert served.json("/state.json?project=demo")["checks"]["ended"] == 3


def test_a_retired_project_is_never_read_and_a_link_to_it_finds_nothing(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    retired = stacked(scene)
    (retired / "queue.json").chmod(0)
    served = Served(scene)
    try:
        assert "attic" not in served.ask("/stack.json")[2]
        assert served.ask("/state.json?project=attic")[0] == 404
        assert served.ask("/state.json?project=../jbus-retired/attic")[0] == 404
    finally:
        served.close()
        (retired / "queue.json").chmod(0o644)


def test_an_answer_names_its_project_and_goes_to_that_projects_state_alone(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    number = asks(scene)
    pantry = scene.state_dir / "pantry"
    served = Served(scene)
    try:
        for path in ("/answer", "/answer?project=", "/answer?project=attic"):
            assert served.write({"numbers": [number]}, path=path)[0] == 404
        assert kept(scene.state)[number].answer is None
        assert served.write({"numbers": [number]}, path="/answer?project=pantry")[0] == 409
        assert not questions.path(pantry).exists()
        status, said = served.write({"numbers": [number]}, path="/answer?project=demo")
        assert (status, [one["number"] for one in said["closed"]]) == (200, [number])
        assert kept(scene.state)[number].answer is not None
    finally:
        served.close()
