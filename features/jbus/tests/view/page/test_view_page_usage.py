"""The page counts what it opens, in the browser: each route it shows, each drawer it opens and
the first click after it loads, posted to its own server, and nothing of what they show."""

import json

import pytest

from jbus.view import usage
from view.page.browser import BROWSES, LAUNCH, PATIENCE, look

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def test_each_route_and_drawer_and_the_first_click_are_counted_by_name_alone(scene, tmp_path):
    """The probe opens every drawer the first screen of every project has, then the walk goes
    to the one project. Each route and each drawer comes to the server as one count, by its
    kind and name alone, and the first click is counted once."""
    seen = look(scene, tmp_path, route="#/", walk=["hash:#/demo", "look"], at=4500, budget=12000)
    counted = seen["counted"]
    assert {(one["path"], one["kind"], one["origin"]) for one in counted} == {
        ("/usage", "application/json", f"http://127.0.0.1:{seen['at']}")
    }
    bodies = [one["body"] for one in counted]
    assert all(set(body) == {"kind", "name", "project"} for body in bodies)
    routes = [(body["name"], body["project"]) for body in bodies if body["kind"] == "route"]
    assert routes == [("stack", ""), ("project", "demo")]
    drawers = {body["name"] for body in bodies if body["kind"] == "drawer"}
    assert drawers == {one["target"].partition(":")[0] for one in seen["opened"]}
    assert [body["kind"] for body in bodies].count("click") == 1
    assert seen["writes"] == []
    kept = (scene.state_dir / usage.FILE).read_text().splitlines()
    assert len(kept) == len(counted), "the server took every count the page sent"
    names = sorted((one["kind"], one["name"]) for one in map(json.loads, kept))
    assert names == sorted((body["kind"], body["name"]) for body in bodies)
