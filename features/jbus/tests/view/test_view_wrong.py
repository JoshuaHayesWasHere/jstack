"""What is wrong, across the projects: `/stack.json` has one list of it, each entry with its
subject, cause, since when and where, and one cause that several projects share is one entry
that names them. Each need names the row or question it is about."""

import json

from jbus.view.state import iso
from view.scene import NOW, Scene, Served, ago, out, stacked

STALL = (
    "stall oat-spoon: #12 is as short as it was 10 passes after its crew was told, at "
    "0123456789ab, it has no review yet; its crew's thread is mcp:crew: oat-spoon"
)
HUNG = 'stall jam-jar: thread "crew: jam-jar" has written nothing for 25 minutes'
DOWN = "HTTP Error 502: Bad Gateway"


def stack(scene):
    served = Served(scene)
    try:
        return served.json("/stack.json")
    finally:
        served.close()


def found(given):
    return sorted((one["kind"], one["subj"]) for one in given["wrong"])


def idle(number, reason="it has no review yet"):
    """An entry of `expedite.json` for a crew that was told and has not acted since."""
    head = "0123456789ab" * 3 + "0123"
    return {"passes": 9, "head": head, "reason": reason, "number": number, "told": 3, "idle": 6}


def troubled(scene):
    """A thread in every liveness, a failed run of CI, a stall of a row that has not moved
    since, and two pull requests whose crews were told what they lack: one of them stalled
    too, and the other only idles."""
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar", "hung", minutes=25, queued=2),
            out("crew: oat-milk", "quiet", minutes=8),
            out("review: oat-spoon"),
            out("scout: look", "waiting", minutes=90),
            out("crew: rye-loaf", "ended", "completed", minutes=40),
            out("home: demo", "unknown"),
        ],
    )
    scene.github([("oat-bowl", "completed", "success"), ("oat-milk", "completed", "failure")])
    scene.events(
        ("merged", "user", "rye-loaf", "merged 9 rye-loaf", 40),
        ("expedite", "quiet", "oat-bowl", "expedite oat-bowl: told the crew", 30),
        ("expedite", "quiet", "oat-spoon", "expedite oat-spoon: told the crew", 28),
        ("stall", "user", "jam-jar", HUNG, 7),
        ("stall", "quiet", "oat-spoon", STALL, 6),
    )
    scene.write("expedite.json", {"oat-bowl": idle(11), "oat-spoon": idle(12)})


def test_each_wrong_thing_of_a_scene_is_in_the_list_once(tmp_path, monkeypatch):
    """A hung and a quiet thread are wrong, and a thread at work, waiting, ended or not known
    is not. The hung thread's stall is the thread's entry, and the pull request that stalled is
    one entry, the stall's."""
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    given = stack(scene)
    assert found(given) == [
        ("ci", "oat-milk"),
        ("idle", "oat-bowl"),
        ("stall", "oat-spoon"),
        ("thread", "crew: jam-jar"),
        ("thread", "crew: oat-milk"),
    ]
    by = {one["subj"]: one for one in given["wrong"]}
    assert by["crew: jam-jar"]["since"] == iso(ago(minutes=25))
    assert by["oat-milk"]["since"] == iso(ago(minutes=29))
    assert by["oat-spoon"]["since"] == iso(ago(minutes=6))
    assert by["oat-bowl"]["since"] == iso(ago(minutes=30))
    assert "no review" in by["oat-spoon"]["cause"]
    for one in given["wrong"]:
        assert one["cause"]
        assert [(place["project"], place["home"]) for place in one["where"]] == [("demo", "")]
        assert one["where"][0]["open"].startswith("#/demo/")


