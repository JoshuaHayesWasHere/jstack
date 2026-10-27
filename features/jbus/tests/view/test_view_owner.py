"""Each fault the view finds has an owner, and only a fault no agent can fix is the user's.

`state.wrongs` gives each entry its `owner` (`state.OWNERS`, one rule for each kind) and what
that owner was told and when (`fixing`). `/stack.json`'s `wrong`, the band and the since line
hold only the user's entries. The rest are on their row, on the board and in the task drawer,
as fixing by their owner."""

import json

import pytest

from jbus.view import state as built
from jbus.view.github import GitHub
from view.scene import NOW, Scene, Served, ago, briefed, iso, out, row, table
from view.test_view_wrong import STALL, idle
from view.walk import sources

RED = "badc0de" + "1" * 33
FIX = "main-red-badc0de11111"
UNAUTHORIZED = "HTTP Error 401: Unauthorized"
DOWN = "HTTP Error 502: Bad Gateway"


def stack(scene):
    served = Served(scene)
    try:
        return served.json("/stack.json")
    finally:
        served.close()


def read(scene):
    """The project as the server reads it, with GitHub's runs from the stand-in `gh`."""
    github = GitHub(lambda: NOW)
    github.patience = 20
    return built.Read(sources(scene), scene.name, NOW, github.runs)


def wrongs(scene):
    return built.wrongs(read(scene))


def board(scene):
    return {
        one["slug"]: one
        for card in read(scene).asked("board")["data"]["homes"]
        for one in card["workers"]
    }


def told(slug, thread, template, minutes, key=""):
    """One line of `outbox.jsonl`: a message the outbox sent `minutes` ago."""
    return {
        "at": iso(ago(minutes=minutes)),
        "thread": thread,
        "row": slug,
        "template": template,
        "needs": "act",
        "key": key or f"{template}|{slug}|d00dd00dd00d",
        "went": "sent",
        "rule": "",
    }


def crewed(scene):
    """The scene's table, with a crew's thread on the pull request whose check failed."""
    scene.github([("oat-bowl", "completed", "success"), ("oat-milk", "completed", "failure")])
    scene.queue(
        [
            row("oat-milk", "pr", pr="#13", thread="mcp:crew-oat-milk")
            if one["slug"] == "oat-milk"
            else one
            for one in table()
        ]
    )


def status(scene, **project):
    said = json.loads((scene.state_dir / "status.json").read_text())
    said["projects"][scene.name] |= project
    scene.write("status.json", said, scene.state_dir)


def silent(scene, source):
    said = json.loads((scene.state_dir / "pass.json").read_text())
    scene.write("pass.json", said | {"silent": {scene.name: source}}, scene.state_dir)


def test_a_red_check_of_a_crews_pull_request_is_the_crews_and_not_in_the_band(
    tmp_path, monkeypatch
):
    """The live case of 2026-10-27: a red check on a crew's pull request, the crew already woken
    by jbus's failed-check message, was drawn as the user's."""
    scene = Scene(tmp_path, monkeypatch)
    crewed(scene)
    scene.lines("outbox.jsonl", [told("oat-milk", "mcp:crew-oat-milk", "failed", 20)])
    (ci,) = [one for one in wrongs(scene) if one["kind"] == "ci"]
    assert (ci["subj"], ci["owner"], ci["row"]) == ("oat-milk", "crew of oat-milk", "oat-milk")
    assert ci["fixing"] == {"told": iso(ago(minutes=20)), "what": "failed"}
    assert ci["since"] == iso(ago(minutes=29))
    given = stack(scene)
    assert [one for one in given["wrong"] if one["kind"] == "ci"] == []
    assert [one for one in given["glance"]["items"] if one["tier"] == "wrong"] == []
    assert board(scene)["oat-milk"]["fixing"] == {
        "owner": "crew of oat-milk",
        "told": iso(ago(minutes=20)),
    }


REDS = {
    "cleanup-fl-msg-red-rows": ("#549", "mcp:ed9e786d", 15),
    "fl-msg-go-as-gate": ("#550", "mcp:a86d154f", 20),
    "fl-sub-shared-leaf": ("#551", "mcp:6989be7f", None),
    "fl-msg-scope-stop": ("#553", "mcp:561b5cf7", None),
}


def test_the_four_crew_reds_of_2026_10_27_are_each_on_its_row_and_none_is_the_users(
    tmp_path, monkeypatch
):
    """#549, #550, #551 and #553 were red on 2026-10-27, each with its crew on it, and the view
    put all four to the user. Replayed: `.wrong` holds none of them, the band is calm, and each
    is on its row as fixing by its crew. `REDS` gives each its pull request, its crew's thread
    and how long ago jbus told the crew of its red check, for the two that the day's events say
    were told (`failed ...: told the crew`)."""
    scene = Scene(tmp_path, monkeypatch)
    (scene.home / "home-id").write_text("mcp:root\n")
    scene.github([(slug, "completed", "failure") for slug in REDS])
    scene.queue([row(slug, "pr", pr=pr, thread=thread) for slug, (pr, thread, _) in REDS.items()])
    scene.lines(
        "outbox.jsonl",
        [
            told(slug, thread, "failed", minutes)
            for slug, (_, thread, minutes) in REDS.items()
            if minutes
        ],
    )
    reds = {one["subj"]: one for one in wrongs(scene) if one["kind"] == "ci"}
    assert {slug: one["owner"] for slug, one in reds.items()} == {
        slug: f"crew of {slug}" for slug in REDS
    }
    given = stack(scene)
    assert given["wrong"] == []
    assert given["glance"]["calm"]
    cards = board(scene)
    assert {slug: cards[slug]["fixing"] for slug in REDS} == {
        slug: {"owner": f"crew of {slug}", "told": iso(ago(minutes=minutes)) if minutes else None}
        for slug, (_, _, minutes) in REDS.items()
    }


