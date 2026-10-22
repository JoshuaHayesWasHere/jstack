"""The threads out: each one's liveness, the scouts' requests, and a thread that is gone."""

import json

import pytest

from view.scene import (
    OPAQUE,
    REPORTED,
    REQUEST,
    Scene,
    Served,
    ago,
    iso,
    logged,
    out,
    requested,
    row,
    stacked,
    tasks,
)


def test_the_state_has_every_thread_out_and_each_task_its_threads_liveness(scene, served):
    began = iso(ago(minutes=40))
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar", "hung", minutes=25, run_started=began, queued=2),
            out("review: oat-milk, second pass", "quiet", minutes=12),
            out("scout: look", "waiting", minutes=90, page=True),
            out("home: demo"),
            out("a thread he opened", "ended", "completed"),
            out("crew: odd", "a word nobody named", secret=OPAQUE),
        ],
        rows={"jam-jar": {"threads": 1, "thread_status": "running", "live": "hung"}},
    )
    state = served.json("/state.json?project=demo")
    assert [(t["title"], t["role"], t["slug"], t["live"], t["out"]) for t in state["threads"]] == [
        ("crew: jam-jar", "crew", "jam-jar", "hung", True),
        ("review: oat-milk, second pass", "reviewer", "oat-milk", "quiet", True),
        ("scout: look", "scout", "look", "waiting", True),
        ("home: demo", "home", "demo", "moving", True),
        ("a thread he opened", "other", "", "ended", False),
        ("crew: odd", "crew", "odd", "unknown", True),
    ]
    assert state["threads"][0] == {
        "today": True,
        "title": "crew: jam-jar",
        "role": "crew",
        "slug": "jam-jar",
        "status": "running",
        "live": "hung",
        "out": True,
        "created": iso(ago(hours=1)),
        "updated": iso(ago(minutes=25)),
        "run_started": began,
        "queued": 2,
        "pending": 0,
        "page": False,
        "rank": 0,
    }
    seen = tasks(state)["jam-jar"]["seen"]
    assert (seen["live"], seen["run_started"], seen["queued"]) == ("hung", began, 2)
    assert seen["wrote"] == iso(ago(minutes=25))
    assert tasks(state)["oat-milk"]["seen"]["live"] == ""
    scene.passed(
        20,
        threads=[out("crew: jam-jar", "hung", run_started=began, queued=2), out("crew: jam-jar")],
        rows={"jam-jar": {"threads": 2, "thread_status": None, "live": None}},
    )
    seen = tasks(served.json("/state.json?project=demo"))["jam-jar"]["seen"]
    assert (seen["live"], seen["wrote"], seen["queued"]) == ("", None, 0)
    assert "the threads that are out" not in json.dumps(state["blind"])


def test_each_scouts_request_says_researching_reported_or_blocked(scene, served):
    """The one source the view reads that jbus does not write: a scout's request, for its
    last `## Report` and the `Status:` line under it. Only `done` counts as reported. The
    view says a scout whose last Report says not done is not done, whatever an earlier one
    said. A Report with a gate in it still has its Status line, and the view says a request
    that is not there is missing, never that there is none."""
    requested(
        scene,
        tea_tin=REQUEST.format(slug="tea-tin"),
        jam_tin=REPORTED.format(slug="jam-tin", status="done"),
        oat_tin=REPORTED.format(slug="oat-tin", status="blocked (the tin is welded shut)"),
        rye_tin=REPORTED.format(slug="rye-tin", status="not done") + "\n## Report\nStatus: done\n",
        kale_tin=REPORTED.format(slug="kale-tin", status="done")
        + "\n## Report\nStatus: not done\n",
        fig_tin=REQUEST.format(slug="fig-tin")
        + "\n## Report\nStatus: blocked\nAnswers:\n- half\n## Gate 2: open the tin?\n"
        + "Status: open\n",
    )
    scene.passed(
        20,
        threads=[
            out(f"scout: {slug}", "ended" if slug == "jam-tin" else "moving")
            for slug in (
                "tea-tin",
                "jam-tin",
                "oat-tin",
                "rye-tin",
                "kale-tin",
                "fig-tin",
                "no-tin",
            )
        ]
        + [out("crew: tea-tin")],
    )
    state = served.json("/state.json?project=demo")
    said = {(t["role"], t["slug"]): t.get("request") for t in state["threads"]}
    asks = "{}: what is in the {} tin"
    assert said == {
        ("scout", "tea-tin"): {
            "state": "researching",
            "status": "",
            "asks": asks.format("tea-tin", "tea-tin"),
        },
        ("scout", "jam-tin"): {
            "state": "reported",
            "status": "done",
            "asks": asks.format("jam-tin", "jam-tin"),
        },
        ("scout", "oat-tin"): {
            "state": "blocked",
            "status": "blocked (the tin is welded shut)",
            "asks": asks.format("oat-tin", "oat-tin"),
        },
        ("scout", "rye-tin"): {
            "state": "reported",
            "status": "done",
            "asks": asks.format("rye-tin", "rye-tin"),
        },
        ("scout", "kale-tin"): {
            "state": "not done",
            "status": "not done",
            "asks": asks.format("kale-tin", "kale-tin"),
        },
        ("scout", "fig-tin"): {
            "state": "blocked",
            "status": "blocked",
            "asks": asks.format("fig-tin", "fig-tin"),
        },
        ("scout", "no-tin"): {"state": "missing", "status": "", "asks": ""},
        ("crew", "tea-tin"): None,
    }
    assert {"name": "scouts/", "by": "server", "state": "ok"} in [
        {key: one[key] for key in ("name", "by", "state")} for one in state["sources"]
    ]


