"""A project's open pull requests are one read a pass (`jbus.pulls.read`), which `watch.look` and
the `jmerge` the pass starts both take. The list is a GraphQL ask, and GraphQL is the allowance
nearest its wall, so it is asked only where REST's open list, a head's check runs or statuses,
or a base's tip changed: those reads answer 304, which costs nothing, while they are unchanged.

The kitchen's `gh` gives the GraphQL list and REST's list from `open.json`, each head's check
runs from `check-runs.json` and its statuses from `statuses.json`."""

import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import merge, passes, pulls, t3, watch
from jmerge.cli import LIST
from jsettings import budget
from test_jbus_kitchen import NOW, Kitchen, rate_limit

HEAD, NEXT = "c" * 40, "d" * 40
RUN = {
    "id": 1,
    "name": "check",
    "status": "in_progress",
    "conclusion": None,
    "started_at": "2026-10-12T14:50:00Z",
    "completed_at": None,
    "details_url": "https://example.test/job/1",
}
ENDED = {
    **RUN,
    "status": "completed",
    "conclusion": "success",
    "completed_at": "2026-10-12T15:01:00Z",
}


def rolled(run):
    """A REST check run as GraphQL's `statusCheckRollup` names it."""
    said = {"status": run["status"].upper(), "conclusion": (run["conclusion"] or "").upper()}
    return {"__typename": "CheckRun", "name": run["name"], **said}


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.set("open.json", [opened(made, 7, HEAD)])
    made.set("check-runs.json", {HEAD: [RUN]})
    yield made
    made.close()


def opened(kitchen, number, head, **more):
    """An open pull request as GraphQL lists it, with every field of `pulls.FIELDS`."""
    return {
        **kitchen.opened(f"row-{number}", number, state=""),
        "headRefOid": head,
        "mergeable": "MERGEABLE",
        "updatedAt": "2026-10-12T14:00:00Z",
        "files": [{"path": "a.txt", "additions": 1, "deletions": 0}],
        "changedFiles": 1,
        "isDraft": False,
        "statusCheckRollup": [rolled(RUN)],
        **more,
    }


def a_pass(minutes=0):
    config = jbus.load()
    return passes.Pass(config, config.projects[0], NOW + timedelta(minutes=minutes), print)


def asked(kitchen):
    """How many times GraphQL was asked for the open list."""
    return sum(line.startswith("pr list --state open") for line in kitchen.log("gh"))


def looked(minutes):
    """The open pull requests `watch.look` gives a pass, by slug."""
    run = a_pass(minutes)
    seen = watch.look(run, t3.Client(run.config.server, run.config.token_path), [])
    assert seen.world is not None
    return seen.world.open


def test_a_second_pass_over_an_unchanged_github_asks_graphql_nothing(kitchen):
    assert set(pulls.FIELDS.split(",")) == set(watch.OPEN.split(",")) | set(LIST.split(","))
    first = pulls.read(a_pass())
    assert asked(kitchen) == 1
    (call,) = [line for line in kitchen.log("gh") if line.startswith("pr list")]
    assert f"--json {pulls.FIELDS}" in call
    second = pulls.read(a_pass(1))
    assert asked(kitchen) == 1
    assert second.pulls == first.pulls == [opened(kitchen, 7, HEAD)]
    assert second.default == "main" and second.at != first.at
    assert json.loads(second.path.read_text())["at"] == second.at


def change_head(kitchen):
    kitchen.set("open.json", [opened(kitchen, 7, NEXT)])
    kitchen.set("check-runs.json", {NEXT: [RUN]})


def end_check(kitchen):
    kitchen.set("check-runs.json", {HEAD: [ENDED]})
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=[rolled(ENDED)])])


def open_one(kitchen):
    kitchen.set("open.json", [opened(kitchen, 7, HEAD), opened(kitchen, 8, NEXT)])
    kitchen.set("check-runs.json", {HEAD: [RUN], NEXT: [RUN]})


def close_one(kitchen):
    kitchen.set("open.json", [])


def move_main(kitchen):
    kitchen.git("commit", "-q", "--allow-empty", "-m", "main moves")
    kitchen.git("push", "-q", "origin", "HEAD:main")
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, mergeable="CONFLICTING")])


def set_status(kitchen):
    kitchen.set("statuses.json", {HEAD: [{"context": "ci/other", "state": "pending"}]})
    rollup = [
        rolled(RUN),
        {"__typename": "StatusContext", "context": "ci/other", "state": "PENDING"},
    ]
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=rollup)])


@pytest.mark.parametrize(
    "change", [change_head, end_check, open_one, close_one, move_main, set_status]
)
def test_each_change_github_can_make_is_read_on_the_next_pass(kitchen, change):
    looked(0)
    before = looked(1)
    assert asked(kitchen) == 1
    change(kitchen)
    after = looked(2)
    assert asked(kitchen) == 2
    (kitchen.state / pulls.FILE).unlink()
    assert after == looked(3) != before
    assert asked(kitchen) == 3


def known(kitchen):
    """What GitHub said of its API budget a moment ago, well above the floor."""
    now = datetime.now(UTC)
    said = {**rate_limit(4000, reset=now + timedelta(hours=1)), "at": now.isoformat()}
    kitchen.state_dir.mkdir(parents=True, exist_ok=True)
    (kitchen.state_dir / budget.KEPT).write_text(json.dumps(said))


