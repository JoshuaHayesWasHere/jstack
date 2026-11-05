"""When the default branch goes from red to green, jbus tells no crew anything: `jmerge` judges a
red pull request again by itself and asks GitHub to merge main into it (`jmerge.cli.Repo.again`,
`features/jmerge/tests/test_jmerge_rejudge.py`). `mainmoved.tell` keeps `main.json`, the record of
main's red tip and green tip that `jmerge` reads to know main is green again. Like
`test_jbus_unlock.py`, the tests run the real pass against the fakes, with the kitchen's own
origin as the remote whose main moves."""

import json
import subprocess
from datetime import timedelta

import pytest

import jbus
from jmerge import mainjson, rows
from test_jbus_kitchen import NOW, iso
from test_jbus_queue import add, go
from test_jbus_watch import beside_a_dispatched_browser_run

HEAD = "c" * 40


@pytest.fixture
def launched(kitchen, request):
    """Alpha and beta are rows that a first pass launched while main's check still ran: a red
    main launches no plain row. Main's check then ends red unless the test asks for `success`,
    and a second pass records where main is. Each thread's turn has ended, since jbus tells
    nothing to a thread that is at work."""
    kitchen.config(max_running=2)
    add(kitchen, "alpha")
    add(kitchen, "beta", priority=2)
    checks(kitchen, tip(kitchen), "")
    said = kitchen.poll(NOW - timedelta(minutes=30))
    assert "launched alpha: mcp:thread-1" in said and "launched beta: mcp:thread-2" in said
    checks(kitchen, tip(kitchen), getattr(request, "param", "failure"))
    kitchen.poll(NOW - timedelta(minutes=29))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    return kitchen


def tip(kitchen):
    asked = ["git", "rev-parse", "refs/heads/main"]
    return subprocess.run(
        asked, cwd=kitchen.origin, capture_output=True, text=True, check=True
    ).stdout.strip()


def red_since(kitchen, sha, at):
    """Write `main.json` as a pass at `at` leaves it once main's check at `sha` failed: the red a
    row launched before it now sits on."""
    kept = mainjson.record(main=sha, at=iso(at), check="failed", broken=sha)
    (kitchen.state / mainjson.NAME).write_text(json.dumps(kept))


def checks(kitchen, sha, conclusion):
    """Set the conclusion of main's one check run at a commit, with `""` for a check run that is
    still running."""
    kept = kitchen.stub / "check-runs.json"
    runs = json.loads(kept.read_text()) if kept.exists() else {}
    runs[sha] = [{"status": "completed" if conclusion else "in_progress", "conclusion": conclusion}]
    kitchen.set("check-runs.json", runs)


def move(kitchen, conclusion="success"):
    """Land a merge on origin's main from another clone, which the checkout never fetches. Its
    check ends as `conclusion` says."""
    other = kitchen.root / "other"
    if not other.exists():
        kitchen.git("clone", "-q", str(kitchen.origin), str(other), cwd=kitchen.root)
    kitchen.git("pull", "-q", "--ff-only", cwd=other)
    kitchen.git("commit", "-q", "--allow-empty", "-m", "a merge", cwd=other)
    kitchen.git("push", "-q", "origin", "main", cwd=other)
    checks(kitchen, tip(kitchen), conclusion)
    return tip(kitchen)


def pull(kitchen, slug, number, state="SUCCESS", mergeable="MERGEABLE"):
    return {**kitchen.opened(slug, number, state), "mergeable": mergeable}


