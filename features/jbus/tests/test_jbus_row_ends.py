"""A row whose thread ended says how: `done`, `left` and why, or `merged` with what is left.

Run as `test_jbus_queue.py` runs: the real pass, against a faked T3 Code server, `gh`
and `jmerge`, over briefs that are made up."""

import json
from datetime import timedelta

import pytest

import jbus
import jsettings
from jbus import digest, leftover
from jbus.view import state
from test_jbus_kitchen import NOW
from test_jbus_queue import add, brief, rows

PULL = "https://example.test/pull/9"


def result(left="none", status="done", pull="none"):
    return f"\n## Result\nStatus: {status}\nBranch: a-branch   Pull request: {pull}\nLeft: {left}\n"


def sends(kitchen):
    """Each message a pass sent a thread: the fake keeps one per request id, so count the calls."""
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def listed(kitchen, kind="left"):
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return [one["line"] for one in kept if one["kind"] == kind]


def line(slug, why):
    """A leftover's line on the list. One whose Result has a `Left:` line says why it is the
    user's: these rows have no home to tell."""
    return f"left {slug}: {why}" + (f"; {leftover.NO_HOME}" if why.startswith("left: ") else "")


def sent_keys(kitchen):
    return jbus.read_json(kitchen.state / "sent.json", [])


def column(kitchen, slug="alpha"):
    row = rows(kitchen)[slug]
    return row["status"], row["pr"], row["why"]


THREADS = [
    ("completed", {}),
    ("completed", {"settled": True}),
    ("interrupted", {}),
]


@pytest.mark.parametrize(("ended", "more"), THREADS)
def test_a_thread_that_ended_done_with_nothing_left_and_no_pull_request_is_done(
    kitchen, ended, more
):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", ended, **more)
    for _ in range(2):
        kitchen.poll()
        assert column(kitchen) == ("done", "", "")
        assert jbus.read_json(kitchen.state / "waiting-on-user.json", None) == []
    assert kitchen.t3.launches == [] and kitchen.lines("gate") == []
    moves = (kitchen.state / "transitions.jsonl").read_text().splitlines()
    assert [(json.loads(m)["from"], json.loads(m)["to"]) for m in moves] == [("queued", "done")]


def test_a_row_launched_from_a_brief_that_holds_a_result_is_launched_not_done(kitchen):
    text = brief("alpha") + result()
    add(kitchen, "alpha", text=text)
    kitchen.t3.on_list = kitchen.t3.threads.clear
    kitchen.poll()
    assert len(kitchen.t3.launches) == 1
    assert column(kitchen) == ("launched", "", "")


@pytest.mark.parametrize(
    ("made", "why"),
    [
        (result("the user's sign-off on the sketch"), "left: the user's sign-off on the sketch"),
        (result(status="blocked"), "status: blocked"),
        (result(status="paused, at abc123"), "status: paused, at abc123"),
        (result("x" * 200), "left: " + "x" * 95 + "[cut]"),
        (result(pull=PULL), "pull request #9 is not open and not merged"),
        (result(pull=PULL + "/files"), "pull request is not open and not merged"),
        ("\n## Result\nStatus: done\nLeft: none\n", "its Result has no Branch line"),
    ],
)
def test_a_thread_that_ended_with_something_left_says_so_and_is_listed_once(kitchen, made, why):
    add(kitchen, "alpha")
    kitchen.brief("alpha", made)
    kitchen.t3.thread("alpha", "completed")
    for _ in range(3):
        kitchen.poll()
        assert column(kitchen) == ("left", "", why)
        assert listed(kitchen) == [line("alpha", why)]
    assert kitchen.lines("gate") == [] and kitchen.t3.launches == []
    assert len(kitchen.lines("waiting")) <= 1


