"""A fault an agent can fix is told to that agent once, by the pass, and never put to the user.

`jbus.owners.tell` reads the project as the view reads it and tells the root home of each fault
of the project or the machine that it was not told of, and the home of a crew that hung. Any
other fault of a row is told by the step that already works that row: a red check of a crew's
pull request by `jbus.rebase`, once a head, and the view reads that message as what the crew
was told.

Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

import json
from datetime import timedelta

import jbus
from jbus import outbox, owners, passes
from jbus.view import state
from test_jbus_github import FAILED, failed, launched, pull, sends
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_leftover import home
from test_jbus_live import hanging
from test_jbus_queue import add
from test_stall import guarded, later

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
    return owners.read(run).once(state.wrongs)


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


def test_a_red_run_no_row_owns_is_told_to_the_root_home_once(launched):
    """A red check on a branch with no row, as a bot's, is a fault of the project."""
    root = home(launched)["threadId"]
    runs(launched, "dependabot/pip/oat")
    for minutes in (0, 3, 6):
        launched.poll(NOW + minutes * MIN)
    assert told(launched) == [(owners.KIND, root)]
    (sent,) = [given for given in sends(launched) if given["threadId"] == root]
    assert sent["message"].startswith("jbus: the ci dependabot/pip/oat is wrong in demo")
    (ci,) = [one for one in wrongs(launched, NOW + 6 * MIN) if one["kind"] == "ci"]
    assert (ci["owner"], ci["fixing"]["what"]) == ("root home", owners.KIND)


def test_with_no_root_home_a_red_run_no_row_owns_is_the_users_and_told_to_nobody(launched):
    runs(launched, "dependabot/pip/oat")
    launched.poll(NOW)
    assert told(launched) == []
    (ci,) = [one for one in wrongs(launched, NOW) if one["kind"] == "ci"]
    assert (ci["owner"], ci["fixing"]) == ("user", None)


def test_a_hung_crew_no_step_works_is_told_to_the_root_home_once(tmp_path, monkeypatch):
    """No other step tells a home of a crew that hangs at work with no queued row: `stall.hung`
    only logs it, and `jbus.watch.unwritten` works only a row. The review of #563 found the
    hang went to nobody."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.quiet()
    root = home(kitchen)["threadId"]
    hanging(kitchen)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + minutes * MIN)
    (sent,) = [given for given in sends(kitchen) if given["threadId"] == root]
    assert sent["message"].startswith("jbus: the thread crew: alpha is wrong in demo")
    (one,) = [one for one in wrongs(kitchen, NOW + 6 * MIN) if one["kind"] == "thread"]
    assert (one["owner"], one["fixing"]["what"]) == ("root home", owners.KIND)
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


def test_a_guarded_stall_is_told_to_its_home_once(tmp_path, monkeypatch):
    """`stall.guarded` only logs a guarded wait that lasts 10 passes at one head, and wakes
    nobody, so the pass tells the row's home. The second review of #563 found it went to
    nobody, drawn as fixing by the home."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    root = home(kitchen)["threadId"]
    add(kitchen, "alpha")
    guarded(kitchen)
    for minute in range(12):
        kitchen.poll(later(minute))
    (sent,) = [given for given in sends(kitchen) if given["threadId"] == root]
    assert sent["message"].startswith("jbus: the stall alpha is wrong in demo")
    (one,) = [one for one in wrongs(kitchen, later(11)) if one["kind"] == "stall"]
    assert (one["owner"], one["fixing"]["what"]) == ("root home", owners.KIND)
    kitchen.close()
