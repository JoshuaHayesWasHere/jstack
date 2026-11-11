"""A revert is held by every check that leans on it, and closes only once each of them is green.

On 2026-11-09 main's check and main's macOS run were both red at fb38874a515a. jbus reverted it
for main (#1426), and the Mac read that revert as its own (`Keep.OPENED`). Main's check then
passed at the red commit itself, and `reverts.close` closed #1426 while the Mac was still red there.
The next pass dropped the closed revert's record, its culprit's slug being over, and the Mac, red
at the same commit and finding no record, opened a second revert of the same row (#1427).

`reverts.json` now keeps, beside each revert, the checks that lean on it (`holders`): the one that
opened it, and each that later read it as its own, main's check in `jbus.culprits.judge` and the
Mac in `reverts.macos`. `close` closes it only once every holder is
green, and its record goes only once every check jbus judges main by has passed at or above its
red, so the row is reverted once.

The tests run the real pass against the fakes, as `test_jbus_reverts.py` does."""

import json
from datetime import timedelta

from jbus import reverts
from jmerge import mainjson
from jmerge import reverts as kept
from test_jbus_kitchen import NOW
from test_jbus_main_moved import move
from test_jbus_reverts import (
    DONE,
    LOG,
    MAC_FLOW,
    asked,
    mac_flow,
    mac_rows,
    mac_state,
    red_merges,
)
from test_jbus_watch import main_red


def both_red(kitchen):
    """alpha's merge lands red on main's check after its one rerun, and on main's macOS run at its
    first attempt, on a commit where both passed. Return the red commit."""
    mac_flow(kitchen)
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    green = json.loads((kitchen.stub / "commits.json").read_text())[-1]["sha"]
    mac = {"path": MAC_FLOW, "event": "push", "head_branch": "main", **DONE}
    suite = {"check_suite": {"id": 71}}
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    runs[green] = [
        {**DONE, "conclusion": "success", "name": "check", "id": 90},
        {**DONE, "conclusion": "success", "name": "macos", "id": 190, "check_suite": {"id": 70}},
    ]
    runs[red] = [*runs[red], {**DONE, "conclusion": "failure", "name": "macos", "id": 191} | suite]
    kitchen.set("check-runs.json", runs)
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    pushed[green] = [{**mac, "id": 600, "conclusion": "success", "check_suite_id": 70}]
    pushed[red] = [
        *pushed[red],
        {**mac, "id": 601, "conclusion": "failure", "run_attempt": 1, "check_suite_id": 71},
    ]
    kitchen.set("push-runs.json", pushed)
    logs = json.loads((kitchen.stub / "logs.json").read_text())
    kitchen.set("logs.json", {**logs, "191": LOG})
    return red


def mac_rerun_fails(kitchen, sha):
    """The Mac's one rerun at `sha` fails too."""
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    pushed[sha] = [
        one | {"run_attempt": 2} if one.get("path") == MAC_FLOW else one for one in pushed[sha]
    ]
    kitchen.set("push-runs.json", pushed)


def main_red_then_mac(kitchen):
    """`both_red`, main's revert opened while the Mac's rerun runs, then the Mac red after it.
    Return the red commit."""
    red = both_red(kitchen)
    polls(kitchen, 0, 3)
    mac_rerun_fails(kitchen, red)
    polls(kitchen, 10, 2)
    return red


def main_passes_at(kitchen, sha):
    """Main's check passes at `sha` on a later run, as the rerun after an outage did at
    fb38874a515a: its macOS run there stays red."""
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    runs[sha] = [
        one | {"conclusion": "success"} if one["name"] == "check" else one for one in runs[sha]
    ]
    kitchen.set("check-runs.json", runs)
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    pushed[sha] = [
        one | {"conclusion": "success"} if one.get("path") != MAC_FLOW else one
        for one in pushed[sha]
    ]
    kitchen.set("push-runs.json", pushed)


def mac_passes_later(kitchen):
    """A later merge lands with main's check and its macOS run both green. Return its commit."""
    later = move(kitchen, "success")
    commits = json.loads((kitchen.stub / "commits.json").read_text())
    kitchen.set("commits.json", [kitchen.commit(later, "fix: the mac (#9)"), *commits])
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    good = {"path": MAC_FLOW, **DONE, "id": 700, "conclusion": "success", "check_suite_id": 79}
    main = {**DONE, "id": 701, "conclusion": "success", "run_attempt": 1}
    kitchen.set("push-runs.json", {**pushed, later: [main, good]})
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    ran = [
        {**DONE, "conclusion": "success", "name": "check", "id": 99},
        {**DONE, "conclusion": "success", "name": "macos", "id": 199, "check_suite": {"id": 79}},
    ]
    kitchen.set("check-runs.json", {**runs, later: ran})
    return later


