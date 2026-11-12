"""A Result names what it waits on to merge on its `Waits on:` line, a row by its slug or a pull
request by its number, at any status, and jbus tells the crew to carry on once, when the last of
them merged (`jbus.pausedon`, `jbus.mirror.waits_on`), a number found merged by `jbus.watch.look`
asking GitHub after it once a pass. A wait written only in prose is refused by the brief lint and
by `jbus brief set|append` (`jbus.mirror.unwritten`, `jbus.brief`).

The replay is of 2026-11-11: st-code-conforms had its pull request #1718 open at head
ba66f41642f6, was told to rebase at that head, and was steered to put the rebase off until #1717,
a pull request with no row, merged. #1717 merged at 2026-11-12T00:44:47Z; the head never moved,
so the once-per-head rebase key was spent, and nothing told the crew again."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import mirror
from test_jbus_kitchen import Kitchen, asks, iso
from test_jbus_queue import add, brief

SLUG = "st-code-conforms"
HEAD = "ba66f41642f6" + "0" * 28
MERGED_AT = datetime(2026, 11, 12, 0, 44, 47, tzinfo=UTC)
STEERS = (
    "Steers: the charts home: the index page is no longer committed after #1717; on the rebase "
    "after #1717 merges drop it with `git rm`. #1717 was open when this came."
)
RESULT = (
    "\n## Result\nStatus: done\nDone when: 1 holds\n"
    f"Branch: {SLUG}   Pull request: https://example.test/pull/1718\n"
    "Steers: none\nLeft: none\n"
)


def carry_ons(kitchen):
    return [one for one in asks(kitchen) if one["clientRequestId"].startswith("waits|")]


def views_of(kitchen, number):
    log = (kitchen.stub / "gh.log").read_text().splitlines()
    return [line for line in log if line.startswith(f"pr view {number} ")]


def open_1718(kitchen):
    return {**kitchen.opened(SLUG, 1718), "headRefOid": HEAD, "mergeable": "CONFLICTING"}


def merged_1717(kitchen):
    pull = kitchen.merged("st-site-untracked", 1717, "a" * 40)
    return {**pull, "mergedAt": iso(MERGED_AT)}


@pytest.fixture
def conforms(tmp_path, monkeypatch):
    """st-code-conforms launched, its pull request #1718 open at HEAD and conflicting, its rebase
    key at HEAD already marked sent, and its Result done with `Waits on: #1717` under the
    11-11 Steers line, while #1717, a pull request no row names, is open. Its turn has ended."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.word()
    add(kitchen, SLUG)
    kitchen.poll(MERGED_AT - timedelta(minutes=40))
    (thread,) = kitchen.t3.threads
    thread["status"] = "completed"
    kitchen.t3.at_work.discard(thread["threadId"])
    path = kitchen.home / "tasks" / f"{SLUG}.md"
    path.write_text(path.read_text() + RESULT + f"{STEERS}\nWaits on: #1717\n")
    sent = jbus.read_json(kitchen.state / "sent.json", [])
    (kitchen.state / "sent.json").write_text(json.dumps([*sent, f"rebase|{SLUG}|{HEAD[:12]}"]))
    kitchen.set("open.json", [open_1718(kitchen), kitchen.opened("st-site-untracked", 1717)])
    yield kitchen
    kitchen.close()


def merge_1717(kitchen, old=False):
    kitchen.set("open.json", [open_1718(kitchen)])
    kitchen.set("merged.json", [{**merged_1717(kitchen), "old": old}])


def test_the_replay_of_1717_tells_the_crew_once_on_the_pass_after_the_merge(conforms):
    conforms.poll(MERGED_AT - timedelta(minutes=2))
    assert carry_ons(conforms) == []

    merge_1717(conforms)
    for minute in (1, 4):
        conforms.poll(MERGED_AT + timedelta(minutes=minute))

    (told,) = carry_ons(conforms)
    (thread,) = conforms.t3.threads
    assert told["threadId"] == thread["threadId"]
    assert told["clientRequestId"].startswith(f"waits|{SLUG}|#1717|")
    assert "#1717 landed" in told["message"] and f"tasks/{SLUG}.md" in told["message"]
    assert [one["clientRequestId"].split("|")[0] for one in asks(conforms)] == ["waits"]


