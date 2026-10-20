"""`jbus noticed`: each `Noticed` line of the briefs and the scout requests is one record in
`noticed.json`, found by a pass and marked once, taken or dropped, by a home. Run as
`tests/test_jbus.py` runs: the real command and the real pass, against a faked T3 Code
server, `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

from jbus import noticed
from test_jbus_kitchen import NOW, Kitchen, complete

AT = "2026-10-12 10:58 ET"
WORD = ("--by", "home", "--at", AT)
RESULT = """
## Result
Status: done
Noticed: the view shows a finished row as stuck.
Left: none
"""
LISTED = """
## Result, follow-up (2026-10-12, a steer)
Status: done
Noticed:
- follow-up: info src/a.py:3 a name is wrong
- the docs say two things
Left: none

## Review
Verdict: findings
Noticed, from the review: jmerge has no lock around a run.
"""
NOTHING = """
## Result
Noticed: none
Left: none

## Result, follow-up (2026-10-12, again)
Noticed:
Left: none
"""
REPORT = """
## Report
Status: done
Noticed: a scout found the home reads nothing of this.
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def kept(kitchen):
    return json.loads((kitchen.state / noticed.NAME).read_text())["records"]


def say(kitchen, *argv):
    code, said = kitchen.main("--project", "demo", "noticed", *argv)
    assert code == 0, said
    return said


def launched(kitchen, *slugs, kind="tasks"):
    """Briefs or requests a pass reads before anything is written in them, as it reads a brief
    or request out in a thread: a file it never read is one a backup put back."""
    for slug in slugs:
        kitchen.brief(slug, kind=kind)


def test_the_first_pass_drops_what_was_there_and_later_passes_add_each_new_line_once(kitchen):
    kitchen.brief("old", RESULT)
    launched(kitchen, "alpha", "beta")
    launched(kitchen, "gamma", kind="scouts")
    kitchen.poll(NOW - timedelta(hours=1))
    (before,) = kept(kitchen)
    assert (before["slug"], before["mark"], before["why"], before["by"]) == (
        "old",
        "dropped",
        "from before the list",
        "jbus",
    )
    assert say(kitchen) == "none is new\n"

    kitchen.brief("alpha", RESULT + LISTED)
    kitchen.brief("beta", NOTHING)
    kitchen.brief("gamma", REPORT, kind="scouts")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=5))
    records = kept(kitchen)
    assert [
        (one["slug"], one["kind"], one["section"], one["label"], one["text"]) for one in records
    ] == [
        ("old", "tasks", "Result", "Noticed", "the view shows a finished row as stuck."),
        ("alpha", "tasks", "Result", "Noticed", "the view shows a finished row as stuck."),
        (
            "alpha",
            "tasks",
            "Result, follow-up (2026-10-12, a steer)",
            "Noticed",
            "follow-up: info src/a.py:3 a name is wrong",
        ),
        (
            "alpha",
            "tasks",
            "Result, follow-up (2026-10-12, a steer)",
            "Noticed",
            "the docs say two things",
        ),
        (
            "alpha",
            "tasks",
            "Review",
            "Noticed, from the review",
            "jmerge has no lock around a run.",
        ),
        ("gamma", "scouts", "Report", "Noticed", "a scout found the home reads nothing of this."),
    ]
    assert [one["mark"] for one in records] == ["dropped", "new", "new", "new", "new", "new"]
    assert {one["seen_at"] for one in records[1:]} == {"2026-10-12T15:00:00+00:00"}
    assert records[1]["key"] == noticed.key("alpha", "the view shows a finished row as stuck.")
    assert len({one["key"] for one in records}) == 6


def test_noticed_prints_the_new_ones_all_of_them_or_json(kitchen):
    launched(kitchen, "alpha", "beta")
    kitchen.poll(NOW - timedelta(hours=1))
    kitchen.brief("alpha", RESULT)
    kitchen.poll()
    kitchen.brief("beta", REPORT.replace("## Report", "## Result"))
    kitchen.poll(NOW + timedelta(minutes=5))
    alpha = noticed.key("alpha", "the view shows a finished row as stuck.")
    beta = noticed.key("beta", "a scout found the home reads nothing of this.")
    assert say(kitchen).splitlines() == [
        f"{beta} beta, Result, new: a scout found the home reads nothing of this.",
        f"{alpha} alpha, Result, new: the view shows a finished row as stuck.",
    ]
    say(kitchen, "drop", beta, "--why", "the scout's own   doubt", *WORD)
    assert say(kitchen).splitlines() == [
        f"{alpha} alpha, Result, new: the view shows a finished row as stuck."
    ]
    assert say(kitchen, "--all").splitlines()[0] == (
        f"{beta} beta, Result, dropped: the scout's own doubt: a scout found the home reads "
        "nothing of this."
    )
    shown = json.loads(say(kitchen, "--json"))
    assert [(one["key"], one["mark"]) for one in shown] == [(alpha, "new")]
    every = json.loads(say(kitchen, "--all", "--json"))
    assert [(one["key"], one["mark"], one["by"], one["at"]) for one in every] == [
        (beta, "dropped", "home", AT),
        (alpha, "new", "", ""),
    ]


