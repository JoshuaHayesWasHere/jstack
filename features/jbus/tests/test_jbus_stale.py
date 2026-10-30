"""`jbus stale --project <p>` lists the state nothing will act on again, five kinds of it, and
deletes nothing. Each hour a pass counts the same, and the root home hears the count from the one
list. The tests run the command and the real pass against the kitchen's fakes, over state made up
here.
"""

import json
from datetime import timedelta

import pytest

from jbus import leftover, questions, stale, wakes
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home

CLEAN = "\n## Result\nStatus: done\nBranch: {slug}   Pull request: none\nLeft: none\n"
LEFT = "\n## Result\nStatus: not done\nBranch: {slug}   {pull}\nLeft: the docs\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def rows(kitchen, **status):
    """Write the queue's rows, each slug at its status, and `removed` as removed."""
    kitchen.state.mkdir(parents=True, exist_ok=True)
    gone = status.pop("removed", ())
    table = [{"slug": slug, "status": said} for slug, said in status.items()]
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    taken = {slug: {"at": "2026-10-11 09:00 EDT", "by": "Josh"} for slug in gone}
    (kitchen.state / "removed.json").write_text(json.dumps(taken))


def result(slug, left=True, pull=""):
    return LEFT.format(slug=slug, pull=pull) if left else CLEAN.format(slug=slug)


def listed(kitchen):
    """Run the command, and return its exit code and the lines it printed."""
    code, said = kitchen.main("stale", "--project", "demo")
    return code, said.splitlines()


def of(lines, kind):
    return [line for line in lines if line.startswith(f"{kind} ")]


def state_of(kitchen):
    """Every file of the home and the state, with its text, to show nothing was written."""
    found = {}
    for root in (kitchen.home, kitchen.state):
        for path in sorted(root.rglob("*")):
            if path.is_file():
                found[str(path)] = path.read_bytes()
    return found


def test_a_brief_is_stale_once_its_row_or_pull_request_ended_with_its_result_not_clean(kitchen):
    rows(
        kitchen,
        alpha="merged",
        beta="done",
        gamma="merged",
        delta="running",
        eps="pr",
        removed=["zeta"],
    )
    kitchen.brief("alpha", result("alpha"))
    kitchen.brief("beta", "")
    kitchen.brief("gamma", result("gamma", left=False))
    pull = "Pull request: https://example.test/pull/7"
    kitchen.brief("delta", result("delta", pull=pull))
    kitchen.brief("eps", result("eps", pull="Pull request: https://example.test/pull/8"))
    kitchen.brief("zeta", "")
    kitchen.brief("eta", result("eta"))
    kitchen.set("open.json", [kitchen.opened("eps", 8)])
    code, lines = listed(kitchen)
    assert code == 0
    assert of(lines, "brief") == [
        "brief alpha: its row is merged, and its last Result says Status: not done, Left: the docs",
        "brief beta: its row is done, and it has no Result",
        "brief delta: its pull request #7 is merged or closed, and its last Result says Status: "
        "not done, Left: the docs",
        "brief zeta: its row is removed, and it has no Result",
    ]


def test_a_brief_with_a_follow_up_that_closes_it_is_not_stale(kitchen):
    rows(kitchen, removed=["alpha"])
    kitchen.brief("alpha", result("alpha") + result("alpha", left=False))
    assert of(listed(kitchen)[1], "brief") == []


def test_a_worktree_is_stale_with_no_open_row_and_no_open_pull_request(kitchen):
    rows(kitchen, alpha="queued", beta="merged", gamma="left")
    for branch in ("alpha", "beta", "gamma", "delta", "eps"):
        kitchen.git("worktree", "add", "-q", "-b", branch, str(kitchen.root / "trees" / branch))
    kitchen.git("worktree", "add", "-q", "--detach", str(kitchen.root / "trees" / "build"))
    kitchen.set("open.json", [kitchen.opened("delta", 4)])
    trees = kitchen.root / "trees"
    assert of(listed(kitchen)[1], "worktree") == [
        f"worktree {trees / 'beta'}: branch beta, of no open row and no open pull request",
        f"worktree {trees / 'eps'}: branch eps, of no open row and no open pull request",
    ]