def test_a_crew_at_work_when_the_merge_lands_is_told_on_its_first_idle_pass(conforms):
    (thread,) = conforms.t3.threads
    merge_1717(conforms)
    thread["status"] = "running"
    conforms.t3.at_work.add(thread["threadId"])
    conforms.poll(MERGED_AT + timedelta(minutes=1))
    assert carry_ons(conforms) == []

    thread["status"] = "completed"
    conforms.t3.at_work.discard(thread["threadId"])
    for minute in (4, 7):
        conforms.poll(MERGED_AT + timedelta(minutes=minute))
    assert len(carry_ons(conforms)) == 1


def test_a_wake_line_added_to_the_result_tells_nothing_again_and_a_new_result_does(conforms):
    merge_1717(conforms)
    conforms.poll(MERGED_AT + timedelta(minutes=1))
    path = conforms.home / "tasks" / f"{SLUG}.md"
    path.write_text(path.read_text() + f"Checked: make check exit 0 at {HEAD}\n")
    conforms.poll(MERGED_AT + timedelta(minutes=4))
    assert len(carry_ons(conforms)) == 1

    path.write_text(
        path.read_text() + RESULT.replace("## Result", "## Result, follow-up") + "Waits on: #1717\n"
    )
    conforms.poll(MERGED_AT + timedelta(minutes=7))
    assert len(carry_ons(conforms)) == 2


def test_a_merge_older_than_githubs_list_is_asked_for_once_by_its_number(conforms):
    merge_1717(conforms, old=True)
    conforms.poll(MERGED_AT + timedelta(minutes=1))
    assert len(views_of(conforms, 1717)) == 1
    assert len(carry_ons(conforms)) == 1

    conforms.poll(MERGED_AT + timedelta(minutes=4))
    assert len(views_of(conforms, 1717)) == 1


def test_a_number_that_never_merged_is_asked_once_and_tells_nothing(conforms):
    conforms.set("open.json", [open_1718(conforms)])
    for minute in (1, 4):
        conforms.poll(MERGED_AT + timedelta(minutes=minute))
    assert len(views_of(conforms, 1717)) == 1
    assert carry_ons(conforms) == []


@pytest.mark.parametrize(
    ("line", "slugs", "named"),
    [
        ("Waits on: #1717", set(), ("#1717",)),
        ("Waits on: `st-pr`, #12", {"st-pr"}, ("#12", "st-pr")),
        ("Waits on: #1717 st-typo", {"st-pr"}, ()),
        ("Waits on: #1717.", set(), ()),
        ("Waits on: 1717", set(), ()),
    ],
)
def test_a_waits_on_line_reads_numbers_beside_slugs_and_one_unknown_word_empties_it(
    line, slugs, named
):
    for status in ("done", "paused", "not done"):
        assert mirror.waits_on(f"## Result\nStatus: {status}\n{line}\n", slugs) == named


def test_the_brief_lint_refuses_the_11_11_steers_prose_with_no_waits_on_line(conforms):
    text = brief("alpha") + RESULT + STEERS + "\n"
    code, said = conforms.main("queue", "check", "alpha", stdin=text)
    assert code == 1
    assert "Steers: line waits on #1717 merging in prose" in said

    code, said = conforms.main("queue", "check", "alpha", stdin=text + "Waits on: #1717\n")
    assert code == 0, said


@pytest.mark.parametrize(
    "line",
    [
        "Left: rebase once st-pr merges",
        "Status: paused until the rebase after `st-pr` merged",
        "Steers: once st-pr's pull request merges, rebase",
    ],
)
def test_brief_append_refuses_a_line_that_waits_on_a_merge_in_prose(conforms, line):
    path = conforms.home / "tasks" / f"{SLUG}.md"
    before = path.read_text()
    code, said = conforms.main("brief", "append", str(path), stdin=line + "\n")
    assert code != 0 and "st-pr merging in prose" in said
    assert path.read_text() == before

    code, said = conforms.main("brief", "set", str(path), "--result", "Waits on:", "st-pr #1717")
    assert code == 0, said
    code, said = conforms.main("brief", "append", str(path), stdin=line + "\n")
    assert code == 0, said


def test_brief_set_refuses_a_steers_line_whose_merge_is_not_on_waits_on(conforms):
    path = conforms.home / "tasks" / f"{SLUG}.md"
    code, said = conforms.main(
        "brief", "set", str(path), "--result", "Left:", "push after #1800 merges"
    )
    assert code != 0 and "#1800 merging in prose" in said
    code, said = conforms.main("brief", "set", str(path), "--result", "Left:", "after #1717 merges")
    assert code == 0, said
