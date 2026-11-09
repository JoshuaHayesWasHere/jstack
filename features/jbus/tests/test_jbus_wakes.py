"""A home is woken from one list, the open items it owns that are new to it (`jbus.wakes`).

`jbus.wakes.tell` reads the project as the view reads it and tells the root home of each fault
of the project or the machine that it was not told of, and the home of a crew that hung. Any
other fault of a row is told by the step that already works that row: a red check of a crew's
pull request by `jbus.rebase`, once a head, and the view reads that message as what the crew
was told.

Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

import json
import threading
from datetime import timedelta

import pytest

import jbus
import jsettings
from jbus import outbox, passes, verbs, wakes
from jbus.view import state
from test_jbus_github import FAILED, failed, launched, pull, sends
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_leftover import home
from test_jbus_live import hanging
from test_jbus_queue import add, brief
from test_jbus_scout import request

__all__ = ["launched"]

MIN = timedelta(minutes=1)


def runs(kitchen, *branches):
    """GitHub's list of the repo's runs: one failed run of `check` on each branch, 10 minutes
    ago."""
    kitchen.set(
        "runs.json",
        {
            "workflow_runs": [
                {
                    "id": 500 + at,
                    "head_branch": branch,
                    "status": "completed",
                    "conclusion": "failure",
                    "created_at": iso(NOW - 12 * MIN),
                    "run_started_at": iso(NOW - 11 * MIN),
                    "updated_at": iso(NOW - 10 * MIN),
                    "html_url": f"https://example.test/o/r/actions/runs/{500 + at}",
                    "name": "check",
                }
                for at, branch in enumerate(branches)
            ]
        },
    )


def wrongs(kitchen, at):
    run = passes.Pass(jbus.load(), jbus.load().projects[0], at)
    return wakes.read(run).once(state.wrongs)


def told(kitchen):
    """Each line of the outbox's log that went, as `(template, thread)`."""
    kept = kitchen.state / outbox.FILE
    lines = [json.loads(line) for line in kept.read_text().splitlines()] if kept.exists() else []
    return [(line["template"], line["thread"]) for line in lines if line["went"] == "sent"]


def test_a_red_check_of_a_crews_pull_request_is_told_to_the_crew_once_and_not_the_user(
    launched,
):
    root = home(launched)["threadId"]
    launched.set("open.json", [pull(launched, [failed()])])
    runs(launched, "alpha")
    for minutes in (0, 3, 6):
        launched.poll(NOW + minutes * MIN)
    assert [given["message"] for given in sends(launched)] == [FAILED.format(short="c" * 12)]
    assert told(launched) == [("failed", "mcp:thread-1")]
    (ci,) = [one for one in wrongs(launched, NOW + 6 * MIN) if one["kind"] == "ci"]
    assert (ci["owner"], ci["row"], ci["to"]) == ("crew of alpha", "alpha", "mcp:thread-1")
    assert ci["fixing"]["what"] == "failed"
    assert root not in {given["threadId"] for given in sends(launched)}


def test_a_red_run_no_row_owns_is_told_to_the_catchall_once_and_not_the_root(launched):
    """A red check on a branch with no row, as a bot's, is a fault of the project, which the
    catch-all's home owns (the user, 2026-11-08: "Uncategorized")."""
    root = home(launched)["threadId"]
    catchall = home(launched, "uncategorized")["threadId"]
    runs(launched, "dependabot/pip/oat")
    for minutes in (0, 3, 6):
        launched.poll(NOW + minutes * MIN)
    assert told(launched) == [(wakes.KIND, catchall)]
    (sent,) = [given for given in sends(launched) if given["threadId"] == catchall]
    assert sent["message"].startswith("jbus: 1 new for this home in demo")
    assert [given for given in sends(launched) if given["threadId"] == root] == []
    (ci,) = [one for one in wrongs(launched, NOW + 6 * MIN) if one["kind"] == "ci"]
    assert (ci["owner"], ci["fixing"]["what"]) == ("home uncategorized", wakes.KIND)


def test_with_no_root_home_a_red_run_no_row_owns_is_the_users_and_told_to_nobody(launched):
    runs(launched, "dependabot/pip/oat")
    launched.poll(NOW)
    assert told(launched) == []
    (ci,) = [one for one in wrongs(launched, NOW) if one["kind"] == "ci"]
    assert (ci["owner"], ci["fixing"]) == ("user", None)


