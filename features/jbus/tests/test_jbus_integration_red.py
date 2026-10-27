"""An integration branch whose tip's latest check failed holds every pull request into it
(`jmerge.rows.base_red`). jbus gives that red one fix row under the branch's home, as it gives a
red main a main-red row:

- the row is filed once for the red, queued unapproved ahead of every row, and the home that the
  held pull requests' briefs name is sent it once;
- a branch with a fix row still open files nothing more, whatever its tip;
- once the branch's tip is green at a later commit, a row that never launched is withdrawn, and
  `jmerge` no longer holds the pull requests on the branch.

The replay runs the real pass against the kitchen's fakes, on small made-up rows.
"""

from datetime import timedelta

import jbus.queue
from jmerge import ready
from jmerge import rows as jmerge_rows
from test_jbus_kitchen import NOW, sends
from test_jbus_red_main import withdrawn

BRANCH = "release/demo"
SCOPE = "releases"
HOME = "mcp:release-home"
RED, LATER_RED, GREEN = "1" * 40, "2" * 40, "3" * 40


def tip(kitchen, sha, conclusion):
    run = {"status": "completed", "conclusion": conclusion, "name": "check", "head_sha": sha}
    run["started_at"] = "2026-10-12T14:00:00Z"
    kitchen.set("check-runs.json", {BRANCH: [run]})
    return [run]


def branch_red(kitchen):
    return [
        row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith("integration-red-")
    ]


def told(kitchen):
    return [given for given in sends(kitchen) if given["threadId"] == HOME]


def held_on_the_branch(kitchen):
    """Two briefs of the branch's home, each with an open pull request into the branch, which
    `jmerge` holds on the branch's red. A first pass records what is already so."""
    (kitchen.home / SCOPE).mkdir()
    (kitchen.home / SCOPE / "home-id").write_text(HOME + "\n")
    (kitchen.home / "integration").write_text(BRANCH + "\n")
    pulls = []
    for slug, number in (("one", 4), ("two", 5)):
        kitchen.brief(slug, f"Home: {SCOPE}\n")
        pulls.append({**kitchen.opened(slug, number), "baseRefName": BRANCH})
    kitchen.set("open.json", pulls)
    tip(kitchen, "0" * 40, "success")
    kitchen.quiet()


def test_a_red_branch_files_one_fix_row_under_its_home_and_a_green_tip_withdraws_it(kitchen):
    held_on_the_branch(kitchen)
    runs = tip(kitchen, RED, "failure")
    hold = ready.BASE_RED.format(base=BRANCH, sha=RED[:12])
    assert [jmerge_rows.base_red(BRANCH, runs, slug) for slug in ("one", "two")] == [hold] * 2
    name = f"integration-red-release-demo-{RED[:12]}"
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=3))
    (row,) = branch_red(kitchen)
    assert row["slug"] == name and row["approved"] == ""
    assert jbus.queue.order(row) <= min(map(jbus.queue.order, jbus.queue.load(kitchen.state)))
    text = (kitchen.home / "tasks" / f"{name}.md").read_text()
    assert f"Home: {SCOPE}\n" in text and f"Pull request: open one against {BRANCH}" in text
    (sent,) = told(kitchen)
    assert name in sent["message"] and "#4" in sent["message"] and "#5" in sent["message"]
    assert jmerge_rows.base_red(BRANCH, runs, name) == ""

    tip(kitchen, LATER_RED, "failure")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [one["slug"] for one in branch_red(kitchen)] == [name]
    assert len(told(kitchen)) == 1

    judged = len(kitchen.log("jmerge"))
    runs = tip(kitchen, GREEN, "success")
    kitchen.poll(NOW + timedelta(minutes=9))
    assert branch_red(kitchen) == []
    move = withdrawn(kitchen.state, name)
    assert move["by"] == "jbus" and f"{BRANCH} is green at {GREEN[:12]}" in move["why"]
    assert len(kitchen.log("jmerge")) > judged
    assert [jmerge_rows.base_red(BRANCH, runs, slug) for slug in ("one", "two")] == ["", ""]
    assert len(told(kitchen)) == 1


def test_a_branch_with_no_pull_request_on_it_is_not_asked_about(kitchen):
    held_on_the_branch(kitchen)
    kitchen.set("open.json", [])
    (kitchen.stub / "gh.log").unlink()
    tip(kitchen, RED, "failure")
    kitchen.poll(NOW)
    assert branch_red(kitchen) == [] and told(kitchen) == []
    assert not [line for line in kitchen.log("gh") if f"commits/{BRANCH}/" in line]