def test_a_stall_stands_until_its_row_moves_or_leaves(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    scene.moves(("oat-spoon", "pr", "pr", 2))
    assert ("stall", "oat-spoon") not in found(stack(scene))
    scene.moves(("oat-spoon", "pr", "pr", 9))
    assert ("stall", "oat-spoon") in found(stack(scene))
    table = json.loads((scene.state / "queue.json").read_text())
    scene.queue([one for one in table if one["slug"] != "oat-spoon"])
    assert ("stall", "oat-spoon") not in found(stack(scene))


def test_a_crew_that_acted_or_left_the_hold_to_the_user_is_not_idle(tmp_path, monkeypatch):
    """An entry nobody was told of, or whose hold is the user's, is no idle pull request: the
    first is not late yet, and the second is a need."""
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    untold = {key: value for key, value in idle(11).items() if key not in ("told", "idle")}
    scene.write("expedite.json", {"oat-bowl": untold, "oat-spoon": idle(12) | {"users": True}})
    assert [kind for kind, _ in found(stack(scene))].count("idle") == 0


def test_one_cause_across_four_projects_is_one_entry_naming_them(tmp_path, monkeypatch):
    """The live case: every project's wakes fail on the same route, which the overview drew
    as four reds."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    (scene.state_dir / "cellar").mkdir()
    (scene.state_dir / "cellar" / "queue.json").write_text("[]")
    status = json.loads((scene.state_dir / "status.json").read_text())
    for name in ("demo", "pantry", "larder", "cellar"):
        status["projects"][name] = {"failed_wakes": 3, "last_error": DOWN, "outbox": 4}
    scene.write("status.json", status, scene.state_dir)
    given = stack(scene)
    assert sum(1 for one in given["projects"] if one["broken"]) == 4
    (bus,) = [one for one in given["wrong"] if one["kind"] == "bus"]
    names = sorted(place["project"] for place in bus["where"])
    assert names == ["cellar", "demo", "larder", "pantry"]


def test_a_file_never_had_is_not_wrong_and_one_that_cannot_be_read_is(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    for name in ("ci.jsonl", "ci-prs.jsonl", "stall.json"):
        (scene.state / name).unlink()
    assert stack(scene)["wrong"] == []
    (scene.state / "checks.json").write_text("{not json")
    (one,) = stack(scene)["wrong"]
    assert (one["kind"], one["subj"]) == ("source", "checks.json")
    written = (scene.state / "checks.json").stat().st_mtime
    assert one["since"] == iso(NOW.fromtimestamp(written, NOW.tzinfo))


def test_main_red_is_wrong_since_main_moved_there(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    red = "badc0de" + "1" * 33
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": red, "check": "failed"})
    (one,) = stack(scene)["wrong"]
    assert (one["kind"], one["subj"], one["since"]) == ("main", "main", iso(ago(minutes=12)))
    assert "badc0de" in one["cause"]


def test_each_need_names_the_row_or_question_it_is_about(tmp_path, monkeypatch):
    """A row at a gate reads with its slug, not only its question, and a question of no row
    with its number."""
    scene = Scene(tmp_path, monkeypatch)
    given = stack(scene)
    subjects = {one["key"]: one["subj"] for one in given["needs"] + given["proceeds"]}
    assert subjects["row:jam-lid"] == "jam-lid"
    assert subjects["approve:tea-kettle"] == "tea-kettle"
    assert subjects["#14"] == "oat-honey"
    gate = next(one for one in given["needs"] + given["proceeds"] if one["kind"] == "gate")
    assert gate["subj"] == "question 4"


def test_a_stall_of_a_head_no_record_counts_now_and_one_of_a_leftover_are_not_wrong(
    tmp_path, monkeypatch
):
    """A stall that names a head stands while jbus still counts that head. A stall of a
    leftover is a need, and is not drawn again here."""
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    moved = idle(12) | {"head": "fedcba987654" * 3 + "fedc"}
    scene.write("expedite.json", {"oat-spoon": moved})
    assert ("stall", "oat-spoon") not in found(stack(scene))
    scene.write("expedite.json", {})
    left = "stall oat-spoon: it ended with something left, and its home did not close it; left: x"
    scene.events(("stall", "quiet", "oat-spoon", left, 6))
    assert ("stall", "oat-spoon") not in found(stack(scene))


def test_a_red_ci_of_main_in_each_project_is_an_entry_each(tmp_path, monkeypatch):
    """Only what one machine shares merges: each project's CI is its own."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    scene.github([("main", "completed", "failure")])
    ci = [one for one in stack(scene)["wrong"] if one["kind"] == "ci"]
    assert sorted(one["where"][0]["project"] for one in ci) == ["demo", "larder", "pantry"]
    assert all(len(one["where"]) == 1 for one in ci)