def test_a_hung_crew_no_step_works_is_told_to_the_root_home_once(tmp_path, monkeypatch):
    """No other step tells a home of a crew that hangs at work with no queued row: `stall.hung`
    only logs it, and `jbus.watch.unwritten` works only a row. The review of #563 found the
    hang went to nobody. The crew is the catch-all's, and the root's thread hears of it while
    it stands in for the catch-all."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.quiet()
    root = home(kitchen)["threadId"]
    hanging(kitchen)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + minutes * MIN)
    (sent,) = [given for given in sends(kitchen) if given["threadId"] == root]
    assert sent["message"].startswith("jbus: 1 new for this home in demo")
    (one,) = [one for one in wrongs(kitchen, NOW + 6 * MIN) if one["kind"] == "thread"]
    assert (one["owner"], one["fixing"]["what"]) == ("home uncategorized", wakes.KIND)
    kitchen.close()


def test_a_hung_home_is_left_to_the_nudge_of_its_parent(tmp_path, monkeypatch):
    """A home's thread that hung is no crew: this step tells nobody of it."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.quiet()
    root = home(kitchen)["threadId"]
    hanging(kitchen, title="home: demo sc")
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + minutes * MIN)
    assert [given for given in sends(kitchen) if given["threadId"] == root] == []
    kitchen.close()


def test_one_red_on_two_branches_wakes_the_root_once_and_a_new_red_wakes_it_again(launched):
    """The review of #585: the pass keys a red by the failing tests its run's log names, so two
    branches red on the same test are one item, and a red on another test is news."""
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat", "dependabot/pip/rye")
    launched.set("run-jobs.json", {str(500 + at): [job(at)] for at in range(3)})
    launched.set("logs.json", {str(900 + at): log_of(at) for at in range(3)} | {"901": log_of(0)})
    for minutes in (0, 3):
        launched.poll(NOW + minutes * MIN)
    (first,) = [given["message"] for given in sends(launched) if given["threadId"] == root]
    assert first.count("\n- ci ") == 1
    runs(launched, "dependabot/pip/oat", "dependabot/pip/rye", "dependabot/pip/wheat")
    for minutes in (6, 9):
        launched.poll(NOW + minutes * MIN)
    _, second = [given["message"] for given in sends(launched) if given["threadId"] == root]
    assert "- ci dependabot/pip/wheat: check failed" in second and second.count("\n- ci ") == 1


def test_a_red_whose_jobs_cannot_be_read_waits_a_pass_and_wakes_the_root_once(launched):
    """The review of #585: a red keyed by its fallback while its jobs cannot be read, and by its
    tests once they can, woke the root twice. It waits for its tests, and unread is not kept as
    no tests, so the one wake carries the key its tests give it."""
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat")
    launched.set("run-jobs.json", {"500": None})
    launched.set("logs.json", {"900": log_of(0)})
    launched.poll(NOW)
    assert reds_told(launched, root) == []
    launched.set("run-jobs.json", {"500": [job(0)]})
    for minutes in (3, 6, 9):
        launched.poll(NOW + minutes * MIN)
    assert reds_told(launched, root) == ["ci dependabot/pip/oat: check failed"]
    record = jbus.read_json(launched.state / wakes.FILE, {})
    assert record["tests"] == {"500": ["tests/test_grain.py::test_0"]}
    assert wakes.red_key(["tests/test_grain.py::test_0"]) in wakes.told_to(record, root)


def test_a_red_whose_tests_stay_unread_wakes_once_with_the_key_it_first_got(launched):
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat")
    launched.set("run-jobs.json", {"500": None})
    for minutes in (0, 3, 6, 9):
        launched.poll(NOW + minutes * MIN)
    launched.set("run-jobs.json", {"500": [job(0)]})
    launched.set("logs.json", {"900": log_of(0)})
    for minutes in (12, 15):
        launched.poll(NOW + minutes * MIN)
    assert reds_told(launched, root) == ["ci dependabot/pip/oat: check failed"]
    assert jbus.read_json(launched.state / wakes.FILE, {})["tests"] == {"500": []}


def test_a_red_runs_failed_job_logs_are_read_at_one_moment_for_the_same_tests(
    launched, monkeypatch
):
    """Each log read waits until every failed job's read has begun, so a pass that read them one
    by one would break the barrier. The run's key is the union of the tests its logs name."""
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat")
    launched.set("run-jobs.json", {"500": [job(at) for at in range(3)]})
    launched.set("logs.json", {str(900 + at): log_of(at) for at in range(3)})
    barrier, met, real = threading.Barrier(3), [], wakes._log_failed

    def reading(run, job_id):
        try:
            barrier.wait(10)
            met.append(True)
        except threading.BrokenBarrierError:
            met.append(False)
        return real(run, job_id)

    monkeypatch.setattr(wakes, "_log_failed", reading)
    for minutes in (0, 3):
        launched.poll(NOW + minutes * MIN)
    assert met == [True] * 3
    assert reds_told(launched, root) == ["ci dependabot/pip/oat: check failed"]
    tests = [f"tests/test_grain.py::test_{at}" for at in range(3)]
    assert jbus.read_json(launched.state / wakes.FILE, {})["tests"] == {"500": tests}