def sends(kitchen):
    """Return every message jbus sent a crew."""
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def test_the_replay_of_494_a_red_pull_request_is_told_nothing_when_main_is_green_again(launched):
    """#494 was red over a red main. When main went green, mainmoved told its crew to rebase, and
    `jmerge` asked GitHub to merge main into it as well: the crew's turn went on a rebase that
    GitHub's merge had made needless. Now the pass only records main as green, which is what
    `jmerge` reads before it asks for that merge (`rows.main`)."""
    red = tip(launched)
    assert rows.main(launched.checkout) == mainjson.Main(red=red)
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    main = move(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert rows.main(launched.checkout) == mainjson.Main(green=main)
    told = [given["clientRequestId"] for given in sends(launched)]
    assert not [key for key in told if key.startswith(("mainmoved|", "rebase|"))], told
    assert launched.lines("mainmoved") == []
    sent = jbus.read_json(launched.state / "sent.json", [])
    assert not [key for key in sent if key.startswith(("mainmoved|", "moved|"))], sent
    assert json.loads((launched.state / "main.json").read_text()) == {
        "main": main,
        "at": NOW.isoformat(),
        "check": "green",
        "green": main,
    }


def test_a_record_left_owing_a_message_ends_the_red_at_its_fixed_tip(launched):
    """A pass before `tell` stopped telling crews could leave `fixed`, the green tip, beside the
    old commit while a message was owed. The next pass takes the red as ended there, though the
    newest tip is pending and GitHub lists none of main's commits, and writes no `fixed` again."""
    red = tip(launched)
    fixed = move(launched)
    owed = {**mainjson.record(main=red, at=iso(NOW), check="failed", broken=red), "fixed": fixed}
    (launched.state / mainjson.NAME).write_text(json.dumps(owed))
    move(launched, "")
    launched.poll()
    assert mainjson.read(launched.state).red == "", f"main reads red at {red[:12]}"
    record = jbus.read_json(launched.state / mainjson.NAME, {})
    assert ("fixed" in record, "held" in record, "broken" in record) == (False, False, False)


def test_the_first_pass_with_no_main_json_records_the_commit(launched):
    (launched.state / "main.json").unlink()
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    main = move(launched)
    launched.poll()
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_a_kept_red_at_a_tip_whose_push_run_passed_beside_a_failed_browser_run_clears(launched):
    """jstack's main.json at d1e3bd5: `checks.json` kept `failed` from three browser runs
    dispatched at main's tip, and main's push run there had passed. The next pass reads main
    green, and jmerge holds nothing."""
    main = tip(launched)
    kept = json.loads((launched.state / "main.json").read_text())
    assert (kept["check"], jbus.read_json(launched.state / "checks.json", {})) == (
        "failed",
        {main: "failed"},
    )
    check_runs, workflow_runs = beside_a_dispatched_browser_run(main, "success")
    launched.set("check-runs.json", check_runs)
    launched.set("push-runs.json", workflow_runs)
    launched.poll()
    record = json.loads((launched.state / "main.json").read_text())
    assert {k: v for k, v in record.items() if k != "at"} == {
        "main": main,
        "check": "green",
        "green": main,
    }
    assert mainjson.read(launched.state).red == ""


def test_a_failed_tip_whose_check_is_rerun_and_passes_is_green_with_no_new_commit(launched):
    """A flake: main's check fails at its tip, and a rerun of that check passes while the tip
    stays where it is. jbus filed a fix row for the flake, and the row is not approved. jbus
    reports the row as green again and leaves it as it is. The next test covers an approved row."""
    red = tip(launched)
    launched.set("commits.json", [launched.commit(red)])
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    add(launched, f"main-red-{red[:12]}", priority=0, approve=False)
    launched.poll()
    assert mainjson.read(launched.state).red == red
    checks(launched, red, "success")
    for minutes in (3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert mainjson.read(launched.state) == mainjson.Main(green=red)
    record = jbus.read_json(launched.state / "main.json", {})
    assert (record["check"], record["green"], "broken" in record) == ("green", red, False)
    assert not [one for one in sends(launched) if one["clientRequestId"].startswith("mainmoved|")]
    row = f"main-red-{red[:12]}"
    green = f"retro {row}: main is green again at {red[:12]}, and its row is left as it is"
    assert [line for line in launched.lines("retro") if "green again" in line] == [green]
    assert [r.get("thread") for r in jbus.queue.load(launched.state) if r["slug"] == row] == [""]


def test_a_fix_row_approved_after_its_main_is_green_again_is_never_launched(launched):
    """As with main-red-b66eaae4c2ca: its tip's check failed, a rerun passed, and the row got its
    approval after that. A main that is green needs no fix, so jbus does not launch the row."""
    red = tip(launched)
    launched.set("commits.json", [launched.commit(red)])
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    row = f"main-red-{red[:12]}"
    add(launched, row, priority=0, approve=False)
    launched.poll()
    checks(launched, red, "success")
    for minutes in (3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [line for line in launched.lines("retro") if "green again" in line] != []
    assert go(launched, row)[0] == 0
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    (left,) = [r for r in jbus.queue.load(launched.state) if r["slug"] == row]
    assert (left.get("thread"), left.get("status")) == ("", "queued")
    assert left.get("why") == (
        f"main is green again at {red[:12]}, its own commit, so it has no red to fix"
    )


@pytest.mark.parametrize("launched", ["success"], indirect=True)
def test_a_tip_that_failed_under_one_no_pass_saw_is_red_while_the_newest_is_pending(launched):
    first = tip(launched)
    red = move(launched, "failure")
    newest = move(launched, "")
    parents = ((newest, red), (red, first))
    commits = [{**launched.commit(sha), "parents": [{"sha": parent}]} for sha, parent in parents]
    launched.set("commits.json", commits)
    launched.poll()
    assert mainjson.read(launched.state).red == red


def test_the_rebase_message_writes_its_key_and_no_main_moved_key(launched):
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    launched.set("open.json", [pull(launched, "alpha", 7, mergeable="CONFLICTING")])
    launched.poll()
    sent = jbus.read_json(launched.state / "sent.json", [])
    assert "rebase|alpha|cccccccccccc" in sent
    assert [key for key in sent if key.startswith(("mainmoved|", "moved|"))] == []
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]
