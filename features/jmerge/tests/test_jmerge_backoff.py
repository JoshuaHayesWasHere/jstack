"""After GitHub refuses a call for its rate limit, `jmerge` asks it nothing until GitHub said it
may (`backoff`), and a run inside the wait says so once and asks nothing. And a pull request's
"repeated" answer is kept for its head and base tip, so no run log is read twice for one pair
(`rejudge.Repeated`).

2026-11-03, the scout gh-api-budget: 65 refused branch updates in ten minutes, each one asked
again on every pass, and every red pull request's run lists and logs read again on every run.
The tests run the command against a real origin and a fake `gh`, as `test_jmerge_rejudge` does."""

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

import test_jmerge_rejudge as rejudging
from jmerge import backoff, rejudge
from jsettings import budget
from test_jmerge_fresh import url
from test_jmerge_rejudge import BROKE, FIXED, OURS, THEIRS, WHOLE_TREE, Replay, checked

LIMITED = """\
        if [ -e "$STUB/limited" ]; then
            cat "$STUB/limited"
            echo "gh: API rate limit exceeded for user ID 1. (HTTP 403)" >&2
            exit 1
        fi
"""
RATE_LIMIT = """\
    "api rate_limit") cat "$STUB/rate_limit.json" ;;
"""


def limited(tmp_path, said=""):
    """A replay of one pull request red over a red main, then main fixed, whose fake GitHub
    refuses the update of its branch for the rate limit, with `said` as the headers and body
    `gh api --include` prints."""
    replay = Replay(tmp_path)
    gh = replay.kitchen.home.stub / "gh"
    down = '        if [ -e "$STUB/down" ]'
    text = gh.read_text().replace(down, LIMITED + down)
    gh.write_text(text.replace("    *) exit 64 ;;\n", RATE_LIMIT + "    *) exit 64 ;;\n"))
    (replay.kitchen.home.stub / "limited").write_text(said)
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at(dict.fromkeys(WHOLE_TREE), FIXED, "green")
    return replay, fix


def run(replay):
    """One run of `jmerge`, whatever its exit: its lines and its exit code."""
    home = replay.kitchen.home
    said = home.sh(f'PYTHONPATH="{replay.kitchen.source}" "{sys.executable}" -m jmerge')
    assert home.stderr == ""
    return said, home.code


def calls(replay):
    path = replay.kitchen.home.stub / "calls"
    return path.read_text().splitlines() if path.exists() else []


def kept_until(replay):
    path = replay.kitchen.home.state / backoff.NAME
    return datetime.fromisoformat(json.loads(path.read_text())["until"])


def waits(until):
    return backoff.WAITS.format(until=budget.at(until))


def test_a_refusal_waits_as_long_as_retry_after_and_asks_github_nothing_until_then(tmp_path):
    headers = 'HTTP/2.0 403 Forbidden\r\nRetry-After: 600\r\n\r\n{"message":"rate limit"}'
    replay, fix = limited(tmp_path, headers)
    before = datetime.now(UTC)
    said, code = run(replay)
    until = kept_until(replay)
    assert before + timedelta(seconds=600) <= until <= datetime.now(UTC) + timedelta(seconds=600)
    refused = f"GitHub did not merge main at {fix[:12]} into it: rate limit"
    assert (said, code) == ([f"wait 333 {url(333)}: {refused}"], 0)
    assert replay.updated() == ["333"]
    asked = calls(replay)
    for _ in range(3):
        assert run(replay) == ([f"wait: {waits(until)}"], 1)
    assert calls(replay) == asked
    log = (replay.kitchen.home.state / "merge.log").read_text()
    assert log.count(f"wait: {waits(until)}") == 1


def test_a_refusal_with_no_retry_after_waits_for_the_spent_window_s_reset(tmp_path):
    replay, _ = limited(tmp_path)
    reset = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=17)
    window = {"remaining": 0, "limit": 5000, "reset": int(reset.timestamp())}
    full = {"remaining": 4000, "limit": 5000, "reset": int(reset.timestamp())}
    limit = {"resources": {"core": window, "graphql": full}}
    (replay.kitchen.home.stub / "rate_limit.json").write_text(json.dumps(limit))
    run(replay)
    assert kept_until(replay) == reset
    assert run(replay) == ([f"wait: {waits(reset)}"], 1)


def test_a_secondary_limit_that_names_no_time_waits_a_minute_then_asks_again(tmp_path):
    """A secondary limit leaves the windows full and may name no time: GitHub asks for at least
    a minute's wait. Once the wait is over, the run asks again."""
    replay, fix = limited(tmp_path)
    full = {"remaining": 4000, "limit": 5000, "reset": 2000000000}
    limit = {"resources": {"core": full, "graphql": full}}
    (replay.kitchen.home.stub / "rate_limit.json").write_text(json.dumps(limit))
    before = datetime.now(UTC)
    run(replay)
    assert before + backoff.AT_LEAST <= kept_until(replay) <= datetime.now(UTC) + backoff.AT_LEAST
    assert run(replay)[1] == 1
    assert replay.updated() == ["333"]
    path = replay.kitchen.home.state / backoff.NAME
    over = datetime.now(UTC) - timedelta(seconds=1)
    path.write_text(json.dumps({"until": over.isoformat()}))
    (replay.kitchen.home.stub / "limited").unlink()
    assert run(replay) == ([f"wait 333 {url(333)}: {rejudging.ASKED.format(tip=fix[:12])}"], 0)
    assert replay.updated() == ["333", "333"]