def test_the_item_is_told_once_and_goes_when_the_result_leaves_nothing(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    thread["status"] = "completed"
    path = kitchen.home / "tasks" / "alpha.md"
    launched = path.read_text()
    path.write_text(launched + result("a word from the user"))
    kitchen.poll()
    kitchen.poll()
    assert kitchen.lines("waiting") == ["waiting demo: 2 wait on user, 1 new (left alpha), 0 gone"]
    path.write_text(launched + result())
    kitchen.poll()
    assert column(kitchen) == ("done", "", "") and listed(kitchen) == []


def test_the_item_goes_with_its_row(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result("a word from the user"))
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert listed(kitchen) == [line("alpha", "left: a word from the user")]
    (kitchen.state / "queue.json").write_text("[]")
    kitchen.poll()
    assert listed(kitchen) == []


def test_a_row_that_depends_on_a_done_row_is_launched_and_on_a_left_row_waits(kitchen):
    add(kitchen, "design")
    add(kitchen, "sketch")
    add(kitchen, "build", priority=2, depends="design")
    add(kitchen, "paint", priority=3, depends="sketch")
    kitchen.brief("design", result())
    kitchen.brief("sketch", result("a word from the user"))
    for slug in ("design", "sketch"):
        kitchen.t3.thread(slug, "completed", settled=True)
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: build"]
    assert column(kitchen, "paint") == ("queued", "", "depends on sketch")


def test_a_result_written_under_a_thread_still_at_work_is_done(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    thread = kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    thread.update(status="running", settled=False)
    kitchen.poll()
    assert column(kitchen) == ("done", "", "")


def test_a_row_that_was_never_launched_is_queued_whatever_an_old_brief_says(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", result())
    kitchen.poll()
    assert column(kitchen) == ("queued", "", "not approved")


AFTER = "after the merge, the tool is installed again"


def merged_with_work_left(kitchen):
    add(kitchen, "alpha")
    thread = kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n" + result(AFTER, pull=PULL))
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    return thread


def test_a_merge_with_work_left_for_after_it_tells_the_thread_once(kitchen):
    thread = merged_with_work_left(kitchen)
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", f"left: {AFTER}")
    (sent,) = sends(kitchen)
    assert (sent["threadId"], sent["mode"]) == (thread["threadId"], "queue")
    assert sent["message"].startswith("jbus: pull request #9 of this task is merged")
    assert "tasks/alpha.md" in sent["message"]
    assert listed(kitchen) == []
    said = kitchen.poll() + kitchen.poll()
    assert len(sends(kitchen)) == 1 and not [line for line in said if line.startswith("told")]
    assert listed(kitchen) == [line("alpha", f"left: {AFTER}")]


def test_a_thread_that_took_up_the_work_after_the_merge_is_not_the_users(kitchen):
    thread = merged_with_work_left(kitchen)
    kitchen.poll()
    thread.update(status="running", settled=False)
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", f"left: {AFTER}") and listed(kitchen) == []
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text() + "\n## Result, follow-up (2026-10-13, the merge)" + result())
    thread["status"] = "completed"
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "") and listed(kitchen) == []
    assert len(sends(kitchen)) == 1


def test_a_merge_that_could_not_be_told_is_told_on_the_next_pass(kitchen):
    merged_with_work_left(kitchen)
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert any(line.startswith("wait alpha: its crew could not be told") for line in said)
    assert kitchen.t3.messages == {} and listed(kitchen) == [line("alpha", f"left: {AFTER}")]
    kitchen.t3.lose_send = False
    kitchen.poll()
    kitchen.poll()
    assert len(kitchen.t3.messages) == 1 and len(sends(kitchen)) == 2


def test_a_merge_t3_code_refuses_to_tell_is_a_wait_line_each_pass_and_the_users(kitchen):
    merged_with_work_left(kitchen)
    kitchen.t3.refuse_send = True
    for _ in range(2):
        said = kitchen.poll()
        assert [line for line in said if line.startswith("wait alpha: its crew could not be told")]
        assert column(kitchen) == ("merged", "#9", f"left: {AFTER}")
        assert listed(kitchen) == [line("alpha", f"left: {AFTER}")]
    assert kitchen.lines("gate") == []


def test_the_thread_is_not_told_again_after_the_weekly_prune(kitchen):
    add(kitchen, "alpha")
    thread = kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n" + result(AFTER, pull=PULL))
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40, ago=timedelta(days=8))])
    kitchen.poll()
    kitchen.poll()
    assert len(sends(kitchen)) == 1
    kitchen.poll(NOW + timedelta(hours=7))
    assert kitchen.lines("snapshot") and "merged|alpha|#9" in sent_keys(kitchen)
    assert not [key for key in sent_keys(kitchen) if key.startswith("result|alpha|")]
    kitchen.poll(NOW + timedelta(hours=7, minutes=1))
    assert len(sends(kitchen)) == 1
    assert listed(kitchen) == [line("alpha", f"left: {AFTER}")]


