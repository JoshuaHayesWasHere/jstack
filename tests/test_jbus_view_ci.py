"""The CI panel: the nine targets of `jbus ci`, each by day, with a mark at the merge of each
change that was to move it. It reads `ci.jsonl` and `ci-prs.jsonl` of the project's state."""

import json
from datetime import datetime

import pytest

from ci_replay import FOLDER, Replay
from jbus.ci import collect, ledger
from test_jbus_ci import NOW as RECORDED
from test_jbus_view import NOW, Scene, Served

TIMES = ("created", "started", "completed", "merged", "closed")
SHIFT = NOW - RECORDED


def later(stamp):
    if not stamp:
        return stamp
    moved = datetime.fromisoformat(stamp.replace("Z", "+00:00")) + SHIFT
    return moved.isoformat().replace("+00:00", "Z")


def keep(scene):
    """The recording's ledger, moved in time to end at the scene's now."""
    state = scene.state.parent.parent / "recorded"
    collect.collect(Replay(), "o/jstack", state, RECORDED, 14)
    jobs = [
        {**one, **{k: later(one[k]) for k in TIMES if k in one}}
        for one in ledger.read(state / ledger.JOBS)
    ]
    pulls = [
        {
            **one,
            **{k: later(one[k]) for k in TIMES if k in one},
            "pushes": [later(p) for p in one["pushes"]],
        }
        for one in ledger.read(state / ledger.PULLS)
    ]
    events = [json.loads(line) for line in (FOLDER / "events.jsonl").open()]
    for one in events:
        one["at"] = later(one["at"])
    for name, rows in (("ci.jsonl", jobs), ("ci-prs.jsonl", pulls), ("events.jsonl", events)):
        (scene.state / name).write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.fixture
def scene(tmp_path, monkeypatch):
    return Scene(tmp_path / "scene", monkeypatch)


@pytest.fixture
def served(scene):
    made = Served(scene)
    yield made
    made.close()


def asked(served):
    return served.json("/panel/ci.json?project=demo")


def landed(home, slug, number, stamp):
    sha = "ab" * 20
    with (home / "merge.log").open("a") as log:
        log.write(f'{stamp} merged {number} {slug} {sha} "a change"\n')


def test_the_panel_draws_the_nine_targets_with_the_values_jbus_ci_prints(scene, served):
    keep(scene)
    ci = asked(served)["data"]["ci"]
    assert ci["read"] is True
    assert [one["key"] for one in ci["numbers"]] == [
        "queue",
        "waste",
        "own",
        "rebases",
        "stale",
        "green",
        "mainred",
        "flaky",
        "inode",
    ]
    by = {one["key"]: one for one in ci["numbers"]}
    assert by["queue"]["shown"] == "26.6 vs 9.67 min" and by["queue"]["met"] is False
    assert by["waste"]["shown"] == "42.9%"
    assert by["queue"]["target"] and by["queue"]["how"]


def test_each_number_is_drawn_by_the_day_for_the_period(scene, served):
    keep(scene)
    ci = asked(served)["data"]["ci"]
    for one in ci["numbers"]:
        assert len(one["series"]) == ci["days"] == 14
        assert [day["day"] for day in one["series"]] == sorted(day["day"] for day in one["series"])
    queue = next(one for one in ci["numbers"] if one["key"] == "queue")
    assert [day["value"] for day in queue["series"][:9]] == [None] * 9
    assert all(day["value"] is not None for day in queue["series"][-3:])


def test_a_mark_is_the_merge_of_each_change_that_has_landed_in_this_home_or_infras(scene, served):
    keep(scene)
    landed(scene.home, "ci-slow-tail", 91, "2026-10-12 09:00")
    landed(scene.home, "unrelated", 92, "2026-10-12 09:30")
    (scene.home_dir / "infra").mkdir()
    landed(scene.home_dir / "infra", "jstack-fast-4", 56, "2026-10-11 19:03")
    marks = asked(served)["data"]["ci"]["marks"]
    assert [(one["label"], one["project"]) for one in marks] == [
        ("slow tail", "demo"),
        ("runner CPUs to 4", "infra"),
    ]
    assert marks[0]["at"] == "2026-10-12T13:00:00+00:00"


def test_with_no_ledger_the_panel_has_no_numbers_and_the_sources_say_the_ledger_is_missing(
    scene, served
):
    scene.state.joinpath("ci.jsonl").unlink()
    scene.state.joinpath("ci-prs.jsonl").unlink()
    ci = asked(served)["data"]["ci"]
    assert (ci["read"], ci["numbers"], ci["jobs"]) == (False, [], 0)
    states = {
        one["name"]: one["state"] for one in served.json("/state.json?project=demo")["sources"]
    }
    assert (states["ci.jsonl"], states["ci-prs.jsonl"]) == ("missing", "missing")


def test_the_panel_names_the_files_it_reads_and_the_inode_series_it_never_had(scene, served):
    keep(scene)
    answer = asked(served)
    assert {"ci.jsonl", "ci-prs.jsonl"} <= {one["name"] for one in answer["sources"]}
    blind = [one["line"] for one in served.json("/state.json?project=demo")["blind"]]
    assert "the /tmp inode series is not kept until a job writes tmp_inode_pct" in blind


def test_the_first_screen_carries_none_of_it(scene, served):
    keep(scene)
    assert "ci" not in served.json("/state.json?project=demo")