def test_a_hold_is_stale_once_its_pull_request_is_not_open(kitchen):
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40, "6": "b" * 40}))
    kitchen.set("open.json", [kitchen.opened("alpha", 6)])
    assert of(listed(kitchen)[1], "hold") == ["hold #5: its pull request is not open"]


def asked(kitchen, number, answered):
    answer = questions.Answer("tea", "Josh", "2026-10-12 10:00 EDT", "here", True)
    return questions.Question(
        number, "alpha", "mcp:a", "tea?", "tea", "", "", "", answer if answered else None
    )


def test_a_told_line_is_stale_once_its_decision_or_stop_ended(kitchen):
    rows(kitchen, alpha="merged", beta="queued", removed=["gamma"])
    questions._write(kitchen.state, 3, [asked(kitchen, 1, True), asked(kitchen, 2, False)])
    open_line = "home-stall /: the root home has had 2 things out and been quiet 61 min"
    record = {"threads": {}, "tests": {}, "open": {open_line: NOW.isoformat()}}
    (kitchen.state / wakes.FILE).write_text(json.dumps(record))
    scope = kitchen.home / "jview"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:a-scope\n")
    (kitchen.home / "told").write_text(
        "decision question 1: tea or coffee? default tea\n"
        "decision question 2: milk? default no\n"
        "stop local alpha: the stack waits on alpha\n"
        "stop local beta: the stack waits on beta\n"
        "stop jbus: home-stall /: the root home has had 3 things out and been quiet 75 min\n"
        "decision jbus: alert: health capped one until 2026-10-12 12:30 EDT\n"
    )
    (scope / "told").write_text("stop local gamma: a launch with no tool\n")
    assert of(listed(kitchen)[1], "told") == [
        "told demo/told:1: question 1 has its answer: decision question 1: tea or coffee? "
        "default tea",
        "told demo/told:3: its row alpha is merged: stop local alpha: the stack waits on alpha",
        "told demo/told:6: no item of the one list says it now: decision jbus: alert: health "
        "capped one until 2026-10-12 12:30 EDT",
        "told demo/jview/told:1: its row gamma is removed: stop local gamma: a launch with no tool",
    ]


def test_a_jbus_told_line_is_not_judged_before_a_pass_kept_the_open_items(kitchen):
    (kitchen.home / "told").write_text("decision jbus: alert: one\n")
    lines = listed(kitchen)[1]
    assert of(lines, "told") == []
    assert "not judged: told: a jbus line, before a pass kept the open items in wakes.json" in lines


def test_a_home_id_is_stale_once_t3_code_no_longer_has_its_thread(kitchen):
    home(kitchen)
    scope = kitchen.home / "jview"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:thread-gone\n")
    assert of(listed(kitchen)[1], "home-id") == [
        "home-id demo/jview/home-id: T3 Code no longer has thread mcp:thread-gone"
    ]


def test_it_counts_each_kind_and_deletes_and_writes_nothing(kitchen):
    rows(kitchen, alpha="merged", removed=["beta"])
    kitchen.brief("alpha", result("alpha"))
    kitchen.git("worktree", "add", "-q", "-b", "alpha", str(kitchen.root / "trees" / "alpha"))
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40}))
    (kitchen.home / "told").write_text("stop local beta: waits\n")
    (kitchen.home / "home-id").write_text("mcp:thread-gone\n")
    before = state_of(kitchen)
    code, lines = listed(kitchen)
    assert code == 0 and state_of(kitchen) == before
    assert (kitchen.root / "trees" / "alpha").is_dir()
    assert lines[-1] == (
        "stale: 5 in demo (brief 1, worktree 1, hold 1, told 1, home-id 1), nothing deleted"
    )


def test_with_github_silent_it_judges_nothing_that_needs_the_open_pull_requests(kitchen):
    rows(kitchen, alpha="running")
    kitchen.brief("alpha", result("alpha", pull="Pull request: https://example.test/pull/7"))
    kitchen.git("worktree", "add", "-q", "-b", "beta", str(kitchen.root / "trees" / "beta"))
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40}))
    kitchen.set("gh-list-down", "connection refused")
    lines = listed(kitchen)[1]
    assert [line for line in lines if not line.startswith("not judged:")] == [
        "stale: 0 in demo (brief 0, worktree 0, hold 0, told 0, home-id 0), nothing deleted"
    ]
    judged = [line.split(":")[1].strip() for line in lines if line.startswith("not judged:")]
    assert judged == ["GitHub did not list the open pull requests", "brief", "worktree", "hold"]


