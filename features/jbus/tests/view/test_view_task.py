"""The tasks of the queue: each on one step of the line, in one state, with one reason."""

import json
import os
import re
from datetime import UTC, datetime, timedelta

import pytest

import jbus
import jsettings
from jbus import queue, record, view, work
from jbus.view import panels
from jbus.view import state as built
from test_jbus_kitchen import NOW as POLLED
from test_jbus_kitchen import Kitchen, complete
from view.scene import (
    GATE,
    JMERGE,
    NAMES,
    NOW,
    PULL,
    ago,
    checked,
    et,
    iso,
    item,
    kinds,
    logged,
    row,
    table,
    tasks,
)


def test_a_queued_row_is_yours_blocked_or_waiting_for_jbus(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert {slug: (found[slug]["step"], found[slug]["who"]) for slug in found if "tea" in slug} == {
        "tea-kettle": ("queued", "user"),
        "tea-cups": ("queued", "dep"),
        "tea-tray": ("queued", "bus"),
    }
    assert found["tea-cups"]["depends"] == [{"slug": "tea-kettle", "state": "queued"}]
    assert found["tea-kettle"]["state"]["say"] == "nobody has approved it"


def test_the_two_rebase_reasons_are_the_rebase_step_and_the_second_pass(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert (found["oat-bowl"]["step"], found["oat-bowl"]["who"]) == ("rebase", "crew")
    assert (found["oat-spoon"]["step"], found["oat-spoon"]["who"]) == ("second", "rev")
    assert found["oat-bowl"]["state"]["say"].startswith("the rebase dropped 2 of main's lines")
    assert found["oat-spoon"]["state"]["say"].startswith("the rebase changed the content after its")


@pytest.mark.parametrize(
    ("why", "step"),
    [
        ("wait: no brief has a Result that names it", "result"),
        ("wait: it has no review yet", "review"),
        ("wait: its findings are not handled: the Result has no Fixed line", "findings"),
        (
            "wait: its fix changed more than the findings named: the second pass is not written",
            "second",
        ),
        ("wait: the rebase changed the content after its review; scoped review of x", "second"),
        ("wait: check has not passed", "check"),
        (
            "wait: main changed a.py after its check started at 20:48 ET; it needs a fresh check",
            "check",
        ),
        ("wait: no proven safety fact at 0123456789ab (x)", "unknown"),
        ("wait: it conflicts with today's main", "rebase"),
        ("wait: it conflicts with its base", "rebase"),
        ("hold: needs user, the rebase dropped 1 of main's lines in src/a.py", "hold"),
        ("wait: its brief says Review: none, so it needs the user's word", "hold"),
        ("wait: a reason nobody has printed before", "unknown"),
        ("", "unknown"),
    ],
)
def test_a_reason_of_jmerge_puts_a_pull_request_on_its_step(scene, served, why, step):
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="passed", why=why)])
    assert tasks(served.json("/state.json?project=demo"))["oat-bowl"]["step"] == step


def test_the_line_has_eleven_steps_and_every_open_row_is_on_one(served):
    state = served.json("/state.json?project=demo")
    assert [one["key"] for one in state["steps"]] == [
        "queued",
        "running",
        "gate",
        "result",
        "review",
        "findings",
        "second",
        "check",
        "rebase",
        "hold",
        "merged",
    ]
    found = tasks(state)
    assert sorted(found) == sorted(one["slug"] for one in table() if one["status"] != "merged")
    assert {one["step"] for one in found.values()} <= {one["key"] for one in state["steps"]}
    assert (found["jam-jar"]["step"], found["jam-lid"]["step"]) == ("running", "gate")
    assert (found["oat-milk"]["step"], found["oat-honey"]["step"]) == ("check", "hold")
    assert [(one["slug"], one["pr"]) for one in state["merged"]] == [("rye-loaf", "#9")]


