"""crew-router-pilot: once `jbus priming start` has run, each new crew or scout row launches on
the arm with fewer rows of its role, the trimmed one on a tie, and its launch record names the
arm. A trimmed row is told `/crew <slug>` as before, and a control row to read the control copy
of today's priming. `jbus priming stop <why>` sends every later row to the control arm. The tests
run the real commands and the real pass against a faked T3 Code server, as
`test_jbus_kitchen.py` does."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from jbus import priming, queue
from test_jbus_entry_go import PLAN
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, go
from test_jbus_scout import add as add_scout
from test_jbus_scout import launches as scout_launches
from test_jbus_scout import request
from testing.paths import REPO


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "flow").mkdir()
    (made.home / "flow" / "home-id").write_text("mcp:flow-home\n")
    (made.home / "plan.md").write_text(PLAN)
    made.config(max_running=8, max_per_project=8, max_per_home=8)
    yield made
    made.close()


def records(kitchen, slug):
    folder = kitchen.state_dir / "launches" / "demo" / slug
    return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))]


def crews(kitchen):
    return {
        one["title"].removeprefix("crew: "): one["message"].split("\n", 1)[0]
        for one in kitchen.t3.launches
        if one["title"].startswith("crew: ")
    }


def control(role, slug):
    return (
        f"Read `{REPO}/features/{role}/control/{role}.md` in full now, and follow it as the "
        f"/{role} skill with the arguments `{slug}`: it is the priming of crew-router-pilot's "
        "control arm."
    )


def launch_crews(kitchen, *slugs):
    for slug in slugs:
        add(kitchen, slug)
    for minutes in range(0, 3 * len(slugs), 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))


def test_with_no_pilot_started_a_crew_launches_as_crew_and_its_record_names_no_arm(kitchen):
    launch_crews(kitchen, "alpha", "beta")

    assert crews(kitchen) == {"alpha": "/crew alpha", "beta": "/crew beta"}
    assert all("priming" not in one for slug in ("alpha", "beta") for one in records(kitchen, slug))


def test_the_pilot_alternates_crew_rows_and_records_each_rows_arm(kitchen):
    assert kitchen.main("priming", "start")[0] == 0

    launch_crews(kitchen, "alpha", "beta", "gamma", "delta")

    order = [one["title"].removeprefix("crew: ") for one in kitchen.t3.launches]
    arms = ["trimmed", "control", "trimmed", "control"]
    told = crews(kitchen)
    for slug, arm in zip(order, arms, strict=True):
        assert told[slug] == (f"/crew {slug}" if arm == "trimmed" else control("crew", slug))
        (record,) = records(kitchen, slug)
        assert (record["state"], record["priming"]) == ("launched", arm)
    code, said = kitchen.main("priming")
    assert code == 0
    assert "crew: trimmed 2, control 2" in said
    assert "scout: trimmed 0, control 0" in said


def test_the_brief_still_follows_the_first_line_on_the_control_arm(kitchen):
    assert kitchen.main("priming", "start")[0] == 0

    launch_crews(kitchen, "alpha", "beta")

    given = kitchen.t3.launches[1]
    slug = given["title"].removeprefix("crew: ")
    first, _, rest = given["message"].partition("\n\n")
    assert first == control("crew", slug)
    assert rest == (kitchen.home / "tasks" / f"{slug}.md").read_text().split("Thread: ")[0]


def test_a_stopped_pilot_sends_every_later_row_to_the_control_arm(kitchen):
    assert kitchen.main("priming", "start")[0] == 0
    launch_crews(kitchen, "alpha")
    code, said = kitchen.main("priming", "stop", "alpha: no reviewer launched")
    assert code == 0, said
    assert "trimmed arm stopped" in said and "alpha: no reviewer launched" in said

    add(kitchen, "beta")
    add(kitchen, "gamma")
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))

    assert crews(kitchen) == {
        "alpha": "/crew alpha",
        "beta": control("crew", "beta"),
        "gamma": control("crew", "gamma"),
    }


def test_stop_names_its_row_and_needs_a_started_pilot(kitchen):
    assert kitchen.main("priming", "stop")[0] == 2
    assert kitchen.main("priming", "stop", "alpha: a door opened")[0] == 2
    assert kitchen.main("priming")[1].startswith("crew-router-pilot: not started")


def test_a_row_launched_again_keeps_the_arm_its_record_names(tmp_path):
    state = tmp_path / "state"
    run = SimpleNamespace(
        config=SimpleNamespace(state_dir=state), project=SimpleNamespace(name="demo")
    )
    state.mkdir()
    priming.file(state).write_text(json.dumps({"started": "2026-11-02T12:00:00+00:00"}))
    folder = state / "launches" / "demo" / "alpha"
    folder.mkdir(parents=True)
    (folder / "aaaaaaaaaaaa.json").write_text(json.dumps({"state": "retry", "priming": "control"}))

    assert priming.arm(run, "alpha", queue.CREW) == "control"
    assert priming.arm(run, "beta", queue.CREW) == "trimmed"


def test_the_pilot_alternates_scout_rows_and_records_each_rows_arm(kitchen):
    assert kitchen.main("priming", "start")[0] == 0
    for slug in ("alpha", "beta"):
        text = request(slug, asked=f"find out what {slug} does")
        assert add_scout(kitchen, slug, text=text)[0] == 0
        assert go(kitchen, slug)[0] == 0

    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))

    first, second = (
        (one["title"].removeprefix("scout: "), one["message"]) for one in scout_launches(kitchen)
    )
    assert first[1] == f"/scout {first[0]}"
    assert second[1] == control("scout", second[0])
    assert [one["priming"] for one in records(kitchen, second[0])] == ["control"]
    assert "scout: trimmed 1, control 1" in kitchen.main("priming")[1]
