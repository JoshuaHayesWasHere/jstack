"""A deferred action a home writes in its plan is an item of the one list that wakes it.

A line of a home's `plan.md` that defers an action on an event no code watches ("take X out once
#12 merges", "on resume") is an item keyed `prose:<file>:<hash>`: the root's for the root plan, a
scope's for its plan. The first pass on a machine records every such line already there as told,
so only a line written after it wakes a home. A home keeps no `notes.md` now, and one left on disk
is not read. The tests run the real pass against the kitchen's fakes.
"""

import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from jbus import leftover, prose, wakes
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home

TODAY = Path(__file__).parent / "fixtures" / "prose" / "deferred-2026-10-28.txt"
NOTE = "- 2026-10-28: take X out once #12 merges"
DECISION = "Decisions: brief once foo lands"
ASK = "a home must remember this: make it a row with `--depends`, or delete the line"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


@pytest.fixture
def homes(kitchen):
    """The root home and the scope jview, each with a thread and a plan."""
    root, scoped = home(kitchen), home(kitchen, "jview")
    (kitchen.home / "plan.md").write_text("# demo: plan\n\n## x: a thing\n")
    (kitchen.home / "jview" / "plan.md").write_text("# jview: plan\n\n## jv-x: a thing\n")
    return kitchen, root["threadId"], scoped["threadId"]


def prose_wakes(kitchen, thread):
    """The messages of the one list to the thread that name a line of prose."""
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and "prose:" in given["message"]
    ]


def listed(kitchen):
    """The prose keys the one list holds as told, for any thread."""
    told = json.loads((kitchen.state / wakes.FILE).read_text())["threads"]
    return [key for seen in told.values() for key in seen if key.startswith("prose:")]


def append(path, line):
    path.write_text(path.read_text() + line + "\n")


def test_a_root_plan_line_written_after_the_seed_wakes_the_root_once_and_leaves_when_deleted(
    homes,
):
    kitchen, root, scoped = homes
    plan = kitchen.home / "plan.md"
    kitchen.poll(NOW)
    assert prose_wakes(kitchen, root) == []
    append(plan, NOTE)
    kitchen.poll(NOW + timedelta(minutes=1))
    (said,) = prose_wakes(kitchen, root)
    assert "- prose:plan.md:" in said and NOTE in said and ASK in said
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(prose_wakes(kitchen, root)) == 1
    assert prose_wakes(kitchen, scoped) == []
    plan.write_text(plan.read_text().replace(NOTE + "\n", ""))
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(prose_wakes(kitchen, root)) == 1
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=4))
    assert listed(kitchen) == []


def test_a_reworded_line_leaves_the_list_and_the_new_wording_is_told_if_it_still_defers(homes):
    kitchen, root, _ = homes
    plan = kitchen.home / "plan.md"
    kitchen.poll(NOW)
    append(plan, NOTE)
    kitchen.poll(NOW + timedelta(minutes=1))
    plan.write_text(plan.read_text().replace(NOTE, "- 2026-10-28: take X out, row x-out"))
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(prose_wakes(kitchen, root)) == 1
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=3))
    assert listed(kitchen) == []


def test_a_scope_plan_line_wakes_that_scope_once_and_the_root_once_late(homes):
    kitchen, root, scoped = homes
    plan = kitchen.home / "jview" / "plan.md"
    kitchen.poll(NOW)
    append(plan, DECISION)
    kitchen.poll(NOW + timedelta(minutes=1))
    (said,) = prose_wakes(kitchen, scoped)
    assert "- prose:jview/plan.md:" in said and DECISION in said and ASK in said
    assert prose_wakes(kitchen, root) == []
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(prose_wakes(kitchen, scoped)) == 1
    kitchen.poll(NOW + timedelta(minutes=leftover.CLOSE_MINUTES + 2))
    (late,) = prose_wakes(kitchen, root)
    assert DECISION in late and scoped in late
    assert len(prose_wakes(kitchen, scoped)) == 1
    plan.write_text(plan.read_text().replace(DECISION + "\n", ""))
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=leftover.CLOSE_MINUTES + 3))
    assert listed(kitchen) == []


def test_the_seed_pass_over_todays_lines_wakes_nobody_and_a_later_line_alone_is_told(homes):
    kitchen, root, scoped = homes
    plan = kitchen.home / "plan.md"
    shutil.copy(TODAY, plan)
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=1))
    assert prose_wakes(kitchen, root) == prose_wakes(kitchen, scoped) == []
    seeded = {one.text for one in prose.read(kitchen.state).values() if one.seeded}
    assert seeded == {one.strip() for one in TODAY.read_text().splitlines() if prose.deferred(one)}
    assert len(seeded) == 22
    append(plan, NOTE)
    kitchen.poll(NOW + timedelta(minutes=2))
    (said,) = prose_wakes(kitchen, root)
    assert said.count("- prose:") == 1


def test_a_notes_md_left_on_disk_is_not_read(homes):
    kitchen, root, _ = homes
    kitchen.poll(NOW)
    (kitchen.home / "notes.md").write_text(NOTE + "\n")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert prose_wakes(kitchen, root) == [] and listed(kitchen) == []


DEFERRED = [
    ("once merges", "take it out once #432 and #436 merge and #12 merges", True),
    ("once merged", "rerun the checks once #66 merged", True),
    ("merged once", "it merged once, on 2026-10-20", False),
    ("once lands", "brief once bot-authority-shape lands", True),
    ("once landed", "re-run the install once #202 landed", True),
    ("once on main", "tell flow once the fix is on main", True),
    ("once green", "the home merges it by hand once green", False),
    ("one sentence", "Once done, stop. The fix merges.", False),
    ("on resume", "On resume: run its check, then push", True),
    ("to resume", "To resume: re-approve the held rows", True),
    ("resume", "jbus sends a resume to the thread", False),
    ("takes it out once", "the plan entry takes it out once Josh says", True),
    ("takes it out", "the plan entry takes it out", False),
    ("when merges", "When #85 merges, lift the hold", True),
    ("when lands", "re-approve on word 877e when infra's change lands", True),
    ("when merged", "when a pull request merged, T3 settles its thread", False),
    ("until merges", "Until it merges, every resume adds a line", True),
    ("until lands", "ft-hard-lints held until its design brief lands", True),
    ("until passes", "wait until the check passes", False),
    ("re-approve when", "re-approve the row when infra sends the list", True),
    ("re-approve once", "re-approve on word 28ceb4f3 once the scout reports", True),
    ("re-approve", "re-approve the held row now", False),
    ("while holds", "make check-fast, while Josh's fast track holds", True),
    ("while", "while the pass runs, nothing else writes", False),
    ("case", "TAKE X OUT ONCE #12 MERGES", True),
    ("word", "the onceover of #12 merges nothing", False),
]


@pytest.mark.parametrize(("pattern", "line", "flagged"), DEFERRED, ids=[one[0] for one in DEFERRED])
def test_each_pattern_flags_a_deferred_action_and_not_its_near_miss(pattern, line, flagged):
    assert prose.deferred(line) is flagged
