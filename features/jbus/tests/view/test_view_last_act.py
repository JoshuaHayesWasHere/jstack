"""The time since the last act, per home and for the whole project, over one real busy moment.

The fixture `fixtures/jv-glance/` is jstack at 2026-10-26 13:00 UTC, the moment the jv-glance
scouts filled their wireframes with (`reports/jv-glance/state/` of the jstack home). It holds
the 71 rows that were open then or ended that day, with their status at that moment, the home
each one's brief names by `jbriefs.home_of`, and the ids of the root and of the three scopes.
Beside them are the six hours of `events.jsonl` before it, with each line cut to 120
characters, the same hours of `transitions.jsonl`, and the day's `merge.log`.

A reviewer of the wireframes (scout jv-glance-r4) found the root shown as quiet for 5h18, since
its last merge, while its rows had events at 08:59 EDT. Another (jv-glance-r2) found 14 of the
44 open rows placed by slug prefix in the wrong home. By `home_of` the open rows are jview's
15, flow's 8, macos's 1 and the root's 20.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from view.scene import Scene, Served, row

FIXTURE = Path(__file__).parent.parent / "fixtures" / "jv-glance"
AT = datetime.fromisoformat("2026-10-26T13:00:00+00:00")
OPEN = {"": 20, "jview": 15, "flow": 8, "macos": 1}


def glance(scene):
    """The scene as jstack was at `AT`: the queue, the briefs and requests with their `Home:`
    lines, the homes' ids, and the three records of acts."""
    kept = json.loads((FIXTURE / "state.json").read_text())
    home = scene.home
    (home / "home-id").write_text(kept["root"]["home-id"] + "\n")
    (home / "handoff.md").write_text(f"Was home: {kept['root']['was']}\n")
    for name, ids in kept["scopes"].items():
        (home / name).mkdir()
        (home / name / "home-id").write_text(ids["home-id"] + "\n")
        if ids["was"]:
            (home / name / "handoff.md").write_text(f"Was home: {ids['was']}\n")
    for kind in ("tasks", "scouts"):
        (home / kind).mkdir(exist_ok=True)
        for slug, named in kept[kind].items():
            line = f"Home: {named}\n" if named else ""
            (home / kind / f"{slug}.md").write_text(f"# {slug}: a task of that day\n{line}")
    scene.queue(
        [
            row(one["slug"], one["status"], **{key: one[key] for key in ("pr", "depends", "since")})
            for one in kept["rows"]
        ]
    )
    for name in ("events.jsonl", "transitions.jsonl"):
        shutil.copy(FIXTURE / name, scene.state / name)
    shutil.copy(FIXTURE / "merge.log", home / "merge.log")
    scene.now = AT


@pytest.fixture
def zoned(tmp_path, monkeypatch):
    """The view of that moment, for a user in New York, where `merge.log` stamps its lines."""
    config = tmp_path / "xdg"
    (config / "jstack").mkdir(parents=True)
    (config / "jstack" / "config.toml").write_text('timezone = "America/New_York"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    scene = Scene(tmp_path, monkeypatch)
    glance(scene)
    made = Served(scene)
    yield made
    made.close()


def test_each_home_has_its_open_rows_by_its_briefs_home_line(zoned):
    """The summary and the board count each open row in its brief's home. The pipeline places
    only the rows on a step it knows, and the fixture keeps no step of `jmerge`'s for most pull
    requests, so each row it places is checked against its brief: a cleanup row, whose brief
    names no home, is the root's whatever row it is stacked on."""
    (project,) = zoned.json("/stack.json")["projects"]
    assert {one["name"]: one["open"] for one in project["homes"]} == OPEN
    board = zoned.json("/panel/board.json?project=demo")["data"]["homes"]
    assert {one["name"]: len(one["workers"]) for one in board} == OPEN
    named = json.loads((FIXTURE / "state.json").read_text())["tasks"]
    rows = zoned.json("/panel/pipeline.json")["data"]["rows"]
    assert {one["slug"]: one["home"] for one in rows} == {
        one["slug"]: named[one["slug"]] or "root" for one in rows
    }
    assert "root" in {one["home"] for one in rows if one["slug"].startswith("cleanup-")}


def test_each_home_and_the_project_say_their_last_act_not_their_last_merge(zoned):
    """The root's last act is the Result of cleanup-ux-flow-status at 08:59:44 EDT, a row
    whose brief names no home. Its last merge was hours before. jview's is jbus's failover of
    its home's thread, which names the thread's id, and it is the project's last act too."""
    (project,) = zoned.json("/stack.json")["projects"]
    last = {one["name"]: one["last"] for one in project["homes"]}
    assert last == {
        "": {
            "at": "2026-10-26T12:59:44+00:00",
            "what": "result cleanup-ux-flow-status: done",
        },
        "flow": {
            "at": "2026-10-26T12:59:45+00:00",
            "what": "merged fl-standing-cap #482 889c39c69f70",
        },
        "jview": {"at": "2026-10-26T12:59:52+00:00", "what": last["jview"]["what"]},
        "macos": {"at": "2026-10-26T12:59:03+00:00", "what": last["macos"]["what"]},
    }
    assert last["jview"]["what"].startswith("failover home: seven_day limit")
    assert last["macos"]["what"].startswith("overlap bl-macos-ci-required:")
    assert project["last"] == {"home": "jview"} | last["jview"]
    board = zoned.json("/panel/board.json?project=demo")["data"]["homes"]
    assert {one["name"]: one["last"] for one in board} == last


def test_a_heartbeat_is_no_act_and_an_act_of_no_home_is_the_projects_alone(zoned, tmp_path):
    """jbus's hourly heartbeat says only that jbus runs. jbus's line about the whole project,
    as `waiting` writes it, names no row: it is the project's last act and no home's."""
    events = (tmp_path / "state" / "demo" / "events.jsonl").open("a")
    for kind, line in (
        ("waiting", "waiting demo: 10 wait on the user"),
        ("heartbeat", "heartbeat: jbus alive"),
    ):
        stamp = "2026-10-26T12:59:58+00:00" if kind == "waiting" else "2026-10-26T12:59:59+00:00"
        events.write(json.dumps({"at": stamp, "event": kind, "slug": "", "line": line}) + "\n")
    events.close()
    (project,) = zoned.json("/stack.json")["projects"]
    assert project["last"] == {
        "at": "2026-10-26T12:59:58+00:00",
        "home": None,
        "what": "waiting demo: 10 wait on the user",
    }
    assert max(one["last"]["at"] for one in project["homes"]) == "2026-10-26T12:59:52+00:00"
