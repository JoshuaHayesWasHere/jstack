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


def test_a_slow_github_holds_no_other_request_and_none_for_long(scene, served, monkeypatch):
    """A request waits on a GitHub that has not answered for its patience at most, and one with
    a kept answer does not wait. What is held is the time each request spends in `GitHub`: the
    rest of a request is the build of its answer, which a busy runner slows (a macOS runner
    under the whole suite took the four requests here to 1.31 s, where an idle Linux takes
    0.64 s), and which no GitHub holds."""
    served.json("/state.json?project=demo")
    github = served.doors.app.github
    github.patience = 0.2
    asks = (scene.bin / "gh").read_text().removeprefix("#!/bin/sh\n")
    scene.script("gh", "sleep 0.7\n" + asks)
    began = time.monotonic()
    answered, waited = [], {"runs": [], "pull": []}

    def timed(name):
        real = getattr(github, name)

        def call(*args):
            start = time.monotonic()
            try:
                return real(*args)
            finally:
                waited[name].append(time.monotonic() - start)

        monkeypatch.setattr(github, name, call)

    for name in ("runs", "pull"):
        timed(name)

    def ask(path):
        """The answer to `path`. A drawer asks `pull`, the state asks `runs`, and two requests of
        one kind do not overlap here, so each one's time on GitHub is what its kind waited."""
        sent = time.monotonic() - began
        said = served.json(path)
        kind = waited["pull" if path.startswith("/task/") else "runs"]
        answered.append((path.split("?")[0], sent, time.monotonic() - began, sum(kind)))
        kind.clear()
        return said, answered[-1]

    def held(asked, limit):
        """The request `asked` waited on GitHub under `limit`, or the message says by how much,
        with every request's times."""
        what, _, _, wait = asked
        each = ", ".join(
            f"{path} sent at {sent:.3f} s, answered at {done:.3f} s, {github_wait:.3f} s on GitHub"
            for path, sent, done, github_wait in answered
        )
        assert wait < limit, (
            f"{what} waited {wait:.3f} s on GitHub, {wait / limit:.1f} times the limit of"
            f" {limit} s; from the first request: {each}"
        )

    drawer = threading.Thread(target=ask, args=("/task/oat-milk/github?project=demo",))
    drawer.start()
    time.sleep(0.05)
    state, asked = ask("/state.json?project=demo")
    assert len(state["checks"]["runs"]) == 3
    held(asked, github.patience / 2)
    drawer.join()
    first = next(one for one in answered if one[0].startswith("/task/"))
    held(first, 2 * github.patience)
    waiting, asked = ask("/task/oat-milk/github?project=demo")
    assert (waiting["pull"], waiting["error"]) == (None, "GitHub has not answered yet")
    held(asked, 2 * github.patience)
    scene.now = NOW + timedelta(seconds=61)
    stale, asked = ask("/state.json?project=demo")
    assert (len(stale["checks"]["runs"]), stale["checks"]["error"]) == (3, "")
    held(asked, 2 * github.patience)
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
