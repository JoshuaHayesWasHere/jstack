"""A train whose tip's latest check failed holds every pull request into it
(`jmerge.rows.base_red`). jbus gives that red one fix row under the train's home, as it gives a
red main a main-red row:

- the row is filed once for the red, queued unapproved ahead of every row, and the home that the
  held pull requests' briefs name is sent it once;
- a train with a fix row still open files nothing more, whatever its tip;
- once the train's tip is green at a later commit, a row that never launched is withdrawn, and
  `jmerge` no longer holds the pull requests on the train.

The replay runs the real pass against the kitchen's fakes, on small made-up rows.
"""

from datetime import timedelta

import jbus.queue
from jmerge import ready
from jmerge import rows as jmerge_rows
from test_jbus_kitchen import NOW, sends
from test_jbus_red_main import withdrawn

TRAIN = "train/demo"
SCOPE = "trains"
HOME = "mcp:train-home"
RED, LATER_RED, GREEN = "1" * 40, "2" * 40, "3" * 40


def tip(kitchen, sha, conclusion):
    run = {"status": "completed", "conclusion": conclusion, "name": "check", "head_sha": sha}
    run["started_at"] = "2026-10-12T14:00:00Z"
    kitchen.set("check-runs.json", {TRAIN: [run]})
    return [run]


def train_red(kitchen):
    return [row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith("train-red-")]


def told(kitchen):
    return [given for given in sends(kitchen) if given["threadId"] == HOME]


def held_on_the_train(kitchen):
    """Two briefs of the train's home, each with an open pull request into the train, which
    `jmerge` holds on the train's red. A first pass records what is already so."""
    (kitchen.home / SCOPE).mkdir()
    (kitchen.home / SCOPE / "home-id").write_text(HOME + "\n")
    (kitchen.home / "integration").write_text(TRAIN + "\n")
    pulls = []
    for slug, number in (("one", 4), ("two", 5)):
        kitchen.brief(slug, f"Home: {SCOPE}\n")
        pulls.append({**kitchen.opened(slug, number), "baseRefName": TRAIN})
    kitchen.set("open.json", pulls)
    tip(kitchen, "0" * 40, "success")
    kitchen.quiet()


def test_a_red_train_files_one_fix_row_under_its_home_and_a_green_tip_withdraws_it(kitchen):
    held_on_the_train(kitchen)
    runs = tip(kitchen, RED, "failure")
    hold = ready.BASE_RED.format(base=TRAIN, sha=RED[:12])
    assert [jmerge_rows.base_red(TRAIN, runs, slug) for slug in ("one", "two")] == [hold] * 2
    name = f"train-red-demo-{RED[:12]}"
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=3))
    (row,) = train_red(kitchen)
    assert row["slug"] == name and row["approved"] == ""
    assert jbus.queue.order(row) <= min(map(jbus.queue.order, jbus.queue.load(kitchen.state)))
    text = (kitchen.home / "tasks" / f"{name}.md").read_text()
    assert f"Home: {SCOPE}\n" in text and f"Pull request: open one against {TRAIN}" in text
    (sent,) = told(kitchen)
    assert name in sent["message"] and "#4" in sent["message"] and "#5" in sent["message"]
    assert jmerge_rows.base_red(TRAIN, runs, name) == ""

    tip(kitchen, LATER_RED, "failure")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [one["slug"] for one in train_red(kitchen)] == [name]
    assert len(told(kitchen)) == 1

    judged = len(kitchen.log("jmerge"))
    runs = tip(kitchen, GREEN, "success")
    kitchen.poll(NOW + timedelta(minutes=9))
    assert train_red(kitchen) == []
    move = withdrawn(kitchen.state, name)
    assert move["by"] == "jbus" and f"{TRAIN} is green at {GREEN[:12]}" in move["why"]
    assert len(kitchen.log("jmerge")) > judged
    assert [jmerge_rows.base_red(TRAIN, runs, slug) for slug in ("one", "two")] == ["", ""]
    assert len(told(kitchen)) == 1


def test_a_train_with_no_pull_request_on_it_is_not_asked_about(kitchen):
    held_on_the_train(kitchen)
    kitchen.set("open.json", [])
    (kitchen.stub / "gh.log").unlink()
    tip(kitchen, RED, "failure")
    kitchen.poll(NOW)
    assert train_red(kitchen) == [] and told(kitchen) == []
    assert not [line for line in kitchen.log("gh") if f"commits/{TRAIN}/" in line]