@pytest.mark.parametrize(
    ("second", "asks"),
    [((OURS,), False), (("features/x/tests/test_ours.py::test_another",), True)],
    ids=["repeated", "not-repeated"],
)
def test_no_run_log_is_read_twice_for_one_head_and_base_tip(tmp_path, second, asks):
    """Whether the last two runs failed a same test of its own is kept for the head and the
    base's tip, "not repeated" too: a later run reads neither the runs nor a log again, also
    while GitHub's update of the branch fails and keeps no record of its own. Once the base
    moves, it is judged again from GitHub's logs."""
    replay = Replay(tmp_path)
    (replay.kitchen.home.stub / "down").write_text("502")
    gh = replay.kitchen.home.stub / "gh"
    text = gh.read_text().replace("    *) exit 64 ;;\n", rejudging.RUNS + "    *) exit 64 ;;\n")
    gh.write_text(text)
    replay.crew("one", 333, {"one.txt": "ours\n"})
    mains = [(70, "2026-10-23T11:30:00Z", (THEIRS,)), (71, "2026-10-23T12:30:00Z", ())]
    checked(replay, "main", mains)
    started = rejudging.STARTED
    checked(replay, "one", [(80, "2026-10-23T12:00:00Z", (OURS,)), (81, started, second)])
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at(dict.fromkeys(WHOLE_TREE), FIXED, "green")

    def reads():
        return [call for call in calls(replay) if call.startswith("run ")]

    replay.run()
    first = reads()
    logs = ["70", "80", "81"] if not asks else ["80", "81"]
    views = sorted(call.split()[2] for call in first if call.startswith("run view"))
    assert views == logs
    assert len(first) == len(set(first))
    for _ in range(3):
        replay.run()
    assert reads() == first
    assert replay.updated() == (["333"] * 4 if asks else [])
    replay.main_at({"b.txt": "theirs\n"}, "2026-10-23T16:00:00Z", "green")
    replay.run()
    assert len(reads()) > len(first)


def going(branch, number, at):
    """A run of the check on `branch` that GitHub lists as still going."""

    def change(stub):
        path = stub / f"runs-{branch}-check.json"
        run = {"databaseId": number, "status": "in_progress", "conclusion": "", "createdAt": at}
        path.write_text(json.dumps([run, *json.loads(path.read_text())]))

    return change


UNSETTLED = {
    "a-run-list-that-failed": lambda stub: (stub / "runs-one-check.json").unlink(),
    "a-log-github-did-not-give": lambda stub: (stub / "log-81.txt").unlink(),
    "a-run-going-on-its-branch": going("one", 82, "2026-10-23T14:00:00Z"),
    "a-run-going-on-main-before-its-last-run": going("main", 72, "2026-10-23T12:45:00Z"),
}


@pytest.mark.parametrize("unsettled", UNSETTLED)
def test_an_answer_github_left_unsettled_is_not_kept_and_the_next_run_reads_again(
    tmp_path, unsettled
):
    """`rejudge.Repeated` leaves its answer unsettled where `gh run list` failed, where GitHub
    gave no log of a run, or where a run is still going on the pull request's branch or on main
    before its last run. No "repeated" is kept for the head and tip then, and the next run lists
    the runs again. Its last two runs failed a same test of its own, so each case's answer would
    be kept were it settled."""
    replay = Replay(tmp_path)
    stub = replay.kitchen.home.stub
    (stub / "down").write_text("502")
    gh = stub / "gh"
    text = gh.read_text().replace("    *) exit 64 ;;\n", rejudging.RUNS + "    *) exit 64 ;;\n")
    gh.write_text(text)
    replay.crew("one", 333, {"one.txt": "ours\n"})
    mains = [(70, "2026-10-23T11:30:00Z", (THEIRS,)), (71, "2026-10-23T12:30:00Z", ())]
    checked(replay, "main", mains)
    checked(
        replay, "one", [(80, "2026-10-23T12:00:00Z", (OURS,)), (81, rejudging.STARTED, (OURS,))]
    )
    UNSETTLED[unsettled](stub)
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at(dict.fromkeys(WHOLE_TREE), FIXED, "green")

    def lists():
        return [call for call in calls(replay) if call.startswith("run list")]

    replay.run()
    first = lists()
    assert first
    path = replay.kitchen.home.state / rejudge.NAME
    records = json.loads(path.read_text()) if path.exists() else {}
    assert "repeated" not in records.get("333", {})
    replay.run()
    assert lists() == first + first