def polls(kitchen, start, count):
    for n in range(count):
        kitchen.poll(NOW + timedelta(minutes=start + 3 * n))


def test_the_mac_red_and_main_green_at_one_commit_keep_the_revert_open(kitchen):
    """The replay of #1426: main and the Mac red at one commit, main's revert open and the Mac
    leaning on it. Main's check then passes at the red commit itself, and the Mac is still red
    there: the revert stays open, and its record names both checks."""
    red = main_red_then_mac(kitchen)
    (revert,) = asked(kitchen, "pr revert")
    assert "main went red" in revert
    main_passes_at(kitchen, red)
    polls(kitchen, 30, 4)
    main = mainjson.read(kitchen.state)
    assert (main.red, main.green) == ("", red)
    assert mac_state(kitchen)["red"] == red
    assert asked(kitchen, "pr close") == []
    assert list(kept.read(kitchen.state)) == [red]
    assert len(asked(kitchen, "pr revert")) == 1
    assert reverts.holders(kitchen.state) == {red: {reverts.MAIN, reverts.MAC}}


def test_a_revert_closed_once_every_holder_is_green_is_never_opened_again(kitchen):
    """Once the Mac too is green at a later commit, the revert closes, naming the Mac's green,
    and its record ends on a later pass. No pass after that opens a second revert of alpha."""
    red = main_red_then_mac(kitchen)
    main_passes_at(kitchen, red)
    polls(kitchen, 30, 2)
    later = mac_passes_later(kitchen)
    polls(kitchen, 60, 6)
    (closed,) = asked(kitchen, "pr close")
    assert "main's macOS run passed at" in closed and later[:12] in closed
    assert len(asked(kitchen, "pr revert")) == 1
    assert kept.read(kitchen.state) == {}


def test_a_revert_main_closed_before_the_mac_judged_its_red_is_not_opened_again(kitchen):
    """Main's check passes at the red commit before the Mac has read it, so main is its one
    holder and the revert closes. The Mac then goes red there: it leans on the closed revert,
    whose record stays until the Mac passes at or above the red, and no second revert opens."""
    red = both_red(kitchen)
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    mac_runs = [one for one in runs[red] if one["name"] == "macos"]
    mac_pushes = [one for one in pushed[red] if one.get("path") == MAC_FLOW]
    kitchen.set("check-runs.json", {**runs, red: [o for o in runs[red] if o not in mac_runs]})
    kitchen.set("push-runs.json", {**pushed, red: [o for o in pushed[red] if o not in mac_pushes]})
    polls(kitchen, 0, 3)
    main_passes_at(kitchen, red)
    polls(kitchen, 10, 2)
    assert len(asked(kitchen, "pr close")) == 1
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    kitchen.set("check-runs.json", {**runs, red: [*runs[red], *mac_runs]})
    mac_pushes = [one | {"run_attempt": 2} for one in mac_pushes]
    kitchen.set("push-runs.json", {**pushed, red: [*pushed[red], *mac_pushes]})
    polls(kitchen, 20, 6)
    assert mac_state(kitchen)["red"] == red
    assert list(kept.read(kitchen.state)) == [red]
    assert len(asked(kitchen, "pr revert")) == 1


def test_a_revert_both_checks_lean_on_that_stalls_gets_each_check_s_row_and_no_second(kitchen):
    """The revert main opened and the Mac leans on gets a failed check while both are still red
    at its commit: it will not end either red by itself, so main files its fix row and the Mac its
    `macos-red-` row, each naming the stalled revert, and neither opens a second revert."""
    red = main_red_then_mac(kitchen)
    made = kept.read(kitchen.state)[red]
    pulls = json.loads((kitchen.stub / "open.json").read_text())
    failed = [{"status": "COMPLETED", "conclusion": "FAILURE", "name": "check"}]
    for pull in pulls:
        if pull["url"] == made.pull:
            pull["statusCheckRollup"] = failed
    kitchen.set("open.json", pulls)
    polls(kitchen, 30, 3)
    (row,) = main_red(kitchen)
    text = (kitchen.home / "tasks" / f"{row['slug']}.md").read_text()
    assert f"its revert {made.pull} has a failed check" in text
    (mac,) = mac_rows(kitchen)
    text = (kitchen.home / "tasks" / f"{mac['slug']}.md").read_text()
    assert f"its revert {made.pull} has a failed check" in text
    assert len(asked(kitchen, "pr revert")) == 1
    assert reverts.holders(kitchen.state) == {red: {reverts.MAIN, reverts.MAC}}