def test_a_thread_that_ended_before_the_users_day_began_is_not_of_today(scene, served):
    """The user's day starts at midnight in the user's zone: 04:00 UTC on this day."""
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar"),
            out("crew: oat-milk", "ended", "completed", minutes=60 * 15),
            out("crew: oat-bowl", "ended", "completed", minutes=60 * 17),
            out("review: oat-bowl", "waiting", minutes=60 * 17),
        ],
    )
    state = served.json("/state.json?project=demo")
    assert [(t["title"], t["out"], t["today"]) for t in state["threads"]] == [
        ("crew: jam-jar", True, True),
        ("crew: oat-milk", False, True),
        ("crew: oat-bowl", False, False),
        ("review: oat-bowl", True, True),
    ]


def test_the_stack_has_each_projects_threads_and_none_where_its_pass_left_no_list(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    requested(scene, look=REQUEST.format(slug="look"))
    scene.passed(20, threads=[out("crew: jam-jar"), out("scout: look", "quiet", minutes=12)])
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    by = {one["name"]: one for one in stack["projects"]}
    assert by["demo"]["threads"] == demo["threads"]
    assert [(t["slug"], t["live"], t.get("request", {}).get("state")) for t in demo["threads"]] == [
        ("jam-jar", "moving", None),
        ("look", "quiet", "researching"),
    ]
    assert (by["larder"]["threads"], by["pantry"]["threads"]) == (None, None)
    assert by["demo"]["health"]["threads"] == 2


def test_a_pass_that_left_no_list_of_threads_is_a_blind_spot_and_no_count_of_none(scene, served):
    scene.passed(20, threads=None)
    state = served.json("/state.json?project=demo")
    assert state["threads"] is None
    assert {
        "line": "the threads that are out are not known: the last pass left no list of them",
        "open": "threads",
    } in state["blind"]


def test_a_launched_row_whose_thread_is_gone_and_wrote_nothing_is_lost(scene, served):
    gone = {"thread": "none", "launch": "launched"}
    scene.queue(
        [
            row("fig-gone", "launched", thread="mcp:1", value="lost", facts=gone),
            row("fig-new", "launched", thread="mcp:3"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    said = found["fig-gone"]["state"]
    assert (said["kind"], said["name"]) == ("lost", "Lost")
    assert said["say"] == "its thread is gone and wrote nothing"
    assert (found["fig-gone"]["step"], found["fig-gone"]["who"]) == ("running", "user")
    assert found["fig-new"]["state"]["kind"] == "launching"


@pytest.mark.parametrize(
    ("minutes", "threads", "says"),
    [
        (10, [], "no reviewer has started"),
        (10, [out("crew: fig-read"), out("review: fig-other")], "no reviewer has started"),
        (9, [], "it has no review yet"),
        (40, [out("review: fig-read")], "it has no review yet"),
        (40, [out("review: fig-read, second pass", "ended", "completed")], "it has no review yet"),
        (40, None, "it has no review yet"),
        (40, [], "its review has no verdict"),
    ],
)
def test_a_pull_request_ten_minutes_on_review_with_no_reviewer_listed_says_so(
    scene, served, minutes, threads, says
):
    reason = says if says.startswith("it") else "it has no review yet"
    scene.queue([row("fig-read", "pr", pr="#31", why=f"wait: {reason}")])
    scene.merge_log(logged(minutes, "wait", 31, reason))
    scene.passed(20, threads=threads)
    task = tasks(served.json("/state.json?project=demo"))["fig-read"]
    assert (task["step"], task["state"]["say"]) == ("review", says)
    waits = "its crewmate to start a reviewer" if says.startswith("no reviewer") else "its reviewer"
    assert task["state"]["waits"] == waits
