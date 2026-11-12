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
