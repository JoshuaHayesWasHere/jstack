"""The Checks panel: what the server asks GitHub for, and when, and the runners."""

import threading
import time
from datetime import timedelta

from view.scene import NOW, PULL, RUN, ago, iso


def test_github_is_asked_for_the_checks_card_once_a_minute(scene, served):
    for _ in range(5):
        state = served.json("/state.json?project=demo")
    assert scene.asked() == ["api repos/acme/demo/actions/runs?per_page=40"]
    assert [(run["branch"], run["state"]) for run in state["checks"]["runs"]] == [
        ("oat-bowl", "success"),
        ("oat-milk", "failure"),
        ("oat-milk", "in_progress"),
    ]
    assert state["checks"]["runs"][0]["url"] == RUN.format(500)
    scene.now = NOW + timedelta(seconds=59)
    served.json("/state.json?project=demo")
    assert len(scene.asked()) == 1
    scene.now = NOW + timedelta(seconds=61)
    served.json("/state.json?project=demo")
    assert scene.asked() == ["api repos/acme/demo/actions/runs?per_page=40"] * 2


def test_github_is_asked_for_a_pull_request_only_when_its_drawer_opens(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    for _ in range(3):
        found = served.json("/task/oat-milk/github?project=demo")
    assert scene.asked() == [
        "api repos/acme/demo/pulls/13",
        "api repos/acme/demo/commits/" + "d00d" * 10 + "/check-runs",
    ]
    assert found["pull"] == {
        "number": 13,
        "state": "open",
        "merged": False,
        "mergeable": True,
        "mergeable_state": "blocked",
        "head": "d00d" * 10,
        "updated": iso(ago(minutes=3)),
        "url": PULL.format(13),
    }
    assert [(one["name"], one["state"]) for one in found["checks"]] == [("check", "in_progress")]
    scene.now = NOW + timedelta(seconds=31)
    served.json("/task/oat-milk/github?project=demo")
    assert len(scene.asked()) == 4


def test_a_slow_github_holds_no_other_request_and_none_for_long(scene, served):
    served.json("/state.json?project=demo")
    served.doors.app.github.patience = 0.2
    asks = (scene.bin / "gh").read_text().removeprefix("#!/bin/sh\n")
    scene.script("gh", "sleep 0.7\n" + asks)
    began = time.monotonic()
    answered = []

    def ask(path):
        sent = time.monotonic() - began
        said = served.json(path)
        answered.append(f"{path.split('?')[0]} {sent:.3f} to {time.monotonic() - began:.3f} s")
        return said

    def parts():
        return "each request, sent to answered, from the first: " + ", ".join(answered)

    drawer = threading.Thread(target=ask, args=("/task/oat-milk/github?project=demo",))
    drawer.start()
    time.sleep(0.05)
    state = ask("/state.json?project=demo")
    assert time.monotonic() - began < 1.0, parts()
    assert len(state["checks"]["runs"]) == 3
    drawer.join()
    waiting = ask("/task/oat-milk/github?project=demo")
    assert (waiting["pull"], waiting["error"]) == (None, "GitHub has not answered yet")
    scene.now = NOW + timedelta(seconds=61)
    stale = ask("/state.json?project=demo")
    assert time.monotonic() - began < 1.2, parts()
    assert (len(stale["checks"]["runs"]), stale["checks"]["error"]) == (3, "")
    time.sleep(1.7)
    assert served.json("/task/oat-milk/github?project=demo")["pull"]["number"] == 13


def test_a_task_with_no_pull_request_asks_github_nothing(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    assert served.json("/task/jam-jar/github?project=demo") == {
        "slug": "jam-jar",
        "pull": None,
        "checks": [],
    }
    assert scene.asked() == []


def test_a_slug_the_queue_does_not_have_is_404_and_asks_nothing(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    for slug in ("nobody", "..", "oat-milk%2F..", "%2e%2e", "13", "oat-milk/../jam-jar"):
        assert served.ask(f"/task/{slug}/github?project=demo")[0] == 404, slug
    assert scene.asked() == []


def test_github_is_only_ever_read(scene, served):
    served.json("/state.json?project=demo")
    for slug in ("oat-bowl", "oat-spoon", "oat-milk", "oat-honey"):
        served.json(f"/task/{slug}/github?project=demo")
    assert scene.asked()
    for call in scene.asked():
        words = call.split()
        assert words[0] == "api" and len(words) == 2, call
        assert words[1].startswith("repos/acme/demo/"), call


def test_a_github_that_does_not_answer_is_said_and_the_page_still_gets_its_state(scene, served):
    scene.script("gh", "exit 1\n")
    state = served.json("/state.json?project=demo")
    assert (state["checks"]["runs"], state["checks"]["error"]) == ([], "GitHub did not answer")
    assert served.json("/task/oat-milk/github?project=demo")["error"] == "GitHub did not answer"
    assert len(state["tasks"]) == 9


def test_the_checks_list_each_runner_and_a_stopped_one_is_no_blind_spot(scene, served):
    scene.runners(
        ("actions-runner-a.service", "active", "running"),
        ("actions-runner-b.service", "inactive", "dead"),
    )
    state = served.json("/state.json?project=demo")
    assert state["checks"]["runners"] == [
        {"unit": "actions-runner-a.service", "active": "active", "sub": "running"},
        {"unit": "actions-runner-b.service", "active": "inactive", "sub": "dead"},
    ]
    assert state["checks"]["runners_read"] is True
    assert [one for one in state["blind"] if "runner" in one["line"]] == []
    listed = {one["name"]: one for one in state["sources"]}["runner units"]
    assert (listed["by"], listed["state"]) == ("server", "ok")
    calls = (scene.root / "systemctl.calls").read_text().splitlines()
    assert calls and set(calls) == {
        "--user list-units actions-runner-* --all --output=json --no-pager"
    }
