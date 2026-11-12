"""A rule that merged naming the open pull requests it breaks (`jmerge.preflight`) has each one's
crew told in the pass that reads its `merged` line (`jbus.rulebreaks`): #1702's four crews each
found the red alone. The tests run the real pass against the kitchen's fakes."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import rulebreaks
from jbus.passes import Pass
from jmerge import lines
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add

HEAD = "c" * 40
COMMIT = "abc1234def56789"
RULE = "features/skill-library/tests/test_statechart_site.py"


def merged(*numbers):
    notes = [lines.rule_breaks([RULE], numbers)]
    return lines.merged(1702, "rule", COMMIT, "a rule", notes, "https://example.test/pull/1702")


@pytest.fixture
def launched(tmp_path, monkeypatch):
    """Alpha is a row a first pass launched, #7 open at `HEAD`, and its crew's turn has ended."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": HEAD}])
    yield kitchen
    kitchen.close()


def told(kitchen):
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["clientRequestId"].startswith(rulebreaks.KIND)
    ]


def owed(kitchen):
    return json.loads((kitchen.state / rulebreaks.FILE).read_text())


def test_the_crew_of_a_pull_request_a_merged_rule_breaks_is_told_in_the_pass_that_reads_it(
    launched,
):
    launched.set("jmerge.txt", merged(7, 8) + "\n")
    launched.poll(NOW)
    (one,) = told(launched)
    assert one["threadId"] == "mcp:thread-1"
    assert one["clientRequestId"] == f"rule-breaks|alpha|{HEAD[:12]}|{COMMIT[:12]}"
    assert "#1702 merged at abc1234def56" in one["message"] and RULE in one["message"]
    assert "#7 fails" in one["message"]
    assert owed(launched) == [], "#8 is not open, so nobody owes it a message"
    launched.set("jmerge.txt", "")
    launched.poll(NOW + timedelta(minutes=1))
    assert len(told(launched)) == 1


def test_a_merge_the_tick_printed_is_kept_for_the_next_pass(launched):
    config = jbus.load()
    run = Pass(config, config.project("demo"), NOW)
    rulebreaks.keep(run, [merged(7)])
    assert [one["breaks"] for one in owed(launched)] == [[7]]
    launched.poll(NOW)
    assert len(told(launched)) == 1
    assert owed(launched) == []