def test_a_line_is_taken_by_a_queue_row_or_a_plan_entry_and_marked_once(kitchen):
    launched(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(hours=1))
    kitchen.brief("alpha", RESULT + LISTED)
    kitchen.poll()
    first, second, docs, third = (one["key"] for one in kept(kitchen))
    assert (
        kitchen.main("queue", "add", "fix-view", "--priority", "1", stdin=complete("fix-view"))[0]
        == 0
    )
    (kitchen.home / "plan.md").write_text(
        "# plan\n\n## a-lock: a lock for jmerge\nStage: planned\n"
    )

    assert say(kitchen, "take", first, "--row", "fix-view", *WORD) == (
        f"{first} alpha, Result, taken by fix-view: the view shows a finished row as stuck.\n"
    )
    assert "taken by a-lock" in say(kitchen, "take", third, "--row", "a-lock", *WORD)
    code, said = kitchen.main("noticed", "take", second, "--row", "nothing-here", *WORD)
    assert (code, said) == (1, "refused: nothing-here is no queue row and no plan entry\n")
    code, said = kitchen.main("noticed", "drop", first, "--why", "no", *WORD)
    assert code == 1 and said.endswith(", and a line is marked once\n")
    code, said = kitchen.main("noticed", "drop", "alpha:000000000000", "--why", "no", *WORD)
    assert (code, said) == (1, "refused: no noticed line has the key alpha:000000000000\n")
    code, said = kitchen.main(
        "noticed", "drop", second, "--why", "no", "--by", "home", "--at", "now"
    )
    assert code == 1 and said.startswith('refused: --at is "<YYYY-MM-DD HH:MM ')

    marks = {one["key"]: (one["mark"], one["row"], one["by"], one["at"]) for one in kept(kitchen)}
    assert marks == {
        first: ("taken", "fix-view", "home", AT),
        second: ("new", "", "", ""),
        docs: ("new", "", "", ""),
        third: ("taken", "a-lock", "home", AT),
    }
    kitchen.poll(NOW + timedelta(minutes=5))
    assert len(kept(kitchen)) == 4


def test_a_file_that_does_not_parse_is_left_as_it_is_and_refused(kitchen):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / noticed.NAME).write_text("{not json")
    kitchen.brief("alpha", RESULT)
    kitchen.poll()
    assert (kitchen.state / noticed.NAME).read_text() == "{not json"
    code, said = kitchen.main("noticed")
    assert code == 1 and "does not parse" in said


def test_a_line_added_under_a_list_later_is_one_new_record_and_the_others_keep_their_marks(
    kitchen,
):
    launched(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(hours=1))
    kitchen.brief("alpha", LISTED)
    kitchen.poll()
    first = noticed.key("alpha", "follow-up: info src/a.py:3 a name is wrong")
    say(kitchen, "drop", first, "--why", "a one-off", *WORD)
    added = LISTED.replace(
        "- the docs say two things\n",
        "- the docs say two things\n  and the help says a third\n- follow-up: info b.py:1 later\n"
        "Woken by a check at abc123, the pull request was green\n",
    )
    kitchen.brief("alpha", added)
    kitchen.poll(NOW + timedelta(minutes=5))
    records = {one["text"]: one["mark"] for one in kept(kitchen)}
    assert records == {
        "follow-up: info src/a.py:3 a name is wrong": "dropped",
        "the docs say two things": "new",
        "the docs say two things\nand the help says a third": "new",
        "follow-up: info b.py:1 later": "new",
        "jmerge has no lock around a run.": "new",
    }


def test_bare_follow_up_lines_and_a_nested_item_are_read_as_the_crew_skill_writes_them(kitchen):
    kitchen.poll(NOW - timedelta(hours=1))
    kitchen.brief(
        "alpha",
        "\n## Review\nVerdict: findings\nNoticed, from the review:\n"
        "follow-up: info src/a.py:3 a name is wrong\n"
        "follow-up: info src/b.py:9 a test is missing\n"
        "- a parent\n  - its child\n"
        "Woken by a check at abc123 the pull request was green\n",
    )
    kitchen.poll()
    assert [one["text"] for one in kept(kitchen)] == [
        "follow-up: info src/a.py:3 a name is wrong",
        "follow-up: info src/b.py:9 a test is missing",
        "a parent\n- its child",
    ]


def test_a_restored_file_no_row_names_is_dropped_and_a_queued_brief_is_new(kitchen):
    """A project past its first pass gets back from a backup a brief and a request a pass never
    read: their lines are from before. A brief a row of the queue names is out, and its lines
    are new however soon after the launch they are written."""
    kitchen.poll(NOW - timedelta(hours=1))
    assert kitchen.main("queue", "add", "live", "--priority", "1", stdin=complete("live"))[0] == 0
    kitchen.brief("restored", RESULT + LISTED)
    kitchen.brief("an-old-scout", REPORT, kind="scouts")
    kitchen.brief("live", RESULT)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=5))
    marks = {(one["slug"], one["mark"], one["why"]) for one in kept(kitchen)}
    assert marks == {
        ("restored", "dropped", noticed.FROM_BEFORE),
        ("an-old-scout", "dropped", noticed.FROM_BEFORE),
        ("live", "new", ""),
    }
    assert say(kitchen).splitlines() == [
        f"{noticed.key('live', 'the view shows a finished row as stuck.')} live, Result, new: "
        "the view shows a finished row as stuck."
    ]