def test_a_red_main_with_its_fix_row_queued_is_the_fix_rows_and_not_the_users(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": RED, "check": "failed"})
    scene.queue([*table(), row(FIX, "running", thread="mcp:crew-fix")])
    scene.moves((FIX, "queued", "launched", 10))
    (main,) = [one for one in wrongs(scene) if one["kind"] == "main"]
    assert (main["owner"], main["row"]) == (f"crew of {FIX}", FIX)
    assert main["fixing"] == {"told": iso(ago(minutes=10)), "what": "the main-red row"}
    assert [one for one in stack(scene)["wrong"] if one["kind"] == "main"] == []


def test_a_bus_whose_webhook_github_refuses_with_401_is_the_users_and_in_the_band(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    status(scene, failed_wakes=3, last_error=UNAUTHORIZED)
    given = stack(scene)
    (bus,) = [one for one in given["wrong"] if one["kind"] == "bus"]
    assert (bus["owner"], bus["fixing"]) == ("user", None)
    (item,) = [one for one in given["glance"]["items"] if one["tier"] == "wrong"]
    assert (item["kind"], item["cause"]) == ("bus", f"wakes to its webhook fail: {UNAUTHORIZED}")
    assert not given["glance"]["calm"]


def test_the_band_is_calm_while_every_fault_has_an_agent_owner(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    scene.queue([row("jam-jar", "running", thread="mcp:0000")])
    scene.waiting([])
    (scene.home / "gates.md").unlink()
    scene.passed(20, threads=[out("crew: jam-jar", "hung", minutes=25)])
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": RED, "check": "failed"})
    status(scene, failed_wakes=3, last_error=DOWN)
    (scene.home / "home-id").write_text("mcp:root\n")
    assert {one["owner"] for one in wrongs(scene)} == {"root home"}
    given = stack(scene)
    assert given["wrong"] == []
    assert given["glance"]["calm"]


def _main(scene):
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": RED, "check": "failed"})


def _ci_of_no_row(scene):
    scene.github([("dependabot/pip/x", "completed", "failure")])


def _ci_unread(scene):
    (scene.root / "runs.json").write_text("{not json")


def _bus_down(scene):
    status(scene, failed_wakes=3, last_error=DOWN)


def _bus_refused(scene):
    status(scene, failed_wakes=3, last_error=UNAUTHORIZED)


def _bus_home_thread(scene):
    status(scene, failed_wakes=3, last_error=DOWN, wake="home")


def _source(scene):
    (scene.state / "checks.json").write_text("{not json")


def _unasked_github(scene):
    silent(scene, "GitHub")


def _unasked_t3(scene):
    silent(scene, "T3 Code")


def _thread(scene):
    briefed(scene, jam_jar="pantry-shelf")
    scene.passed(20, threads=[out("crew: jam-jar", "hung", minutes=25)])


def _stall(scene):
    scene.write("expedite.json", {"oat-spoon": idle(12)})
    scene.events(("stall", "quiet", "oat-spoon", STALL, 6))


def _stall_gated(scene):
    """jam-lid waits on a gate, which holds only for a case of `gates.md`."""
    scene.events(("stall", "quiet", "jam-lid", "stall jam-lid: nobody has acted on it", 6))


def _stall_capped(scene):
    capped = f"stall oat-spoon: claudeAgent is capped until {iso(ago(minutes=-30))}"
    scene.events(("stall", "quiet", "oat-spoon", capped, 6))


def _idle(scene):
    scene.events(("expedite", "quiet", "oat-bowl", "expedite oat-bowl: told the crew", 30))
    scene.write("expedite.json", {"oat-bowl": idle(11)})


@pytest.mark.parametrize(
    ("made", "kind", "owner"),
    [
        (_main, "main", "root home"),
        (_ci_of_no_row, "ci", "root home"),
        (_ci_unread, "ci", "root home"),
        (_bus_down, "bus", "root home"),
        (_bus_refused, "bus", "user"),
        (_bus_home_thread, "bus", "user"),
        (_source, "source", "root home"),
        (_unasked_github, "unasked", "root home"),
        (_unasked_t3, "unasked", "user"),
        (_thread, "thread", "home pantry-shelf"),
        (_stall, "stall", "root home"),
        (_stall_gated, "stall", "user"),
        (_stall_capped, "stall", "user"),
        (_idle, "idle", "root home"),
    ],
)
def test_each_row_of_the_owner_table_names_who_fixes_its_kind(
    tmp_path, monkeypatch, made, kind, owner
):
    """Each row of `state.OWNERS`: a fault of the project or the machine is the root home's, a
    fault of a row is its home's, and the user's only where no agent can fix it: a token GitHub
    refuses, T3 Code not answering, a fix that is a case of `gates.md`, or a cap."""
    scene = Scene(tmp_path, monkeypatch)
    (scene.home / "home-id").write_text("mcp:root\n")
    made(scene)
    found = [one for one in wrongs(scene) if one["kind"] == kind]
    assert found and {one["owner"] for one in found} == {owner}
    shown = [one for one in stack(scene)["wrong"] if one["kind"] == kind]
    assert bool(shown) == (owner == "user")


def test_a_home_with_no_thread_to_tell_leaves_the_fault_the_users(tmp_path, monkeypatch):
    """An agent owner is one that can be told: with no root home, nobody is."""
    scene = Scene(tmp_path, monkeypatch)
    _source(scene)
    (one,) = [one for one in wrongs(scene) if one["kind"] == "source"]
    assert one["owner"] == "user"
