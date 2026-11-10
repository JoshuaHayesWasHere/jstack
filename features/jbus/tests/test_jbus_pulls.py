"""A project's open pull requests are one read a pass (`jbus.pulls.read`), which `watch.look` and
the `jmerge` the pass starts both take. The list is a GraphQL ask, and GraphQL is the allowance
nearest its wall, so it is asked only where REST's open list, a head's check runs or statuses,
or a base's tip changed: those reads answer 304, which costs nothing, while they are unchanged.

The kitchen's `gh` gives the GraphQL list from `open.json` and each head's check runs from
`check-runs.json`; `github` lays over it REST's view of the same pull requests, and their
statuses from `statuses.json`."""

import hashlib
import json
from datetime import timedelta

import pytest

import jbus
from jbus import passes, pulls, t3, watch
from jmerge.cli import LIST
from test_jbus_kitchen import NOW, Kitchen, fake_gh

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


def github(stub, args, cwd):
    """The kitchen's `gh`, with REST's list of the open pull requests and a head's statuses."""
    path = args[1] if args[:1] == ["api"] else ""
    if path.startswith("repos/{owner}/{repo}/pulls?state=open"):
        opened = json.loads((stub / "open.json").read_text())
        said = [
            {
                "number": one["number"],
                "html_url": one["url"],
                "title": one["title"],
                "head": {"ref": one["headRefName"], "sha": one["headRefOid"]},
                "base": {"ref": one["baseRefName"]},
                "draft": one.get("isDraft", False),
                "updated_at": one.get("updatedAt", ""),
            }
            for one in opened
        ]
    elif path.endswith("/status"):
        kept = stub / "statuses.json"
        every = json.loads(kept.read_text()) if kept.exists() else {}
        said = {"statuses": every.get(path.split("/")[-2], [])}
    else:
        return fake_gh(stub, args, cwd)
    with open(stub / "gh.log", "a") as log:
        log.write(" ".join(args) + "\n")
    said = json.dumps(said)
    etag = f'W/"{hashlib.sha256(said.encode()).hexdigest()}"'
    if "-H" in args and args[args.index("-H") + 1] == f"If-None-Match: {etag}":
        return 1, "HTTP/2.0 304 Not Modified\r\n\r\n", "gh: HTTP 304\n"
    return 0, f"HTTP/2.0 200 OK\r\nEtag: {etag}\r\n\r\n{said}\n", ""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    gh = str(made.stub / "gh")
    made.fakes[gh] = (github, made.fakes[gh][1])
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
    ended = {**RUN, "status": "completed", "conclusion": "success"}
    kitchen.set("check-runs.json", {HEAD: [{**ended, "completed_at": "2026-10-12T15:01:00Z"}]})
    rollup = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
    kitchen.set("open.json", [opened(kitchen, 7, HEAD, statusCheckRollup=rollup)])


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
    rollup = [{"context": "ci/other", "state": "PENDING"}]
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
