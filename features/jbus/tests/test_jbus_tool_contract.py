"""A pass asks T3 Code what it serves and raises one alert of the machine's for each tool of
`jbus.t3.TOOLS` it no longer serves (`jbus.t3.contract`). The alert is told once while the tool
stays missing, and its end once.

Every test runs the real pass against the faked T3 Code server of `test_jbus_kitchen`, which drops
a tool from its `tools/list`. Nothing reaches the network.
"""

import json

import pytest

from jbus import alert, t3
from test_jbus_kitchen import NOW

GONE = "t3_thread_configure"
ALERT = f"alert: T3 Code no longer serves {GONE}, a tool jbus calls"
ENDED = f"recovered: T3 Code serves {GONE} again"


@pytest.fixture
def infra(kitchen):
    return kitchen.second("infra").wakes


def told(lines):
    """The alert and recovered lines of a pass, or of a home, about T3 Code's tools."""
    return [line for line in lines if line.startswith(("alert: T3 Code", "recovered: T3 Code"))]


def test_a_tool_that_goes_missing_is_said_on_the_first_pass_and_no_later_one(kitchen, infra):
    kitchen.t3.dropped = {GONE}
    first = told(kitchen.poll())
    assert [line.startswith(ALERT) for line in first] == [True]
    assert [line.startswith(ALERT) for line in told(infra.said)] == [True]
    assert [line for line in kitchen.log("notify") if GONE in line] == [f"jbus | {first[0]}"]
    assert told(kitchen.wakes.said) == []
    infra.listed.clear()
    assert told(kitchen.poll()) == []
    assert told(kitchen.poll()) == []
    assert told(infra.said) == []
    assert len([line for line in kitchen.log("notify") if GONE in line]) == 1


def test_its_end_is_said_once_and_wakes_no_one(kitchen, infra):
    kitchen.t3.dropped = {GONE}
    kitchen.poll()
    infra.listed.clear()
    kitchen.t3.dropped = set()
    assert told(kitchen.poll()) == [ENDED]
    assert told(kitchen.poll()) == []
    assert told(infra.said) == []
    code, printed = kitchen.main("--project", "infra", "events")
    assert code == 0
    assert [json.loads(line)["line"] for line in printed.splitlines()].count(ENDED) == 1
    kitchen.t3.dropped = {GONE}
    assert [line.startswith(ALERT) for line in told(kitchen.poll())] == [True]


def test_each_missing_tool_has_its_own_alert(kitchen, infra):
    kitchen.t3.dropped = {GONE, "t3_thread_send"}
    assert len(told(kitchen.poll())) == 2
    kitchen.t3.dropped = {"t3_thread_send"}
    assert told(kitchen.poll()) == [ENDED]
    assert [key for key in alert.streaks(kitchen.state_dir) if key.startswith(t3.MISSING)] == [
        f"{t3.MISSING}t3_thread_send"
    ]


def test_a_server_that_serves_them_all_shows_none_and_a_pass_lists_once(kitchen, infra):
    assert told(kitchen.poll()) == []
    assert kitchen.t3.listings == 1
    assert told(infra.said) == [] and kitchen.log("notify") == []
    kitchen.t3.dropped = {GONE}
    kitchen.poll()
    assert kitchen.t3.listings == 2


def test_a_list_that_did_not_come_says_nothing_of_a_tool_either_way(kitchen, infra):
    kitchen.t3.lose_listing = True
    said = kitchen.poll()
    assert told(said) == []
    assert [line for line in said if line.startswith("wait: T3 Code's tools not known: ")]
    assert [key for key in alert.streaks(kitchen.state_dir) if key.startswith(t3.MISSING)] == []
    kitchen.t3.lose_listing = False
    kitchen.t3.dropped = {GONE}
    kitchen.poll()
    kitchen.t3.dropped = set()
    kitchen.t3.lose_listing = True
    assert told(kitchen.poll()) == []
    assert f"{t3.MISSING}{GONE}" in alert.streaks(kitchen.state_dir)


def test_a_tool_jbus_stopped_naming_ends_with_no_line(kitchen, infra):
    config_key = f"{t3.MISSING}t3_thread_configuration"
    kitchen.t3.dropped = {GONE}
    kitchen.poll(NOW)
    streaks = alert.streaks(kitchen.state_dir)
    old = {**streaks[f"{t3.MISSING}{GONE}"], "key": config_key}
    kitchen.write(kitchen.state_dir / "streaks.json", json.dumps({**streaks, config_key: old}))
    assert "t3_thread_configuration" not in " ".join(told(kitchen.poll()))
    assert config_key not in alert.streaks(kitchen.state_dir)
