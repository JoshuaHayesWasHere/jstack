"""An alert is on the one list only while a home can clear it (`jbus.alert.open_items`).

A closed project runs no pass, so nothing ends an alert about it: that alert leaves the list at
`jbus project close`, and comes back at `jbus project open` while its cause still holds. Like
`test_jbus_project_close.py`, the test runs the real commands and the real pass against the
kitchen's fakes."""

from datetime import timedelta

import jbus
from jbus import passes, wakes
from test_jbus_kitchen import NOW, sends
from test_jbus_merge import DIES

ALERT = "alert: jmerge other failed"


def at(minutes):
    return NOW + timedelta(minutes=minutes)


def listed(now):
    """For each open project, the lines of `other`'s jmerge alert on the one list its home is
    woken from."""
    config = jbus.load()
    return {
        one.name: [
            item.line
            for item in wakes.alert_items(passes.Pass(config, one, now))
            if item.line.startswith(ALERT)
        ]
        for one in config.projects
    }


def told(kitchen):
    """The messages of the one list that the passes sent to a home thread."""
    return [one["message"] for one in sends(kitchen) if one["clientRequestId"].startswith("wakes|")]


def test_a_closed_projects_alert_leaves_the_list_and_comes_back_when_it_opens(kitchen):
    """`other`'s jmerge fails pass after pass until it alerts. Closed, it runs no pass, and no
    home, the infra project's neither, holds or is told of its alert. Opened again with its
    jmerge still failing, its own home's list has the alert again."""
    kitchen.second()
    kitchen.config(infra="demo")
    kitchen.set("jmerge-dies", DIES)
    for minute in range(3):
        kitchen.poll(at(minute))
    before = listed(at(3))
    assert (before["demo"], len(before["other"])) == ([], 1)

    assert kitchen.main("project", "close", "other")[0] == 0
    was = len(told(kitchen))
    kitchen.poll(at(5))
    kitchen.poll(at(6))
    assert listed(at(6)) == {"demo": []}
    assert [one for one in told(kitchen)[was:] if ALERT in one] == []

    assert kitchen.main("project", "open", "other")[0] == 0
    kitchen.poll(at(7))
    assert listed(at(7)) == {"demo": [], "other": before["other"]}


LEGACY = {
    "alerted": True,
    "count": 9,
    "key": "jmerge case-control",
    "since": "2026-10-28T00:51:47.266083+00:00",
}


def kept(kitchen, *records):
    """Put these records into the machine's `streaks.json`, as an older jbus left them."""
    path = kitchen.state_dir / "streaks.json"
    have = jbus.read_json(path, {})
    jbus.write_json(path, have | {one["key"]: one for one in records}, mode=0o600)


def items(now):
    """For each open project, the alert items on the one list its home is woken from."""
    config = jbus.load()
    return {
        one.name: [
            (item.key, item.line) for item in wakes.alert_items(passes.Pass(config, one, now))
        ]
        for one in config.projects
    }


def test_an_alert_with_no_line_is_no_item_and_wakes_no_home_with_an_empty_line(kitchen):
    """A record kept before alerts had a line and an owner (#731), under a project name that is
    gone, is owned by no one, so it falls to the infra project. Its line says nothing: no home
    could act on it, so it is no item of the list, and no wake carries a bare `- `."""
    kitchen.config(infra="demo")
    kept(kitchen, LEGACY)
    kitchen.poll(at(0))
    kitchen.poll(at(1))
    assert items(at(1)) == {"demo": []}
    assert [one for one in told(kitchen) if "- " in one.splitlines()] == []


STALL = "home-stall /: the root home is still quiet after two nudges, 181 min: ..."


def test_a_closed_projects_stall_wakes_no_infra_home(kitchen):
    """The record of the incident: a stall of the closed project's root home, owned by that
    project. Closed, it falls to the infra project, whose list holds no item for it and whose
    wake says nothing of it (#1762)."""
    kitchen.second()
    kitchen.config(infra="demo")
    assert kitchen.main("project", "close", "other")[0] == 0
    kept(
        kitchen,
        {
            "alerted": True,
            "count": 1,
            "key": "home-stall other /",
            "since": "2026-11-07T14:51:00+00:00",
            "owner": "other",
            "line": STALL,
        },
    )
    kitchen.poll(at(0))
    kitchen.poll(at(1))
    assert items(at(1)) == {"demo": []}
    assert [one for one in told(kitchen) if "home-stall" in one] == []
