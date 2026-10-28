"""The banner of a stopped jbus or a gone server, and the page on a phone."""

import json

import pytest

from view.days import TODAY, lineup
from view.page.browser import BROWSES, LAUNCH, PATIENCE, PHONE, clean, look
from view.scene import NOW, ago

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


PHONE_NEEDS = 520


THUMB = 44


def frozen(seen, since, said):
    """A stopped jbus: the banner, and each drawer saying once how fresh it is."""
    clean(seen)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended " + since)
    assert said in seen["banner"]
    assert seen["header"]["machine"] == {
        "text": "jbus stopped",
        "cls": "machw bad",
        "href": "#/demo/pulse",
    }
    assert seen["header"]["read"].startswith("Updated "), "jbus stopped, the server did not"
    drawers = {one["target"]: one for one in seen["opened"]}
    assert drawers["pulse"]["title"] == "jbus has not passed"
    for live in ("room", "checks"):
        assert drawers[live]["fresh"].endswith(" by the server itself, also while jbus is stopped")
    assert drawers["bus"]["fresh"] == f"As the last pass left it at {since}: jbus has stopped"
    assert drawers["task:oat-milk"]["fresh"] == drawers["bus"]["fresh"]
    assert "#13 open" in seen["github"]


def stamp(moment):
    return moment.astimezone().strftime("%H:%M:%S")


def test_a_timer_that_is_not_active_shows_the_banner_and_freezes_what_jbus_writes(scene, tmp_path):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, task="oat-milk")
    said = "jbus.timer inactive (dead), jbus.service exit-code, exit 1"
    frozen(seen, stamp(ago(seconds=20)), said)


def test_a_last_pass_more_than_150_s_ago_shows_the_banner_too(scene, tmp_path):
    scene.passed(seconds_ago=400)
    seen = look(scene, tmp_path, task="oat-milk")
    frozen(
        seen, stamp(ago(seconds=400)), "jbus.timer active (waiting), jbus.service success, exit 0"
    )


def test_a_jbus_that_passes_shows_no_banner_and_nothing_frozen(scene, tmp_path):
    seen = look(scene, tmp_path)
    assert (seen["body"], seen["banner"]) == ("", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    assert seen["header"]["stale"] is False


def test_with_the_server_gone_the_page_says_so_after_two_answers_missed(scene, tmp_path):
    seen = look(scene, tmp_path, at=8000, budget=12000, dark_after=1)
    assert (seen["body"], seen["banner"]) == ("", "")
    seen = look(scene, tmp_path, at=12000, budget=16000, dark_after=1, task="oat-milk")
    clean(seen)
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer last answer ")
    assert "2 answers missed" in seen["banner"]
    read = NOW.astimezone().strftime("%H:%M")
    assert seen["header"]["read"] == f"Stale since {read}", "the time of the last answer"
    assert seen["header"]["stale"] is True
    assert "GitHub cannot be asked" in seen["github"]
    assert len(seen["prog"]) == 9 - 3, "the three tasks in Needs you are not drawn again"


def test_a_server_that_never_answered_is_said_too(scene, tmp_path):
    seen = look(scene, tmp_path, at=40000, budget=44000, dark_after=0)
    assert seen["errors"] == []
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer")


def test_on_a_phone_the_page_is_one_column_and_every_target_takes_a_thumb(scene, tmp_path):
    open_rows = lineup(scene, TODAY)
    screen = (PHONE[0], PHONE[1] + PHONE_NEEDS)
    seen = look(scene, tmp_path, budget=9000, screen=screen)
    opened = clean(seen, screen)
    assert {row["open"] for row in seen["prog"]} <= opened
    assert len([row for row in seen["prog"] if row["slug"] in open_rows]) == 28 - 4
    assert all(
        row["box"][0] >= 0 and row["box"][0] + row["box"][2] <= screen[0] for row in seen["prog"]
    )
    assert min(row["box"][3] for row in seen["prog"]) >= THUMB
    assert (seen["small"], seen["cut"]) == ([], [])
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *screen)}
    assert all(one["closed"] for one in seen["opened"])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []


@pytest.mark.parametrize("github", ["names", "down"])
def test_on_a_phone_a_stopped_jbus_with_unwell_sources_and_long_checks_is_whole(
    scene, tmp_path, github
):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    (scene.state / "queue.json").write_text("{not json")
    (scene.state / "main.json").unlink()
    (scene.state / "stall.json").unlink()
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"][scene.name] |= {"failed_wakes": 3, "outbox": 9}
    scene.write("status.json", status, scene.state_dir)
    if github == "down":
        scene.script("gh", "exit 1\n")
    else:
        long = "a-branch-with-a-long-name-that-goes-on"
        scene.github(
            runs=[
                (f"{long}-one", "in_progress", None),
                (f"{long}-two", "in_progress", None),
                (f"{long}-three", "queued", None),
                (f"{long}-four", "completed", "failure"),
            ]
        )
    screen = (PHONE[0], PHONE[1] + PHONE_NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    clean(seen, screen)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended ")
    assert seen["header"]["machine"]["text"] == "jbus stopped"
    assert (seen["small"], seen["cut"]) == ([], [])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *screen)}
