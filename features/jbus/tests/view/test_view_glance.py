"""The band at the top of `#/`: in one look, what is wrong, then what waits on the user, then
whether the work moves. `/stack.json` has it as `glance`: its items in the order the band draws
them, each with its subject, its cause and since when, and `calm` where nothing is wrong and
nothing waits on the user, when the band is the one line that says the work moves."""

from datetime import timedelta

import jsettings
from jbus.view import state as built
from jbus.view.state import iso
from view.scene import NOW, Scene, Served, ago, et, out, row
from view.test_view_wrong import STALL, idle
from view.walk import runs, sources

RED = "badc0de" + "1" * 33


def stack(scene):
    served = Served(scene)
    try:
        return served.json("/stack.json")
    finally:
        served.close()


def quiet(scene):
    """One row at work, nothing at a gate, no question and every source as a day of runs
    leaves it."""
    scene.queue([row("jam-jar", "running", thread="mcp:0000")])
    scene.waiting([])
    (scene.home / "gates.md").unlink()
    for name in ("ci.jsonl", "ci-prs.jsonl", "stall.json"):
        (scene.state / name).unlink()
    scene.passed(20, threads=[out("crew: jam-jar", minutes=1)])


def troubled(scene):
    """The quiet scene with a red main, a stall, a hung thread and two rows that wait for the
    user's approval."""
    quiet(scene)
    scene.queue(
        [
            row("tea-kettle", approved="", why="not approved", since=et(ago(minutes=50))),
            row("tea-pot", approved="", why="not approved", since=et(ago(minutes=20))),
            row("jam-jar", "running", thread="mcp:0000"),
            row("oat-spoon", "pr", pr="#12", checks="passed", why="wait: it has no review yet"),
        ]
    )
    scene.passed(20, threads=[out("crew: jam-jar", "hung", minutes=25)])
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": RED, "check": "failed"})
    scene.events(("stall", "quiet", "oat-spoon", STALL, 6))
    scene.write("expedite.json", {"oat-spoon": idle(12)})


def drawn(glance):
    return [(one["tier"], one["kind"], one["subj"]) for one in glance["items"]]


def test_wrong_comes_first_then_what_waits_on_you_then_whether_it_moves(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    glance = stack(scene)["glance"]
    assert drawn(glance) == [
        ("wrong", "thread", "crew: jam-jar"),
        ("wrong", "main", "main"),
        ("wrong", "stall", "oat-spoon"),
        ("yours", "approve", "2 approvals"),
        ("moving", "moving", "moving"),
    ]
    assert glance["calm"] is False
    by = {one["subj"]: one for one in glance["items"]}
    assert by["crew: jam-jar"]["since"] == iso(ago(minutes=25))
    assert by["main"]["since"] == iso(ago(minutes=12))
    assert by["oat-spoon"]["since"] == iso(ago(minutes=6))
    assert by["2 approvals"]["since"] == iso(ago(minutes=50))
    assert "badc0de" in by["main"]["cause"]
    assert "hung" in by["crew: jam-jar"]["cause"]
    assert "no review" in by["oat-spoon"]["cause"]
    assert by["2 approvals"]["cause"] == "tea-kettle, tea-pot"
    assert (by["2 approvals"]["verb"], by["2 approvals"]["count"]) == ("Approve 2", 2)
    for one in glance["items"]:
        assert one["cause"] and one["since"] and one["open"].startswith("#/")


def test_the_verdict_names_motion_and_the_top_cause_with_its_age(tmp_path, monkeypatch):
    """A red main holds every merge, so it is the top cause though a hung thread is older."""
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    verdict = stack(scene)["glance"]["verdict"]
    assert verdict["top"] == {
        "tier": "wrong",
        "kind": "main",
        "subj": "main",
        "cause": f"red at {RED[:7]}",
        "since": iso(ago(minutes=12)),
    }
    assert (verdict["motion"], verdict["last_merge"]) == ("moving", iso(ago(minutes=40)))
    assert (verdict["per_hour"], verdict["window"]) == (0.3, 3)


def test_merges_an_hour_count_the_window_and_none_in_it_is_still(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    scene.moves(*((f"rye-{n}", "pr", "merged", minutes) for n, minutes in enumerate((5, 50, 170))))
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["motion"], verdict["per_hour"]) == ("moving", 1.0)
    assert verdict["merges"] == [iso(ago(minutes=m)) for m in (170, 50, 5)]
    scene.moves(("rye-loaf", "pr", "merged", 200))
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["motion"], verdict["per_hour"]) == ("still", 0.0)
    assert verdict["last_merge"] == iso(ago(minutes=200))
    assert verdict["top"]["tier"] == ""


def test_a_merge_before_midnight_counts_in_the_window_after_it(tmp_path, monkeypatch):
    """The window of the verdict crosses the start of the user's day: an hour after midnight,
    a merge ten minutes before it is the last merge and counts in the merges an hour."""
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    midnight = jsettings.load().local(NOW).replace(hour=0, minute=0, second=0, microsecond=0)
    before = iso(midnight - timedelta(minutes=10))
    scene.lines("transitions.jsonl", [{"slug": "rye", "from": "pr", "to": "merged", "at": before}])
    verdict = built.stack(sources(scene), midnight + timedelta(hours=1), runs)["glance"]["verdict"]
    assert (verdict["motion"], verdict["last_merge"]) == ("moving", before)
    assert verdict["per_hour"] == 0.3


def test_a_quiet_machine_is_one_calm_line(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    glance = stack(scene)["glance"]
    assert glance["calm"] is True
    assert drawn(glance) == [("moving", "moving", "moving")]
    (line,) = glance["items"]
    assert line["cause"] == "1 open in 1 project, 1 merged today, 1 thread out"
    assert line["since"] == iso(ago(seconds=20))


def test_jbus_stopped_is_wrong_and_first(tmp_path, monkeypatch):
    """A stopped jbus is the band's own entry: the wrong list leaves it to the band."""
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    scene.timer(active="inactive", sub="dead")
    given = stack(scene)
    assert drawn(given["glance"])[0] == ("wrong", "jbus", "jbus")
    assert given["glance"]["items"][0]["cause"] == "stopped: the timer is not active"
    assert given["glance"]["calm"] is False
    assert all(one["kind"] != "jbus" for one in given["wrong"])


def test_failed_passes_are_wrong_with_their_count(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    since = iso(ago(minutes=4))
    scene.write("streaks.json", {"pass": {"count": 3, "since": since}}, scene.state_dir)
    (first,) = [one for one in stack(scene)["glance"]["items"] if one["tier"] == "wrong"]
    assert (first["kind"], first["cause"], first["since"]) == ("jbus", "3 passes failed", since)