def test_a_task_says_since_when_it_is_on_its_step_and_how_often_it_came_back(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert found["oat-milk"]["since"] == iso(ago(minutes=4))
    assert found["oat-milk"]["visits"] == 2
    assert [one["step"] for one in found["oat-milk"]["history"]] == ["check", "review", "check"]
    assert (found["oat-bowl"]["since"], found["oat-bowl"]["visits"]) == (iso(ago(minutes=50)), 1)
    assert found["jam-jar"]["since"] == iso(ago(minutes=35))
    assert found["tea-kettle"]["since"] == iso(ago(minutes=50))


def test_each_kind_of_row_is_in_one_state_with_one_reason_and_names_no_other(scene, served):
    expected = kinds(scene)
    rows = json.loads((scene.state / "queue.json").read_text())
    assert {one["status"] for one in rows} == set(queue.STATUSES)
    assert set(expected.values()) == set(work.VALUES) - {
        "removed",
        "done",
        "closed",
        "quiet",
        "unknown",
    }
    state = served.json("/state.json?project=demo")
    found = {one["slug"]: one for one in state["tasks"] + state["ended"]}
    assert {slug: one["state"]["kind"] for slug, one in found.items()} == expected
    unclosed = {"fig-burr", "fig-rind"}
    for slug, one in found.items():
        said, kind = one["state"], expected[slug]
        assert said["name"] == ("Ended, not closed" if slug in unclosed else NAMES[kind])
        assert said["say"] and said["waits"], slug
        assert one["reason"] == said["say"]
        spoken = said["waits"]
        if kind in JMERGE:
            assert said["say"] == JMERGE[kind]
        else:
            spoken += " " + said["say"]
        others = [name for name in NAMES.values() if name not in (said["name"], NAMES[kind])]
        if kind in ("leftover", "closed"):
            others = [name for name in others if name not in ("Merged", "Done")]
        named = [name for name in others if re.search(rf"\b{name}\b", spoken, re.I)]
        assert named == [], (slug, spoken)
    assert found["fig-leaf"]["state"]["waits"] == "fig-seed to merge"
    assert found["fig-jam"]["state"]["waits"] == "a slot"
    assert found["fig-seed"]["state"]["waits"] == found["fig-husk"]["state"]["waits"]
    assert found["fig-husk"]["state"]["waits"] == "your approval"
    assert found["fig-stalk"]["state"]["say"] == "its thread ended early and wrote nothing back"
    assert found["fig-root"]["state"]["say"] == "its thread was settled and wrote nothing"
    assert found["fig-root"]["state"]["waits"].startswith("your word on what is left")
    burr = found["fig-burr"]["state"]
    assert burr["say"] == (
        "it ended with no pull request, and its brief does not say the work is finished: "
        "status: paused"
    )
    assert (burr["waits"], burr["row"]) == ("your word on how it ends", "")
    assert "done" not in burr["say"]


def test_the_tasks_of_state_json_hold_exactly_the_states_of_work_json(scene, served):
    kinds(scene)
    judged = json.loads((scene.state / "work.json").read_text())["work"]
    state = served.json("/state.json?project=demo")
    drawn = {
        one["slug"]: (one["state"]["kind"], one["who"], one["step"])
        for one in state["tasks"] + state["ended"]
    }
    over = {"fig-pod", "fig-tree"}
    assert drawn == {
        one["slug"]: (one["value"], one["who"], one["lane"] or "unknown")
        for one in judged
        if one["slug"] not in over
    }
    rows = {
        one["slug"]: one["status"] for one in json.loads((scene.state / "queue.json").read_text())
    }
    assert rows["fig-pip"] == "queued" and drawn["fig-pip"][0] == "merged"
    assert [one["slug"] for one in state["ended"]] == ["fig-pip"]


def test_a_quiet_thread_and_a_closed_pull_request_are_drawn_as_the_pass_judged_them(scene, served):
    closed = "pull request #18 is not open and not merged"
    scene.queue(
        [
            row("fig-calm", "running", thread="mcp:14", value="quiet"),
            row("fig-shut", "left", pr="#18", why=closed, thread="mcp:15"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    calm, shut = found["fig-calm"], found["fig-shut"]
    assert (calm["state"]["name"], calm["step"], calm["who"]) == ("Quiet", "running", "crew")
    assert calm["state"]["say"] == "its thread has written nothing for a while"
    assert (shut["state"]["kind"], shut["state"]["name"], shut["step"]) == (
        "closed",
        "Closed",
        "gate",
    )
    assert shut["state"]["say"] == (
        "its thread ended and its pull request #18 is not merged: " + closed
    )
    assert shut["state"]["waits"] == "your word on how it ends"


def test_a_row_work_json_does_not_have_is_unknown_and_says_what_its_row_says(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000")], judged=False)
    scene.write("work.json", {"at": iso(NOW), "answered": "both", "work": []})
    bowl = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert (bowl["state"]["kind"], bowl["step"], bowl["who"]) == ("unknown", "unknown", "unknown")
    assert bowl["state"]["say"] == "the last pass did not judge it: work.json does not have it"
    assert bowl["state"]["row"] == "the row says running, approved"


def test_a_task_the_last_pass_did_not_confirm_says_so(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000", confirmed=False)])
    bowl = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert bowl["state"]["kind"] == "working"
    assert bowl["unconfirmed"]["line"] == built.NOT_CONFIRMED


def test_a_task_behind_a_row_the_pass_judged_merged_is_still_behind_it_as_jbus_holds_it(
    scene, served
):
    kinds(scene)
    state = served.json("/state.json?project=demo")
    found = {one["slug"]: one for one in state["tasks"] + state["ended"]}
    stem, sap, fly = found["fig-stem"], found["fig-sap"], found["fig-fly"]
    assert stem["state"]["say"] == "fig-pip comes first"
    assert stem["state"]["waits"] == "jbus to see that fig-pip is through"
    assert stem["depends"] == [{"slug": "fig-pip", "state": "merged, and its row says queued"}]
    assert stem["blocked"] == {"by": "fig-pip", "what": "fig-pip", "state": "Merged"}
    assert sap["blockers"] == ["fig-tart", "fig-pip"]
    assert sap["state"]["waits"] == "fig-tart to merge"
    assert sap["blocked"] == {"by": "fig-tart", "what": "fig-tart", "state": "Running"}
    assert fly["blocked"] == {"by": "", "what": "fig-gone", "state": "not in the queue"}
    assert found["fig-pip"]["behind"] == ["fig-sap", "fig-stem"]


def test_a_task_that_is_merged_or_finished_is_not_on_the_line_and_a_lost_one_is(scene, served):
    kinds(scene)
    state = served.json("/state.json?project=demo")
    open_work = tasks(state)
    assert {"fig-pip", "fig-tree", "fig-pod"} & set(open_work) == set()
    assert {"fig-moth", "fig-vine"} <= set(open_work)
    assert sorted(one["slug"] for one in state["ended"]) == ["fig-pip"]
    held = {
        slug: (one["step"], one["who"])
        for slug, one in open_work.items()
        if one["state"]["kind"] in ("lost", "hung")
    }
    assert held == {
        "fig-root": ("running", "user"),
        "fig-stalk": ("running", "user"),
        "fig-twig": ("running", "user"),
    }
    vine = open_work["fig-vine"]
    assert (vine["state"]["kind"], vine["step"], vine["who"]) == ("leftover", "gate", "user")
    assert open_work["fig-twig"]["blocked"] == {"by": "", "what": "thread", "state": ""}
    assert open_work["fig-leaf"]["who"] == "dep" and open_work["fig-jam"]["who"] == "bus"


def test_a_fix_whose_scoped_review_is_not_written_is_on_the_second_pass(scene, served):
    """jv-work-state's case of 2026-10-14: its pull request was in the Unknown lane with this
    reason. `jmerge` gave the reason, and no rule named it."""
    why = "wait: its fix is not reviewed: the scoped review of it is not written"
    scene.queue([row("jv-work-state", "pr", pr="#431", checks="passed", why=why)])
    task = tasks(served.json("/state.json?project=demo"))["jv-work-state"]
    assert (task["step"], task["who"]) == ("second", "rev")
    assert task["state"]["say"] == why.removeprefix("wait: ")


def test_a_reason_of_jmerge_that_no_pattern_matches_is_unknown_and_on_a_lane_of_its_own(
    scene, served
):
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="passed", why="wait: another home's")])
    state = served.json("/state.json?project=demo")
    bowl = tasks(state)["oat-bowl"]
    assert (bowl["state"]["kind"], bowl["state"]["name"]) == ("unknown", "Unknown")
    assert bowl["state"]["say"] == "jmerge said: another home's"
    assert (bowl["step"], bowl["who"]) == ("unknown", "unknown")
    assert bowl["step"] not in {one["key"] for one in state["steps"]}
    assert (state["unknown"]["key"], state["unknown"]["name"]) == ("unknown", "Unknown")
    assert (bowl["state"]["waits"], bowl["state"]["row"]) == ("what the view cannot tell", "")
    scene.queue([row("oat-bowl", "pr", pr="#11")])
    said = tasks(served.json("/state.json?project=demo"))["oat-bowl"]["state"]
    assert (said["kind"], said["say"]) == ("unknown", "jmerge has said nothing of it yet")


def test_a_pass_that_could_not_ask_says_which_source_and_the_view_says_it_of_every_task(
    tmp_path, monkeypatch
):
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        for slug in ("alpha", "beta"):
            text = complete(slug)
            assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
        kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=2))
        sources = view.Sources(
            state_dir=kitchen.state_dir, home_dir=kitchen.home.parent, user=jsettings.load()
        )

        def told(minutes):
            now = POLLED + timedelta(minutes=minutes)
            kitchen.poll(now)
            record = json.loads((kitchen.state_dir / "pass.json").read_text())
            state = built.build(sources, "demo", now, lambda repo: {"runs": [], "at": None})
            assert sorted(one["slug"] for one in state["tasks"]) == ["alpha", "beta"]
            lines = {one["unconfirmed"] and one["unconfirmed"]["line"] for one in state["tasks"]}
            return record.get("silent"), lines, [one["line"] for one in state["blind"]]

        assert told(0)[:2] == ({}, {None})
        (kitchen.stub / "gh-down").touch()
        silent, lines, blind = told(1)
        assert silent == {"demo": "GitHub"}
        assert lines == {"not confirmed since 2026-10-12 11:00 ET: GitHub did not answer"}
        assert "2 tasks are not confirmed since 2026-10-12 11:00 ET: GitHub did not answer" in blind
        (kitchen.stub / "gh-down").unlink()
        token = (kitchen.config_dir / "t3.json").read_text()
        (kitchen.config_dir / "t3.json").unlink()
        silent, lines, _ = told(2)
        assert silent == {"demo": "T3 Code"}
        assert lines == {"not confirmed since 2026-10-12 11:00 ET: T3 Code did not answer"}
        kitchen.write(kitchen.config_dir / "t3.json", token)
        silent, lines, blind = told(3)
        assert (silent, lines) == ({}, {None})
        assert [line for line in blind if "not confirmed" in line] == []
    finally:
        kitchen.close()


def test_one_task_that_is_not_confirmed_is_said_as_one(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000")])
    record = json.loads((scene.state_dir / "pass.json").read_text())
    scene.write("pass.json", record | {"silent": {scene.name: "T3 Code"}}, scene.state_dir)
    blind = [one["line"] for one in served.json("/state.json?project=demo")["blind"]]
    assert "1 task is not confirmed since 2026-10-12 15:59 ET: T3 Code did not answer" in blind


def test_a_pass_that_starts_keeps_what_the_last_one_said_did_not_answer(tmp_path, monkeypatch):
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        (kitchen.stub / "gh-down").touch()
        kitchen.poll()
        record.Record(jbus.load(), POLLED + timedelta(minutes=1)).start()
        written = json.loads((kitchen.state_dir / "pass.json").read_text())
        assert (written["ended"], written["silent"]) == (None, {"demo": "GitHub"})
        record.Record(jbus.load(), POLLED + timedelta(minutes=2)).end({}, {})
        written = json.loads((kitchen.state_dir / "pass.json").read_text())
        assert (bool(written["ended"]), written["silent"]) == (True, {"demo": "GitHub"})
        record.Record(jbus.load(), POLLED + timedelta(minutes=3)).end({"demo": {}}, {})
        assert json.loads((kitchen.state_dir / "pass.json").read_text())["silent"] == {}
    finally:
        kitchen.close()


def test_the_limits_file_is_a_source_and_a_limit_whose_reset_is_past_is_unknown(scene, served):
    path = scene.root / "limits"
    state = served.json("/state.json?project=demo")
    source = {one["name"]: one for one in state["sources"]}["limits"]
    assert (source["by"], source["state"]) == ("session", "ok")
    assert source["at"] == built.iso(datetime.fromtimestamp(path.stat().st_mtime, UTC))
    assert state["room"]["plan"]["five_hour"]["used"] == 23.0
    past, ahead = int(ago(hours=1).timestamp()), int((NOW + timedelta(days=3)).timestamp())
    path.write_text(f"five_hour 23.0 {past}\nseven_day 22.0 {ahead}\n")
    written = ago(hours=6).timestamp()
    os.utime(path, (written, written))
    state = served.json("/state.json?project=demo")
    plan = state["room"]["plan"]
    assert plan["five_hour"] == {
        "used": None,
        "resets": iso(ago(hours=1)),
        "written": iso(ago(hours=6)),
        "say": f"unknown, last written {et(ago(hours=6))}",
    }
    assert "23" not in json.dumps(plan["five_hour"]) and "%" not in json.dumps(plan)
    assert (plan["seven_day"]["used"], plan["seven_day"]["say"]) == (22.0, "")
    source = {one["name"]: one for one in state["sources"]}["limits"]
    assert (source["state"], source["at"]) == ("stale", iso(ago(hours=6)))
    line = f"the plan's five-hour limit is unknown, last written {et(ago(hours=6))}"
    assert {"line": line, "open": "room"} in state["blind"]
    path.unlink()
    state = served.json("/state.json?project=demo")
    assert state["room"]["plan"] == {}
    assert {one["name"]: one["state"] for one in state["sources"]}["limits"] == "missing"
    assert [one for one in state["blind"] if "could not be read" in one["line"]] == []


def test_the_page_says_what_it_still_cannot_say(served):
    blind = [one["line"] for one in served.json("/state.json?project=demo")["blind"]]
    spots = [spot for panel in panels.found() for spot in panel.not_kept]
    never = [spot.line for spot in sorted(spots, key=lambda spot: spot.rank)]
    assert never and never == blind[-len(never) :]
    assert "the step a task of unknown state is on is not guessed" in blind
    assert (
        "the plan's use since the limits file was last written is not known: "
        "only a session's status line writes it"
    ) in blind
    assert (
        "a pass that raised, or could not read its queue, is not said on a task: "
        "only T3 Code and GitHub are"
    ) in blind


OPEN = ("leaf", "bark", "sap")


NOTE = "the style pass over the four pages of the guide, " + "page by page, " * 30 + "to the end"


def leftovers(scene):
    """Two tasks that are finished and left a note, and one that is stuck. `plum-jam` merged.
    Its brief has the whole note, while the row has the note cut as a pass cuts it.
    `plum-pit` ended with no pull request, `plum-skin` is queued over a thread that failed,
    and `plum-stem` left a note in a Result that says it is paused. `plum-leaf` is done and
    its Result names no branch, `plum-bark` has a note and no brief to read, and `plum-sap`
    is done with a note and a pull request that did not merge."""
    cut = "left: " + NOTE[:95] + "[cut]"
    scene.queue(
        [
            row("plum-jam", "merged", pr="#51", why=cut, thread="mcp:21"),
            row("plum-pit", "left", why="left: the stones are not sorted", thread="mcp:22"),
            row("plum-skin", thread="mcp:23", value="lost", facts={"thread": "failed"}),
            row("plum-stem", "left", why="left: the stem is half cut", thread="mcp:24"),
            row("plum-leaf", "left", why="its Result has no Branch line", thread="mcp:25"),
            row("plum-bark", "left", why="left: the bark is not off", thread="mcp:26"),
            row("plum-sap", "left", pr="#52", why="left: the sap is not drawn", thread="mcp:27"),
        ]
    )
    (scene.home / "tasks").mkdir(exist_ok=True)
    for slug, status, note in (
        ("plum-pit", "done", "the stones are not sorted"),
        ("plum-stem", "paused", "the stem is half cut"),
        ("plum-leaf", "done", "none"),
        ("plum-sap", "done", "the sap is not drawn"),
    ):
        said = f"## Result\nStatus: {status}\nLeft: {note}\n"
        (scene.home / "tasks" / f"{slug}.md").write_text(f"# {slug}\n\n{said}")
    result = f"## Result\nStatus: done\nLeft: {NOTE}\nBranch: {PULL.format(51)}\n"
    (scene.home / "tasks" / "plum-jam.md").write_text(f"# plum-jam\nTask: jam\n\n{result}")
    scene.waiting(
        [
            item("left", "left:plum-jam", f"left plum-jam: {cut}", slug="plum-jam"),
            item("left", "left:plum-pit", "left plum-pit: left: the stones", slug="plum-pit"),
            item("left", "left:plum-stem", "left plum-stem: left: the stem", slug="plum-stem"),
            *(item("left", f"left:plum-{one}", "left", slug=f"plum-{one}") for one in OPEN),
        ]
    )
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record["projects"][scene.name]["rows"] = {
        "plum-skin": {"threads": 1, "thread_status": "failed", "thread_updated": iso(NOW)}
    }
    scene.write("pass.json", record, scene.state_dir)


def test_a_merged_task_that_left_a_note_is_done_and_waits_only_for_a_word_on_the_note(
    scene, served
):
    leftovers(scene)
    assert len(NOTE) > 300
    jam = tasks(served.json("/state.json?project=demo"))["plum-jam"]
    said = jam["state"]
    assert (said["kind"], said["name"]) == ("leftover", "Ended, with a leftover")
    assert "lost" not in json.dumps(jam).lower()
    assert said["say"].startswith("its pull request #51 is merged and the work is done. ")
    assert f"Its crewmate left a note of something it did not do: {NOTE}. " in said["say"]
    assert "[cut]" not in said["say"]
    assert said["say"].endswith(
        "Either of two things ends it: a new task for what was left, "
        "a Left: none line in its brief once you say the rest is not wanted"
    )
    assert (said["waits"], said["row"]) == ("your word on that note", "")
    assert (jam["step"], jam["who"], jam["blocked"]) == ("gate", "user", None)


def test_a_task_that_ended_with_no_pull_request_and_a_note_is_done_too(scene, served):
    leftovers(scene)
    found = tasks(served.json("/state.json?project=demo"))
    said = found["plum-pit"]["state"]
    assert (said["kind"], said["waits"]) == ("leftover", "your word on that note")
    assert said["say"].startswith("it ended with no pull request and the work is done. ")
    assert "left a note of something it did not do: the stones are not sorted. " in said["say"]
    assert found["plum-skin"]["state"]["name"] == "Lost"
    stem = found["plum-stem"]["state"]
    assert (stem["kind"], stem["name"]) == ("leftover", "Ended, not closed")
    assert stem["say"] == (
        "it ended with no pull request, and its brief does not say the work is finished. "
        "Its crewmate left a note: the stem is half cut"
    )
    assert stem["waits"] == "your word on how it ends"
    assert [slug for slug, one in found.items() if one["state"]["kind"] == "lost"] == ["plum-skin"]


def test_a_row_that_ended_says_its_brief_is_not_finished_only_where_a_status_says_so(scene, served):
    leftovers(scene)
    found = tasks(served.json("/state.json?project=demo"))
    said = {one: found[f"plum-{one}"]["state"] for one in OPEN}
    assert {one["name"] for one in said.values()} == {"Ended, not closed"}
    assert said["leaf"]["say"] == "it ended with no pull request: its Result has no Branch line"
    assert said["bark"]["say"] == (
        "it ended with no pull request. Its crewmate left a note: the bark is not off"
    )
    assert said["sap"]["say"] == (
        "its thread ended and its pull request #52 is not merged. "
        "Its crewmate left a note: the sap is not drawn"
    )


def test_a_note_longer_than_the_view_keeps_is_cut_and_the_sentence_keeps_its_end(scene, served):
    leftovers(scene)
    brief = scene.home / "tasks" / "plum-jam.md"
    brief.write_text(brief.read_text().replace(NOTE, "long " * 2000))
    say = tasks(served.json("/state.json?project=demo"))["plum-jam"]["state"]["say"]
    assert say.endswith("once you say the rest is not wanted") and len(say) < 5000


def test_the_waiting_list_words_a_leftover_as_the_drawer_does(scene, served):
    leftovers(scene)
    state = served.json("/state.json?project=demo")
    found = tasks(state)
    lines = {one["slug"]: one["line"] for one in state["waiting"] if one["kind"] == "left"}
    assert lines == {
        slug: found[slug]["state"]["say"]
        for slug in ("plum-jam", "plum-pit", "plum-stem", *(f"plum-{one}" for one in OPEN))
    }
    assert lines["plum-jam"].startswith("its pull request #51 is merged and the work is done")
    assert NOTE in lines["plum-jam"]


def test_a_chain_of_three_names_each_blocker_and_the_first_blocks_two(scene, served):
    findings = "wait: its findings are not handled: the Result has no Fixed line"
    scene.queue(
        [
            row("nut-shell", "pr", pr="#41", why=findings),
            row("nut-meat", depends=["nut-shell"], why="depends on nut-shell"),
            row("nut-oil", depends=["nut-meat"], why="depends on nut-meat"),
            row("nut-husk", approved="", why="not approved"),
            row("nut-bowl", "running", thread="mcp:1"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert found["nut-shell"]["blocked"] == {"by": "", "what": "findings", "state": ""}
    assert found["nut-meat"]["blocked"] == {
        "by": "nut-shell",
        "what": "nut-shell",
        "state": "Findings",
    }
    assert found["nut-oil"]["blocked"] == {"by": "nut-meat", "what": "nut-meat", "state": "Behind"}
    assert found["nut-shell"]["behind"] == ["nut-meat", "nut-oil"]
    assert found["nut-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}
    assert found["nut-bowl"]["blocked"] is None
    assert {slug: one["blocks"] for slug, one in found.items()} == {
        "nut-shell": 2,
        "nut-meat": 1,
        "nut-oil": 0,
        "nut-husk": 0,
        "nut-bowl": 0,
    }


def test_each_queued_row_names_the_one_row_it_waits_on_last(scene, served):
    """A chain of four: `pea-soup` is behind three rows. `pea-vine` is behind a row that is out.
    `pea-mash` waits on two rows of one wave, and `pea-pod` is the first of them in the queue.
    `pea-husk` is not approved, and `pea-salt` is behind a row that merged."""
    scene.queue(
        [
            row("pea-pod", "gate", why="a gate the Chef has", priority=0),
            row("pea-one"),
            row("pea-two", depends=["pea-one"]),
            row("pea-three", depends=["pea-two"]),
            row("pea-four", depends=["pea-three"]),
            row("pea-soup", depends=["pea-one", "pea-three", "pea-two"]),
            row("pea-vine", depends=["pea-pod"]),
            row("pea-mash", depends=["pea-one", "pea-pod"]),
            row("pea-husk", approved="", why="not approved", depends=["pea-two"]),
            row("pea-done", "merged", pr="#61"),
            row("pea-salt", depends=["pea-done"]),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert {slug: one["waits_on"] for slug, one in found.items()} == {
        "pea-pod": "",
        "pea-one": "",
        "pea-two": "pea-one",
        "pea-three": "pea-two",
        "pea-four": "pea-three",
        "pea-soup": "pea-three",
        "pea-vine": "pea-pod",
        "pea-mash": "pea-pod",
        "pea-husk": "pea-two",
        "pea-salt": "",
    }
    assert found["pea-husk"]["state"]["kind"] == "unapproved"
    assert found["pea-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}


def test_rows_that_depend_on_each_other_still_name_the_row_they_wait_on():
    assert built.waits_on(["a", "b", "c"], {"a": ["b"], "b": ["a"], "c": ["gone"]}) == {
        "a": "b",
        "b": "a",
        "c": "gone",
    }


def test_the_wait_band_is_the_list_the_pass_left_with_the_gates_read_now(scene, served):
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [(one["kind"], one["line"]) for one in waiting] == [
        ("gate", "gate 4: tea or coffee?"),
        ("row", "gate jam-lid: which lid?"),
        ("approve", "approve tea-kettle: jbus queue approve"),
        ("hold", "hold 14: needs user"),
    ]
    assert waiting[0]["since"] == iso(ago(hours=3))
    assert (waiting[0]["question"], waiting[0]["default"]) == ("tea or coffee?", "tea")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write("\n" + GATE.format(n=6, asked="milk?", status="open", default="no"))
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [one["line"] for one in waiting if one["kind"] == "gate"] == [
        "gate 4: tea or coffee?",
        "gate 6: milk?",
    ]
    assert waiting[1]["since"] is None


def owed(scene, pass_minutes):
    """owed-entry's scene of round-2026-10-28: the row jbus wrote says `checks: pending` with
    jmerge's older reason, merge.log's newer line names macos, and the pass that ended
    `pass_minutes` ago saw one check of four still pending."""
    stale = "check has no run at 90a937d3305d"
    scene.queue([row("owe-entry", "pr", pr="#13", checks="pending", why=f"wait: {stale}")])
    scene.merge_log(logged(10, "wait", 13, stale), logged(2, "wait", 13, "macos has not passed"))
    scene.passed(pass_minutes * 60, rows={"owe-entry": checked("check 2 of 4", "pending", 12)})


def test_a_drawer_leads_with_the_newest_of_merge_log_and_the_pass_with_its_time(scene, served):
    owed(scene, 4)
    now = tasks(served.json("/state.json?project=demo"))["owe-entry"]["now"]
    assert now == {"at": iso(ago(minutes=2)), "by": "jmerge", "say": "macos has not passed"}
    owed(scene, 1)
    now = tasks(served.json("/state.json?project=demo"))["owe-entry"]["now"]
    assert now == {"at": iso(ago(minutes=1)), "by": "jbus", "say": "checks pending"}
    assert "check 2 of 4" not in now["say"]


def test_a_drawer_off_the_check_step_keeps_what_it_waits_on_at_its_head(scene, served):
    owed(scene, 1)
    why = "wait: it has no review yet"
    scene.queue([row("owe-entry", "pr", pr="#13", checks="passed", why=why)])
    scene.merge_log(logged(10, "wait", 13, "it has no review yet"))
    found = tasks(served.json("/state.json?project=demo"))["owe-entry"]
    assert found["step"] == "review"
    assert found["now"] == {
        "at": iso(ago(minutes=10)),
        "by": "jmerge",
        "say": "it has no review yet",
    }


def test_a_drawer_whose_state_is_not_jmerge_s_keeps_its_own_say_at_its_head(scene, served):
    why = "wait: it has no review yet"
    lost = row("owe-entry", "pr", pr="#13", why=why, value="lost", facts={"thread": "failed"})
    scene.queue([lost])
    scene.merge_log(logged(30, "wait", 13, "it has no review yet"))
    found = tasks(served.json("/state.json?project=demo"))["owe-entry"]
    assert (found["state"]["name"], found["state"]["say"]) == (
        "Lost",
        "its thread ended early and wrote nothing back",
    )
    assert found["now"] is None
