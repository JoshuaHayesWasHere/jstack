"""A plan entry whose `Builds on:` has merged and that has no row of its own wakes its home to
brief it.

Each pass reads every home's plan, the root's and each scope's. An entry whose `Builds on:` line
names rows or entries that have all merged, and that has no queue row (a scout's included), is an
item of the one list that wakes the entry's home once: `brief <entry>: <dep> merged`. It leaves
the list on the entry's first row. A parked or scouting entry raises nothing, and the entry's
`Decisions:` text is never read for a wait. The tests run the real pass against the kitchen's fakes.
"""

import json

import pytest

from jbus import wakes
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home, later
from test_jbus_queue import brief, go
from test_jbus_row_ends import PULL, result
from test_jbus_scout import request

PLAN = """\
# demo: plan

## next: build on a
Stage: planned
Size: S
Builds on: a: the table a adds
Done when:
- it works
Decisions:
- "brief once a lands"
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def planned(kitchen, text, scope=""):
    (kitchen.home / scope / "plan.md").write_text(text)


def queued(kitchen, slug, entry="", more="", scope=""):
    """Queue an approved row for `slug`, under the entry `entry` where one is given."""
    text = brief(slug, more)
    if scope:
        text = text.replace("Home: mcp:a-home\n", f"Home: {scope}\n")
    argv = ["queue", "add", slug, "--priority", "1", *(["--entry", entry] if entry else [])]
    code, said = kitchen.main(*argv, stdin=text)
    assert code == 0, said
    assert go(kitchen, slug)[0] == 0


def merged(kitchen, *slugs):
    """End each row the way a crew's ends when its pull request merged."""
    pulls = []
    for number, slug in enumerate(slugs, start=9):
        kitchen.t3.thread(slug, "completed", settled=True)
        kitchen.brief(slug, result(pull=PULL))
        pulls.append(kitchen.merged(slug, number, "a" * 40))
    kitchen.set("merged.json", pulls)


def briefs(kitchen, thread):
    """The messages of the one list to the thread that ask for an entry's brief."""
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and "- brief " in given["message"]
    ]


def told(kitchen):
    kept = json.loads((kitchen.state / wakes.FILE).read_text())["threads"]
    return [key for seen in kept.values() for key in seen if key.startswith("brief ")]


def test_an_entry_whose_builds_on_merged_and_has_no_row_wakes_its_home_once(kitchen):
    """The Proves it of plan-builds-on-fires: `Builds on: a`, row `a` merged, no row for the
    entry: one wake, then none, and the item leaves the list on the entry's first row."""
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN)
    queued(kitchen, "a")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    (said,) = briefs(kitchen, thread)
    assert "- brief next: a merged" in said
    assert "jbus queue add <slug> --entry next" in said
    kitchen.poll(later(5))
    assert len(briefs(kitchen, thread)) == 1

    queued(kitchen, "next-1", entry="next", more="Builds on: a: the table a adds\n")
    kitchen.poll(later(10))
    assert len(briefs(kitchen, thread)) == 1
    assert told(kitchen) == []


def test_an_entry_whose_builds_on_has_not_merged_wakes_nobody(kitchen):
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN)
    queued(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []


def test_an_entry_with_a_scout_of_its_own_wakes_nobody(kitchen):
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN)
    queued(kitchen, "a")
    asked = request("next-design", asked="how should next build on a")
    code, said = kitchen.main(
        "queue", "add", "next-design", "--priority", "1", "--entry", "next", stdin=asked
    )
    assert code == 0, said
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []


def test_a_wait_written_only_in_decisions_wakes_nobody(kitchen):
    """plan.md's `Decisions:` text is not read: "brief once a lands" with no `Builds on:` line
    raises nothing when `a` merges."""
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN.replace("Builds on: a: the table a adds\n", ""))
    queued(kitchen, "a")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []


def test_an_entry_waits_for_every_row_its_builds_on_names(kitchen):
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN.replace("Builds on: a: the table a adds", "Builds on: a, b"))
    queued(kitchen, "a")
    queued(kitchen, "b")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []
    merged(kitchen, "a", "b")
    kitchen.poll(later(5))
    (said,) = briefs(kitchen, thread)
    assert "- brief next: a, b merged" in said


def test_a_builds_on_line_wrapped_onto_a_second_line_is_read_whole(kitchen):
    """The line is read as a brief's is: an item wrapped onto the next line is still one it waits
    on."""
    thread = home(kitchen)["threadId"]
    wrapped = "Builds on: a: the table a adds;\n  b: the view b adds"
    planned(kitchen, PLAN.replace("Builds on: a: the table a adds", wrapped))
    queued(kitchen, "a")
    queued(kitchen, "b")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []
    merged(kitchen, "a", "b")
    kitchen.poll(later(5))
    (said,) = briefs(kitchen, thread)
    assert "- brief next: a, b merged" in said


SCOPED = """\
# jview: plan

## bot-feed: a feed for the bots
Stage: planned
Size: M
Builds on: bot-authority
Done when:
- it feeds
"""


def test_a_scoped_entry_whose_builds_on_names_a_merged_entry_wakes_its_own_home(kitchen):
    """The case of bot-feed: its `Builds on:` names the entry bot-authority, whose rows have all
    merged under other slugs. The scope's home is woken, and the root's is not."""
    root, scoped = home(kitchen)["threadId"], home(kitchen, "jview")["threadId"]
    planned(kitchen, "# demo: plan\n")
    planned(kitchen, SCOPED, scope="jview")
    queued(kitchen, "bot-authority-shape", entry="bot-authority")
    queued(kitchen, "no-webhook-path", entry="bot-authority")
    merged(kitchen, "bot-authority-shape")
    kitchen.poll(NOW)
    assert briefs(kitchen, scoped) == []
    merged(kitchen, "bot-authority-shape", "no-webhook-path")
    kitchen.poll(later(5))
    (said,) = briefs(kitchen, scoped)
    assert "- brief jview/bot-feed: bot-authority merged" in said
    assert "the jview home's plan" in said
    assert briefs(kitchen, root) == []


def test_a_parked_entry_wakes_nobody_when_its_builds_on_merged(kitchen):
    """A parked entry is one the user said waits: its `Builds on:` merging does not ask for it."""
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN.replace("Stage: planned", "Stage: parked"))
    queued(kitchen, "a")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []


def test_a_scouting_entry_wakes_nobody_when_its_builds_on_merged(kitchen):
    """`Stage: scouting` says a scout is out for the entry: its `Builds on:` merging does not ask
    for a brief before that scout reports."""
    thread = home(kitchen)["threadId"]
    planned(kitchen, PLAN.replace("Stage: planned", "Stage: scouting"))
    queued(kitchen, "a")
    merged(kitchen, "a")
    kitchen.poll(NOW)
    assert briefs(kitchen, thread) == []