def test_the_jmerge_a_pass_starts_is_handed_its_read_where_the_budget_is_known(kitchen):
    run = a_pass()
    merge.merge(run)
    assert kitchen.log("jmerge") == ["--if-free"] and asked(kitchen) == 0
    known(kitchen)
    merge.merge(run)
    handed = kitchen.log("jmerge")[-1].split()
    path = str(kitchen.state / pulls.FILE)
    assert handed == ["--if-free", "--pulls", path, "--pulls-at", run.now.isoformat()]
    assert json.loads((kitchen.state / pulls.FILE).read_text())["at"] == run.now.isoformat()
    assert asked(kitchen) == 1


def no_rest_list(kitchen):
    """A pull request REST's list cannot give: the kitchen's REST view needs its title."""
    kitchen.set("open.json", [{k: v for k, v in opened(kitchen, 7, HEAD).items() if k != "title"}])


def no_check_runs(kitchen):
    kitchen.set("check-runs.json", {HEAD: [{"name": "check"}]})


def no_origin(kitchen):
    kitchen.git("remote", "set-url", "origin", str(kitchen.root / "gone.git"))


def unread_kept(kitchen):
    path = kitchen.state / pulls.FILE
    if path.exists():
        path.write_text(json.dumps({**json.loads(path.read_text()), "asked": "never"}))


@pytest.mark.parametrize("unread", [no_rest_list, no_check_runs, no_origin, unread_kept])
def test_a_list_no_read_vouches_for_is_asked_again_on_each_pass(kitchen, unread):
    for minutes in range(3):
        unread(kitchen)
        assert [pull["number"] for pull in pulls.read(a_pass(minutes)).pulls] == [7]
    assert asked(kitchen) == 3


def test_a_rollup_that_lags_the_check_runs_is_asked_again(kitchen):
    """GitHub's GraphQL rollup can lag its REST check runs: a list kept while it still says
    IN_PROGRESS of a run REST says completed would hold the merge it gates for `FRESH`."""
    kitchen.set("check-runs.json", {HEAD: [ENDED]})
    for minutes in range(3):
        pulls.read(a_pass(minutes))
    assert asked(kitchen) == 3
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=[rolled(ENDED)])])
    for minutes in range(3, 6):
        assert pulls.read(a_pass(minutes)).pulls[0]["statusCheckRollup"] == [rolled(ENDED)]
    assert asked(kitchen) == 4
    kitchen.set("statuses.json", {HEAD: [{"context": "ci/other", "state": "success"}]})
    pending = {"__typename": "StatusContext", "context": "ci/other", "state": "PENDING"}
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=[rolled(ENDED), pending])])
    for minutes in range(6, 8):
        pulls.read(a_pass(minutes))
    assert asked(kitchen) == 6
    required = {**pending, "context": "ci/required", "state": "EXPECTED"}
    agreed = [rolled(ENDED), {**pending, "state": "SUCCESS"}, required]
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=agreed)])
    for minutes in range(8, 10):
        pulls.read(a_pass(minutes))
    assert asked(kitchen) == 7


def test_a_kept_list_is_asked_again_once_it_is_ten_minutes_old(kitchen):
    for minutes in (0, 1, 9, 10, 11):
        pulls.read(a_pass(minutes))
    assert asked(kitchen) == 2


def test_a_silent_github_hands_the_jmerge_of_the_pass_nothing(kitchen):
    known(kitchen)
    kitchen.set("gh-list-down", "gh: Bad Gateway (HTTP 502)\n")
    merge.merge(a_pass())
    assert kitchen.log("jmerge") == ["--if-free"]


def probes(kitchen, ran):
    """Each free read `pulls.probe` made: REST's open list, a head's check runs or statuses, as
    the kitchen's `gh` logged them, and the `git ls-remote --symref` of the remote's tips."""
    rest = ("pulls?state=open", "/check-runs", "/status")
    said = [line for line in kitchen.log("gh") if any(one in line for one in rest)]
    return said + [" ".join(one) for one in ran if one[:3] == ["git", "ls-remote", "--symref"]]


def test_a_pass_probes_once(kitchen, monkeypatch):
    """The read `merge.handed` takes for the `jmerge` it starts is the one `watch.look` uses
    after: a pass pays each probe once. A pass that handed no read has `watch.look` read on its
    own, as a pass whose budget is not known does."""
    open_one(kitchen)
    ran, run_of = [], subprocess.run

    def logged(command, **how):
        ran.append(list(command))
        return run_of(command, **how)

    monkeypatch.setattr(subprocess, "run", logged)
    for minutes, budget_known in ((0, True), (1, False)):
        if budget_known:
            known(kitchen)
        else:
            (kitchen.state_dir / budget.KEPT).unlink()
        run = a_pass(minutes)
        before = len(probes(kitchen, ran))
        merge.merge(run)
        handed = "--pulls" in kitchen.log("jmerge")[-1]
        seen = watch.look(run, t3.Client(run.config.server, run.config.token_path), [])
        assert seen.world is not None and sorted(seen.world.open) == ["row-7", "row-8"]
        assert handed == budget_known
        assert len(probes(kitchen, ran)) - before == 6, probes(kitchen, ran)[before:]