def test_one_unread_log_of_several_leaves_the_run_unread_for_a_pass(launched):
    """The other logs are read, and the run still waits for its tests: one read is not a red."""
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat")
    launched.set("run-jobs.json", {"500": [job(at) for at in range(3)]})
    launched.set("logs.json", {"900": log_of(0), "902": log_of(2)})
    launched.poll(NOW)
    assert reds_told(launched, root) == []
    assert jbus.read_json(launched.state / wakes.FILE, {})["tests"] == {"500": wakes.UNREAD}
    launched.set("logs.json", {str(900 + at): log_of(at) for at in range(3)})
    for minutes in (3, 6):
        launched.poll(NOW + minutes * MIN)
    assert reds_told(launched, root) == ["ci dependabot/pip/oat: check failed"]
    tests = [f"tests/test_grain.py::test_{at}" for at in range(3)]
    assert jbus.read_json(launched.state / wakes.FILE, {})["tests"] == {"500": tests}


def reds_told(kitchen, thread):
    """Each red the thread was told of, as its line on the list."""
    said = [given["message"] for given in sends(kitchen) if given["threadId"] == thread]
    return [line[2:] for one in said for line in one.splitlines() if line.startswith("- ci ")]


def job(at):
    return {"id": 900 + at, "status": "completed", "conclusion": "failure"}


def log_of(at):
    return f"FAILED tests/test_grain.py::test_{at}\n"


def test_an_item_whose_words_move_only_to_a_new_commit_or_time_is_not_news():
    """The key of a wrong leaves out its commit and time (`state.key_of`), and so do its words: a
    main that stays red at a new commit says nothing new, and a red that changed does."""
    red = wakes.Item(key="wrong|red", to="mcp:root", line="red main: check failed, red at abc1234")
    seen = {red.key: {"said": wakes.words(red)}}
    moved = wakes.Item(key=red.key, to=red.to, line="red main: check failed, red at def5678")
    worse = wakes.Item(key=red.key, to=red.to, line="red main: two checks failed, red at def5678")
    assert wakes.pick([moved], seen, red.to) == []
    assert wakes.pick([worse], seen, red.to) == [worse]


@pytest.mark.parametrize("kind", ["tasks", "scouts"])
def test_a_row_to_approve_wakes_no_thread_and_waits_on_needs_and_the_tree(
    tmp_path, monkeypatch, kind
):
    """A home approves a row on the user's word as it queues it (`queue add --message`), so a go
    still owed is the user's alone: it wakes neither the home whose brief or scout's request it
    is, nor the uncategorized home, nor the root, and `jbus needs` and
    the view's tree of homes still show it, each under the home whose row it is."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    homes = [home(kitchen, *name)["threadId"] for name in ((), ("sidebar",), ("uncategorized",))]
    for slug, named, where in (
        ("sb-rows-build", "sidebar", kind),
        ("alpha", "uncategorized", "tasks"),
    ):
        given = (request(slug) if where == "scouts" else brief(slug)).replace(
            "Home: uncategorized\n", ""
        )
        add(kitchen, slug, approve=False, text=f"{given}Home: {named}\n")
        kitchen.brief(slug, f"Home: {named}\n", kind=where)
    for minutes in (0, 5, 10):
        kitchen.poll(NOW + minutes * MIN)
    heard = [
        line
        for given in sends(kitchen)
        if given["threadId"] in homes
        for line in given["message"].splitlines()
        if line.startswith("- approve ")
    ]
    assert heard == []
    monkeypatch.setattr(verbs, "clock", lambda: NOW + 10 * MIN)
    code, said = kitchen.main("needs")
    assert code == 0, said
    assert sorted(
        line.split(":")[0] for line in said.splitlines() if line.startswith("demo approve ")
    ) == [
        "demo approve alpha",
        "demo approve sb-rows-build",
    ]
    sources = state.Sources(kitchen.state_dir, kitchen.root / "home", user=jsettings.load())
    tree = state.summary(state.Read(sources, "demo", NOW + 10 * MIN, lambda _: {}))["homes"]
    assert {one["name"]: one["waits"] for one in tree} == {"": 0, "uncategorized": 1, "sidebar": 1}