def stale_wakes(kitchen):
    return [line for line in kitchen.wakes.said if line.startswith("jbus stale:")]


def test_the_hourly_audit_sends_its_count_to_the_root_home_once_each_time_it_changes(kitchen):
    root = home(kitchen)["threadId"]
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40}))
    kitchen.poll(NOW)
    hint = "`jbus stale --project demo` lists each, and deletes nothing"
    assert stale_wakes(kitchen) == [f"jbus stale: 1 stale in demo (hold 1): {hint}"]
    assert stale.read(kitchen.state) == {
        "hour": int(NOW.timestamp() // stale.HOUR),
        "count": 1,
        "kinds": {"brief": 0, "worktree": 0, "hold": 1, "told": 0, "home-id": 0},
        "gone": False,
    }
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40, "6": "b" * 40}))
    kitchen.poll(NOW + timedelta(minutes=30))
    assert len(stale_wakes(kitchen)) == 1
    kitchen.poll(NOW + timedelta(hours=1))
    assert stale_wakes(kitchen)[1:] == [f"jbus stale: 2 stale in demo (hold 2): {hint}"]
    kitchen.poll(NOW + timedelta(hours=2))
    assert len(stale_wakes(kitchen)) == 2
    sends = [one for tool, one in kitchen.t3.calls if tool == "t3_thread_send"]
    assert {one["threadId"] for one in sends if "jbus stale:" in one["message"]} == {root}
    (kitchen.home / "holds.json").write_text("{}")
    kitchen.poll(NOW + timedelta(hours=3))
    assert stale.read(kitchen.state)["count"] == 0 and len(stale_wakes(kitchen)) == 2


def test_a_told_line_of_an_item_a_pass_kept_ends_a_day_after_no_pass_has_it(kitchen):
    """The home copies the line of an item a real pass told it into `told`: it is open while a pass
    had that item within a day, through a pass that lists less, and ended after."""
    home(kitchen)
    holds = kitchen.home / "holds.json"
    holds.write_text(json.dumps({"5": "a" * 40}))
    kitchen.poll(NOW)
    (said,) = stale_wakes(kitchen)
    (kitchen.home / "told").write_text(f"decision jbus: {said}\n")
    assert of(listed(kitchen)[1], "told") == []
    holds.write_text("{}")
    kitchen.poll(NOW + timedelta(hours=1))
    assert stale.read(kitchen.state)["count"] == 0
    assert of(listed(kitchen)[1], "told") == []
    kitchen.poll(NOW + wakes.KEEP + timedelta(hours=2))
    assert of(listed(kitchen)[1], "told") == [
        "told demo/told:1: no item of the one list says it now: "
        + stale._cut(f"decision jbus: {said}")
    ]


def test_a_root_home_whose_home_id_is_gone_is_not_sent_the_count(kitchen):
    (kitchen.home / "home-id").write_text("mcp:thread-gone\n")
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40}))
    kitchen.poll(NOW)
    assert stale.read(kitchen.state)["count"] == 2 and stale.read(kitchen.state)["gone"]
    assert stale_wakes(kitchen) == []
    home(kitchen)
    kitchen.poll(NOW + timedelta(hours=1))
    assert stale_wakes(kitchen) == [
        "jbus stale: 1 stale in demo (hold 1): `jbus stale --project demo` lists each, and "
        "deletes nothing"
    ]


def test_a_brief_whose_leftover_jbus_holds_is_not_stale(kitchen):
    rows(kitchen, alpha="merged")
    kitchen.brief("alpha", result("alpha"))
    (kitchen.state / leftover.NAME).write_text(json.dumps({"alpha": {"left": "the docs"}}))
    assert of(listed(kitchen)[1], "brief") == []


def test_a_brief_whose_merged_row_still_waits_on_something_is_not_stale(kitchen):
    rows(kitchen, alpha="merged")
    table = json.loads((kitchen.state / "queue.json").read_text())
    table[0]["why"] = "left: the docs"
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    kitchen.brief("alpha", result("alpha"))
    assert of(listed(kitchen)[1], "brief") == []
