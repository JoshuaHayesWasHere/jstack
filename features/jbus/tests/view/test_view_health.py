"""What is broken in a project, on the overview's row: each reason clears once its source
works again, and each says since when."""

import json

from jbus import alert
from jbus.view.state import iso
from view.scene import NOW, Scene, Served, ago, stacked

DROPPED = "the config has no webhook_url"
DOWN = "T3 Code did not answer"


def answers(scene):
    served = Served(scene)
    try:
        return served.json("/stack.json"), served.json(f"/state.json?project={scene.name}")
    finally:
        served.close()


def row(stack, name="demo"):
    return next(one for one in stack["projects"] if one["name"] == name)


def at_home(scene, error, streak=0):
    """The project's `wake` is `home`, as a pass leaves it: the status file and the home
    thread's `wake.json` hold the error of the home thread's last wake, and `streaks.json`
    the streak of its failed wakes. The project's own `wake.json` still holds the error its
    webhook gave last, before the route was dropped."""
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"][scene.name] |= {
        "wake": "home",
        "failed_wakes": streak,
        "last_error": error,
        "outbox": 0,
    }
    status["stranded"] = {}
    scene.write("status.json", status, scene.state_dir)
    old = {"began": True, "last_error": DROPPED, "posted": NOW.timestamp() - 6 * 3600}
    scene.write("wake.json", old)
    (scene.state / "home-thread").mkdir(exist_ok=True)
    said = {"last_error": error, "posted": NOW.timestamp() - 60}
    scene.write("wake.json", said, scene.state / "home-thread")
    key = alert.home(scene.name)
    since = {"key": key, "count": streak, "since": iso(ago(minutes=25)), "alerted": False}
    scene.write("streaks.json", {key: since} if streak else {}, scene.state_dir)


def test_a_dropped_routes_old_error_is_no_fault_of_the_route_in_effect(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    at_home(scene, "")
    stack, state = answers(scene)
    assert row(stack)["broken"] == []
    assert state["bus"]["last_error"] == ""


def test_a_failed_wake_is_red_since_its_streak_began_and_clears_once_one_goes(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    at_home(scene, DOWN, streak=3)
    stack, _ = answers(scene)
    assert row(stack)["broken"] == [
        {"what": "bus failed to send", "open": "bus", "since": iso(ago(minutes=25))}
    ]
    at_home(scene, "")
    stack, _ = answers(scene)
    assert row(stack)["broken"] == []


def test_a_source_never_had_is_not_unread_and_one_that_cannot_be_read_is(tmp_path, monkeypatch):
    """`ci.jsonl` and `stall.json` the project never had are no fault. `checks.json` that it
    has and cannot read is, since it was last written, and it clears once it reads again."""
    scene = Scene(tmp_path, monkeypatch)
    for name in ("ci.jsonl", "ci-prs.jsonl", "stall.json"):
        (scene.state / name).unlink()
    stack, state = answers(scene)
    assert row(stack)["broken"] == []
    assert {one["name"]: one["state"] for one in state["sources"]}["ci.jsonl"] == "missing"
    (scene.state / "checks.json").write_text("{not json")
    stack, _ = answers(scene)
    (reason,) = row(stack)["broken"]
    assert (reason["what"], reason["open"]) == ("1 source unread", "pulse")
    written = (scene.state / "checks.json").stat().st_mtime
    assert reason["since"] == iso(NOW.fromtimestamp(written, NOW.tzinfo))
    scene.write("checks.json", {"aa" * 20: "green"})
    stack, _ = answers(scene)
    assert row(stack)["broken"] == []


def test_main_red_names_its_tip_on_every_row_since_main_moved_there(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    red = "badc0de" + "1" * 33
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": red, "check": "failed"})
    stack, state = answers(scene)
    assert state["main"]["red"] == red
    assert row(stack)["broken"][0] == {
        "what": "main red badc0de",
        "open": "pulse",
        "since": iso(ago(minutes=12)),
    }
    scene.write("main.json", {"at": iso(ago(minutes=2)), "main": "c0ffee" * 6 + "abcd"})
    stack, state = answers(scene)
    assert state["main"]["red"] == ""
    assert row(stack)["broken"] == []


def test_a_red_tip_main_moved_past_is_red_since_a_time_not_known(tmp_path, monkeypatch):
    """`at` is when main moved to its tip. Once main moved past the red tip, `at` is the later
    move, which says nothing of when the red began."""
    scene = Scene(tmp_path, monkeypatch)
    red, later = "badc0de" + "1" * 33, "c0ffee" * 6 + "abcd"
    kept = {"at": iso(ago(minutes=3)), "main": later, "check": "pending", "broken": red}
    scene.write("main.json", kept)
    stack, _ = answers(scene)
    assert row(stack)["broken"][0] == {"what": "main red badc0de", "open": "pulse", "since": None}


def test_ci_that_failed_is_red_since_its_oldest_failed_run(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    scene.github([("oat-bowl", "completed", "success"), ("oat-milk", "completed", "failure")])
    stack, _ = answers(scene)
    assert row(stack)["broken"] == [
        {"what": "CI 1 failed", "open": "checks", "since": iso(ago(minutes=29))}
    ]


def test_the_passes_that_failed_in_a_row_are_the_machines(tmp_path, monkeypatch):
    """The count is the `pass` streak of `streaks.json`, which `jbus alarm` writes after each
    pass that raised, so it is never a pass behind the status file."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    stack, state = answers(scene)
    assert stack["machine"]["jbus"]["failed"] == state["jbus"]["failed"] == 0
    streak = {"key": alert.PASS, "count": 4, "since": iso(ago(minutes=4)), "alerted": True}
    scene.write("streaks.json", {alert.PASS: streak}, scene.state_dir)
    stack, state = answers(scene)
    assert stack["machine"]["jbus"]["failed"] == state["jbus"]["failed"] == 4
