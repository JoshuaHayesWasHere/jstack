"""A red main changes the order: the fix jbus files for it is queued ahead of every row of its
project and is the next launch there, `main.json` (`mainmoved`'s record) keeps the last tip
of main that was green and the red tip that is not, `jmerge` reads that file
(`features/jmerge/tests/test_jmerge_order.py`), and a launched brief names the green sha on a
`Green main:` line. Run as `test_jbus_watch.py` runs: the real pass, against the fakes.
"""

import json
from datetime import timedelta

import jbus.queue
import jbus.wake
import test_jbus_main_moved
from jmerge import mainjson
from jmerge import rows as jmerge_rows
from test_jbus_kitchen import NOW, approved, complete, go, queued
from test_jbus_main_moved import checks, move, pull, tip
from test_jbus_watch import main_of, main_red


def kept(kitchen):
    return mainjson.read(kitchen.state)


def launched(kitchen):
    return [given["title"] for given in kitchen.t3.launches]


def test_the_fix_of_a_red_main_is_queued_ahead_of_every_row_and_launches_next(kitchen):
    for slug, priority in (("beta", 0), ("gamma", -5)):
        text = complete(slug)
        assert kitchen.main("queue", "add", slug, "--priority", str(priority), stdin=text)[0] == 0
    shas = main_of(kitchen, "failure")
    kitchen.poll()
    name = f"main-red-{shas[-1][:12]}"
    rows = jbus.queue.load(kitchen.state)
    assert [row["slug"] for row in sorted(rows, key=jbus.queue.order)] == [name, "gamma", "beta"]
    (fix,) = main_red(kitchen)
    assert fix["priority"] < -5 and fix["approved"] == ""
    for slug in ("gamma", "beta", name):
        assert go(kitchen, slug)[0] == 0
    said = kitchen.poll(NOW + timedelta(minutes=3))
    assert launched(kitchen) == [f"crew: {name}"], said