@pytest.mark.parametrize(
    ("made", "why", "told"),
    [
        (result("After the merge, install it", pull=PULL), "left: After the merge, install it", 1),
        (result("the docs", pull=PULL), "left: the docs", 0),
        (result(status="blocked", pull=PULL), "status: blocked", 0),
    ],
)
def test_a_merged_row_says_whatever_its_result_leaves_and_only_after_the_merge_is_told(
    kitchen, made, why, told
):
    add(kitchen, "alpha")
    thread = kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n" + made)
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", why)
    assert listed(kitchen) == [line("alpha", why)] and len(sends(kitchen)) == told


def test_a_merged_row_whose_brief_has_no_result_is_over_and_on_no_list(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.brief("alpha")
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "") and listed(kitchen) == []
    assert digest.build(jbus.load(), now=NOW)["projects"]["demo"]["rows"] == []


def test_a_thread_jbus_settled_at_the_merge_and_then_told_is_at_work_by_its_status(kitchen):
    add(kitchen, "alpha")
    thread = kitchen.t3.thread("alpha", "completed")
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n" + result(AFTER, pull=PULL))
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    assert thread["settled"] and len(sends(kitchen)) == 1
    thread["status"] = "running"
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", f"left: {AFTER}") and listed(kitchen) == []
    thread["status"] = "completed"
    kitchen.poll()
    assert listed(kitchen) == [line("alpha", f"left: {AFTER}")]


def test_a_gh_that_fails_on_the_address_a_brief_names_gives_no_answer_for_the_pass(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(pull=PULL))
    kitchen.t3.thread("alpha", "completed", settled=True)
    old = kitchen.merged("another-name", 9, "a" * 40, ago=timedelta(days=30))
    kitchen.set("merged.json", [{**old, "old": True, "url": "https://example.test/pull/90"}])
    kitchen.poll()
    assert column(kitchen) == ("left", "", "pull request #9 is not open and not merged")
    gh = kitchen.stub / "gh"
    gh.write_text(gh.read_text().replace('elif args[:2] == ["pr", "view"]:', "elif 0:"))
    said = kitchen.poll()
    assert any(line.startswith("wait demo: could not ask GitHub: gh exited ") for line in said)
    assert column(kitchen) == ("left", "", "pull request #9 is not open and not merged")


def test_a_merge_that_leaves_nothing_tells_nobody(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.brief("alpha", result(pull=PULL))
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "") and kitchen.t3.messages == {}


def test_a_pull_request_is_its_briefs_whatever_its_branch_is_called(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(pull=PULL))
    kitchen.t3.thread("alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("another-name", 9)])
    kitchen.poll()
    assert column(kitchen) == ("pr", "#9", "") and kitchen.lines("gate") == []
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("another-name", 9, "a" * 40)])
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "")
    assert kitchen.lines("merged") == [f"merged alpha #9 {'a' * 12}"]


def test_a_pull_request_of_another_repository_with_the_same_number_claims_nothing(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    kitchen.brief("alpha", result(pull="https://example.com/them/theirs/pull/9"))
    kitchen.brief("beta")
    for slug in ("alpha", "beta"):
        kitchen.t3.thread(slug, "completed")
    kitchen.set("open.json", [kitchen.opened("beta", 9)])
    said = kitchen.poll()
    assert column(kitchen, "beta") == ("pr", "#9", "")
    assert column(kitchen) == ("left", "", "pull request #9 is not open and not merged")
    assert not [line for line in said if "could not ask GitHub" in line]


def test_a_revert_names_the_slug_of_the_brief_not_the_branch(kitchen):
    kitchen.brief("alpha", result(pull="https://example.test/pull/7"))
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("another-name", 7, "a" * 40)])
    kitchen.set("commits.json", [kitchen.commit("d" * 40, f"Revert {'a' * 40}")])
    kitchen.poll()
    assert kitchen.lines("retro") == [f"retro alpha: reverted by {'d' * 12}"]


def test_a_pass_github_does_not_answer_keeps_the_item(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result("a word from the user"))
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    (kitchen.stub / "gh-down").touch()
    kitchen.poll()
    assert listed(kitchen) == [line("alpha", "left: a word from the user")]


