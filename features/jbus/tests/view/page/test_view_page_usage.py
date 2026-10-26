"""The page keeps its events, in the browser: the view opened, each route it shows, each item
it opens and each action it takes, posted to its own server by name alone, with the seconds from
page load to the first of each item and action, and nothing of what they show. The browser of
these tests is headless, and the page marks each event so."""

import json

import pytest

from jbus.view import usage
from view.page.browser import BROWSES, LAUNCH, PATIENCE, gated, look
from view.scene import ago, iso

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def bodies(seen):
    counted = seen["counted"]
    assert {(one["path"], one["kind"], one["origin"]) for one in counted} == {
        ("/usage", "application/json", f"http://127.0.0.1:{seen['at']}")
    }
    return [one["body"] for one in counted]


def test_the_view_each_route_and_each_item_are_kept_by_name_alone(scene, tmp_path):
    """The walk goes to the triage tab and then to the one project, and at 4.5 s the probe
    opens every drawer. The view's opening, each route and each item come to the server as one
    event each, by kind and name alone, and the first of each item carries the seconds from page
    load to it."""
    walk = ["hash:#/triage", "hash:#/demo", "look"]
    seen = look(scene, tmp_path, route="#/", walk=walk, at=4500, budget=12000)
    said = bodies(seen)
    assert all(set(body) == usage.FIELDS and body["headless"] is True for body in said)
    assert [(b["name"], b["project"]) for b in said if b["kind"] == "open"] == [("stack", "")]
    routes = [(b["name"], b["project"]) for b in said if b["kind"] == "route"]
    assert routes == [("stack", ""), ("triage", ""), ("project", "demo")]
    items = [body for body in said if body["kind"] == "item"]
    assert {body["name"] for body in items} == {
        one["target"].partition(":")[0] for one in seen["opened"]
    }
    timed = [body for body in items if body["seconds"] is not None]
    assert sorted(body["name"] for body in timed) == sorted({body["name"] for body in items})
    assert {(body["route"], body["project"]) for body in timed} == {("project", "demo")}
    assert all(4.5 <= body["seconds"] < 9 for body in timed), "the probe opens them at 4.5 s"
    assert seen["writes"] == []
    kept = (scene.state_dir / usage.FILE).read_text().splitlines()
    assert len(kept) == len(said), "the server took every event the page sent"
    names = sorted((one["kind"], one["name"]) for one in map(json.loads, kept))
    assert names == sorted((body["kind"], body["name"]) for body in said)


def test_a_write_the_page_sends_is_kept_as_an_action_with_its_seconds(scene, tmp_path):
    """The probe ticks every gate and closes them in one write: the page keeps one action,
    `answer`, timed from page load, and the write itself is sent as before."""
    gated(scene)
    seen = look(scene, tmp_path, budget=12000, gates={"batch": True})
    assert len(seen["writes"]) == 1
    actions = [body for body in bodies(seen) if body["kind"] == "action"]
    assert len(actions) == 1
    (action,) = actions
    assert (action["name"], action["route"], action["project"]) == ("answer", "project", "demo")
    assert 0 < action["seconds"] < 60
    assert action["headless"] is True


def test_a_steer_the_page_sends_is_kept_as_an_action_named_by_its_action(scene, tmp_path):
    """The page opens the drawer of a proposed work item and the walk taps its Approve. The
    page sends the steer as one write to `/steer`, and keeps one action, named `approve` after
    the steer's action, which the server takes."""
    made = {"id": "w1.1", "item": "w1", "at": iso(ago(minutes=9)), "by": "Josh", "where": "chat"}
    made |= {"line": "proposed", "verb": "proposed", "project": "demo", "slug": "jam-jar"}
    (scene.state / "items.jsonl").write_text(json.dumps(made) + "\n")
    route = "#/demo/item/w1"
    seen = look(scene, tmp_path, route=route, walk=["tap:#iapprove", "look"], at=4000, budget=12000)
    assert [(one["path"].partition("?")[0], one["body"]["action"]) for one in seen["writes"]] == [
        ("/steer", "approve")
    ]
    actions = [body for body in bodies(seen) if body["kind"] == "action"]
    assert [(one["name"], one["route"], one["project"]) for one in actions] == [
        ("approve", "project", "demo")
    ]
    assert 2.5 <= actions[0]["seconds"] < 60, "the walk taps it from 2.5 s on"
    kept = [json.loads(one) for one in (scene.state_dir / usage.FILE).read_text().splitlines()]
    assert [one["name"] for one in kept if one["kind"] == "action"] == ["approve"]