def test_a_second_red_tip_is_queued_ahead_of_the_fix_that_is_still_waiting(kitchen):
    first = main_of(kitchen, "failure")
    kitchen.poll()
    second = main_of(kitchen, "failure", "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    rows = sorted(jbus.queue.load(kitchen.state), key=jbus.queue.order)
    assert [row["slug"] for row in rows] == [
        f"main-red-{second[-1][:12]}",
        f"main-red-{first[0][:12]}",
    ]


def test_a_green_tip_is_the_last_green_main(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    assert kept(kitchen) == mainjson.Main(green=green)


def test_a_red_tip_keeps_the_green_tip_before_it(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kept(kitchen) == mainjson.Main(green=green, red=red)


def test_a_red_main_with_no_merge_in_a_day_is_still_kept_as_red(kitchen):
    kitchen.quiet()
    red = tip(kitchen)
    checks(kitchen, red, "failure")
    kitchen.poll()
    assert kept(kitchen) == mainjson.Main(red=red)
    assert main_red(kitchen) == []


def test_a_later_green_tip_clears_the_red_and_becomes_the_green(kitchen):
    checks(kitchen, tip(kitchen), "failure")
    kitchen.poll()
    green = move(kitchen, "success")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kept(kitchen) == mainjson.Main(green=green)


def test_a_tip_whose_check_has_not_ended_changes_nothing(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    move(kitchen, "")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kept(kitchen) == mainjson.Main(green=green, red=red)


def test_main_json_is_the_one_record_of_the_red_tip_and_both_readers_agree(kitchen):
    """`mainmoved` keeps the red tip as `broken`, and `jmerge` reads the same sha from the same
    file. `checks.json` holds the sha too, as the answer GitHub gave for that commit, which is no
    record of which tip is red: no other file of the project's state names a red main."""
    checks(kitchen, tip(kitchen), "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    record = json.loads((kitchen.state / "main.json").read_text())
    assert record["broken"] == red == jmerge_rows.main(kitchen.checkout).red
    assert jmerge_rows.red(jmerge_rows.main(kitchen.checkout), "beta").endswith(
        f"{red[:12]}, its fix merges first"
    )
    named = {path.name for path in kitchen.state.rglob("*.json") if red in path.read_text()}
    assert named == {"main.json", "checks.json"}
    assert json.loads((kitchen.state / "checks.json").read_text())[red] == "failed"
    move(kitchen, "success")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert jmerge_rows.main(kitchen.checkout).red == ""


crews = test_jbus_main_moved.launched


def test_a_main_that_turns_green_while_a_message_is_owed_is_green_at_once(crews):
    """A red crew whose head GitHub has not judged yet is owed its message, so `tell` keeps the
    old commit to look at again: the red main is still freed for `jmerge` on that pass."""
    red = tip(crews)
    crews.set("open.json", [pull(crews, "alpha", 7, "FAILURE", mergeable="UNKNOWN")])
    crews.box = jbus.wake.Box(crews.state, jbus.load().projects[0])
    crews.box.mark("rebase|alpha|cccccccccccc")
    green = move(crews)
    crews.poll()
    record = json.loads((crews.state / "main.json").read_text())
    assert (record["main"], record["broken"], record["fixed"]) == (red, red, green)
    assert kept(crews) == mainjson.Main(green=green)
    assert jmerge_rows.main(crews.checkout).red == ""


def test_a_record_from_before_broken_was_kept_names_its_failed_tip_as_red():
    record = {"main": "d" * 40, "check": "failed"}
    assert mainjson.of(record) == mainjson.Main(red="d" * 40)


def test_a_launched_brief_names_the_last_green_main_on_a_green_main_line(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    approved(kitchen, "beta")
    before = (kitchen.state / "briefs" / "beta.md").read_text()
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    line = f"Green main: {green}"
    assert given["message"].splitlines().count(line) == 1
    assert line in given["message"].split("## ")[0]
    assert (kitchen.home / "tasks" / "beta.md").read_text().splitlines().count(line) == 1
    assert (kitchen.state / "briefs" / "beta.md").read_text() == before


def test_a_launched_brief_after_a_red_main_names_the_green_before_the_red(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    approved(kitchen, "beta")
    kitchen.poll(NOW + timedelta(minutes=6))
    (given,) = kitchen.t3.launches
    assert f"Green main: {green}" in given["message"]
    assert red not in given["message"]


def test_a_brief_that_names_a_green_main_itself_is_sent_with_jbus_own_line(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    text = "".join(
        "\n".join(
            [
                "# beta: a task",
                'Task: "do beta"',
                "Green main: " + "9" * 40,
                "Done when:",
                "- it is done",
                "",
            ]
        )
        + "Proves it: `make check`\nSize: S\nWhere: `src/beta/`\nDesign: none, a test\n"
        "Pull request: open one when done\nReview: review\nPlaybook: feature\n"
    )
    queued(kitchen, "beta", text)
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    assert [x for x in given["message"].splitlines() if x.startswith("Green main:")] == [
        f"Green main: {green}"
    ]


def test_a_brief_already_in_the_home_gets_the_green_main_line_it_is_launched_with(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    approved(kitchen, "beta")
    target = kitchen.home / "tasks" / "beta.md"
    target.write_text(
        complete("beta").replace("\n", "\nHome: root\nGreen main: " + "9" * 40 + "\n", 1)
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    line = f"Green main: {green}"
    assert line in given["message"]
    lines = target.read_text().splitlines()
    assert [x for x in lines if x.startswith("Green main:")] == [line]
    assert "Home: root" in lines


def test_a_launch_with_no_green_main_known_sends_the_brief_as_approved(kitchen):
    approved(kitchen, "beta")
    kitchen.poll()
    (given,) = kitchen.t3.launches
    assert "Green main" not in given["message"]