def test_a_merge_that_fell_out_of_the_list_is_asked_for_by_the_address_the_brief_names(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(pull=PULL))
    kitchen.t3.thread("alpha", "completed", settled=True)
    old = kitchen.merged("another-name", 9, "a" * 40, ago=timedelta(days=30))
    kitchen.set("merged.json", [{**old, "old": True}])
    kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "")
    assert [line for line in kitchen.log("gh") if line.startswith("pr view")] == [
        f"pr view {PULL} --json number,url,title,headRefName,mergeCommit,mergedAt,state"
    ]
    kitchen.poll()
    assert len([line for line in kitchen.log("gh") if line.startswith("pr view")]) == 1


def scene(kitchen):
    """Four rows that ended: done, with work left, merged with work left, and merged."""
    for slug in ("done", "left", "after", "merged"):
        add(kitchen, slug)
        kitchen.t3.thread(slug, "completed", settled=True)
    kitchen.brief("done", result())
    kitchen.brief("left", result("a word from the user"))
    kitchen.brief("after", result(AFTER, pull=PULL))
    kitchen.brief("merged", result(pull="https://example.test/pull/8"))
    pulls = [kitchen.merged("after", 9, "a" * 40), kitchen.merged("merged", 8, "b" * 40)]
    kitchen.set("merged.json", pulls)
    kitchen.poll()
    kitchen.poll()


def test_the_digest_has_the_rows_that_leave_something_and_names_the_ones_done(kitchen):
    scene(kitchen)
    demo = digest.build(jbus.load(), now=NOW)["projects"]["demo"]
    assert [(row["slug"], row["status"], row["why"]) for row in demo["rows"]] == [
        ("after", "merged", f"left: {AFTER}"),
        ("left", "left", "left: a word from the user"),
    ]
    assert [one["slug"] for one in demo["done"]] == ["done"]
    assert demo["pulls"] == []
    assert sorted(one["slug"] for one in demo["merged"]) == ["after", "merged"]
    assert [one["line"] for one in demo["waiting"]] == [
        line("after", f"left: {AFTER}"),
        line("left", "left: a word from the user"),
    ]


def test_the_view_has_the_same_rows_at_the_gate_step_as_the_users(kitchen):
    scene(kitchen)
    sources = state.Sources(kitchen.state_dir, kitchen.root / "home", user=jsettings.DEFAULTS)
    built = state.build(sources, "demo", NOW, lambda repo: {"runs": [], "at": None, "error": ""})
    assert [(t["slug"], t["status"], t["step"], t["who"]) for t in built["tasks"]] == [
        ("after", "merged", "gate", "user"),
        ("left", "left", "gate", "user"),
    ]
    after, left = (t["reason"] for t in built["tasks"])
    assert after.startswith("its pull request #9 is merged and the work is done. ")
    assert f"left a note of something it did not do: {AFTER}. " in after
    assert left.startswith("it ended with no pull request and the work is done. ")
    assert "left a note of something it did not do: a word from the user. " in left
    assert {t["state"]["name"] for t in built["tasks"]} == {"Ended, with a leftover"}
    kitchen.brief("left", result("a word from the user", status="paused"))
    built = state.build(sources, "demo", NOW, lambda repo: {"runs": [], "at": None, "error": ""})
    paused = built["tasks"][1]["state"]
    assert (paused["name"], "done" in paused["say"]) == ("Ended, not closed", False)
    assert built["queue"]["by_status"] == {"done": 1, "left": 1, "merged": 2}
    assert [(one["kind"], one["slug"]) for one in built["waiting"]] == [
        ("left", "after"),
        ("left", "left"),
    ]


def test_the_view_gives_a_merged_row_to_its_crewmate_while_the_list_does_not_have_it(kitchen):
    thread = merged_with_work_left(kitchen)
    kitchen.poll()
    thread.update(status="running", settled=False)
    kitchen.poll()
    assert listed(kitchen) == []
    sources = state.Sources(kitchen.state_dir, kitchen.root / "home", user=jsettings.DEFAULTS)
    built = state.build(sources, "demo", NOW, lambda repo: {"runs": [], "at": None, "error": ""})
    assert [(t["slug"], t["step"], t["who"], t["reason"]) for t in built["tasks"]] == [
        ("alpha", "running", "crew", f"left: {AFTER}")
    ]
