"""Whether jbus is passing, and the room the machine has."""

import json
from datetime import timedelta

from view.scene import NOW, ago, iso


def test_jbus_is_passing_while_the_timer_is_active_and_a_pass_ended_lately(served):
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (False, "")
    assert jbus["last_end"] == iso(ago(seconds=20))
    assert jbus["said"] == "jbus.timer active (waiting), jbus.service success, exit 0"


def test_jbus_has_stopped_when_the_timer_is_not_active(scene, served):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "the timer is not active")
    assert jbus["said"] == "jbus.timer inactive (dead), jbus.service exit-code, exit 1"
    assert jbus["last_end"] == iso(ago(seconds=20))


def test_jbus_has_stopped_when_the_last_pass_ended_more_than_150_s_ago(scene, served):
    scene.passed(seconds_ago=150)
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is False
    scene.passed(seconds_ago=151)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "no pass in the last 150 s")
    assert jbus["last_end"] == iso(ago(seconds=151))


def test_a_pass_that_is_running_is_no_stop_and_one_that_hangs_is(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["pass"]["running"]) == (False, True)
    scene.now = NOW + timedelta(seconds=200)
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is True


def test_a_pass_that_systemd_says_is_running_is_no_stop_however_long_it_takes(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    scene.now = NOW + timedelta(seconds=200)
    scene.timer(service="activating")
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (False, "")


def test_a_pass_that_starts_and_dies_each_minute_has_stopped(scene, served):
    scene.passed(seconds_ago=400)
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record |= {"started": iso(ago(seconds=5)).replace("+00:00", "Z"), "ended": None}
    scene.write("pass.json", record, scene.state_dir)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "no pass in the last 150 s")
    assert jbus["last_end"] == iso(ago(seconds=400).replace(second=0))


def test_what_jbus_wrote_is_frozen_and_what_the_server_reads_is_live(served):
    sources = {one["name"]: one["by"] for one in served.json("/state.json?project=demo")["sources"]}
    assert {name for name, by in sources.items() if by == "server"} == {
        "jbus.timer",
        "gates.md",
        "plan.md",
        "scouts/",
        "GitHub",
        "runner units",
        "test slots",
        "the machine",
        "~/.claude/projects",
    }
    assert {"queue.json", "waiting-on-user.json", "status.json", "pass.json"} <= {
        name for name, by in sources.items() if by == "jbus"
    }


def test_the_room_is_the_one_answer_jgauge_room_gives(scene, served):
    room = served.json("/state.json?project=demo")["room"]
    assert (room["answer"], room["why"], room["load"][0]) == ("go", "", 2.5)
    assert room["plan"]["five_hour"]["used"] == 23.0
    assert room["cpu_pressure"] == 4.2
    assert room["limits"] == {
        "load": 200,
        "cpu": 40,
        "memory": 6,
        "pressure": 10,
        "slots": 85,
        "plan": 90,
    }
    scene.machine(five_hour=89.0)
    assert served.json("/state.json?project=demo")["room"]["answer"] == "go"
    scene.machine(five_hour=100.0)
    room = served.json("/state.json?project=demo")["room"]
    assert room["answer"] == "wait"
    assert room["why"].startswith("the five-hour limit is 100.0% used, at or over 90%")
