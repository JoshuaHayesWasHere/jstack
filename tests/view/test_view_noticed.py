"""The Noticed panel: each line, newest first, with its mark."""

from jbus import noticed
from view.scene import a_noticed, ago, iso


def test_the_noticed_panel_lists_each_line_newest_first_with_its_mark(scene, served):
    old, taken, fresh = a_noticed(
        scene,
        ("tea-tray", "dropped", 300, {"why": "from before the list", "by": "jbus"}),
        ("jam-jar", "taken", 60, {"row": "fix-jar", "by": "home", "at": "2026-10-12 10:58 ET"}),
        ("oat-milk", "new", 5, {}),
    )
    said = served.json("/state.json?project=demo")["noticed"]
    assert [one["key"] for one in said] == [fresh, taken, old]
    assert {key: said[1][key] for key in ("slug", "mark", "row", "by", "seen_at", "text")} == {
        "slug": "jam-jar",
        "mark": "taken",
        "row": "fix-jar",
        "by": "home",
        "seen_at": iso(ago(minutes=60)),
        "text": "jam-jar saw a thing",
    }
    assert said[2]["why"] == "from before the list"
    assert served.json("/state.json?project=demo")["noticed_older"] == 0
    assert served.json("/panel/noticed.json?project=demo")["data"] == {
        "noticed": said,
        "noticed_older": 0,
    }
    many = [(f"old-{n:02}", "dropped", 500 + n, {"why": "from before the list"}) for n in range(30)]
    a_noticed(scene, ("oat-milk", "new", 5, {}), *many)
    state = served.json("/state.json?project=demo")
    assert [one["slug"] for one in state["noticed"]] == [
        "oat-milk",
        *(f"old-{n:02}" for n in range(20)),
    ]
    assert state["noticed_older"] == 10
    (scene.state / noticed.NAME).write_text("{not json")
    state = served.json("/state.json?project=demo")
    assert state["noticed"] == []
    assert {one["name"]: one["state"] for one in state["sources"]}[noticed.NAME] == "unreadable"
