"""Once a week the root home hears which files pull requests kept conflicting in.

On the first pass on or after Monday in the user's zone, the pass runs
`features/jmerge/scripts/force_pushes.py <state> --since <7 days back> --until <now> --files --json`
in the project's checkout and sends the home one message: the top 10 files by insert and renumber
hunks, each with its pull requests, and a line naming the files new to the top 10 since last
week's report, which `collisions.json` keeps under its Monday. A week with no conflict is one line.
The real pass runs against the kitchen's fakes, whose clock reads Monday 2026-10-12, 11:00 ET."""

import json
import shutil
from datetime import timedelta

import pytest

import jsettings
from jbus import collisions
from test_jbus_kitchen import HOME, NOW, Kitchen
from testing.paths import REPO

DAY, WEEK = timedelta(days=1), timedelta(days=7)
STAND_IN = """import json, pathlib, sys
stub = pathlib.Path({stub!r})
with (stub / "collisions.log").open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
said = (stub / "collisions.json").read_text()
if said.startswith("fail"):
    sys.exit(said)
print(said)
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def stand_in(kitchen, files):
    """Put a script where the real one is that prints `files` as `--json` does, and logs how it
    was called."""
    script = kitchen.checkout / collisions.SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(STAND_IN.format(stub=str(kitchen.stub)))
    said(kitchen, files)


def said(kitchen, files):
    kitchen.set("collisions.json", {"pushes": 1, "merged": 1, "causes": {}, "files": files})


def hit(path, pulls, **hunks):
    return {"path": path, "pulls": pulls, "pushes": len(pulls), "hunks": hunks}


def reports(kitchen):
    return {
        key.split("|")[1]: (sent["threadId"], sent["message"])
        for key, sent in kitchen.t3.messages.items()
        if key.startswith(f"{collisions.TEMPLATE}|")
    }


def kept(kitchen):
    return json.loads((kitchen.state / collisions.LEDGER).read_text())


FILES = [
    *(hit(f"docs/list-{n:02}.md", [100 + n], insert=n) for n in range(1, 12)),
    hit("specs/Flow.tla", [7, 8, 9], renumber=4, edit=2),
    hit("src/code.py", [5, 6], edit=40),
]


def test_a_week_with_no_conflict_is_one_line_from_the_real_script_on_a_fixture_state(kitchen):
    """The real `force_pushes.py`, on a state where one pull request merged with no force-push."""
    script = kitchen.checkout / collisions.SCRIPT
    script.parent.mkdir(parents=True)
    shutil.copy(REPO / collisions.SCRIPT, script)
    kitchen.state.mkdir(parents=True, exist_ok=True)
    merged = {"number": 7, "branch": "alpha", "merged": "2026-10-10T12:00:00Z", "pushes": []}
    (kitchen.state / "ci-prs.jsonl").write_text(json.dumps(merged) + "\n")
    (kitchen.state / "events.jsonl").write_text("")
    kitchen.poll()
    assert reports(kitchen) == {
        "2026-10-12": (
            HOME,
            "collisions demo, week of 2026-10-12 (2026-10-05 to 2026-10-12): "
            "no pull request conflicted with main.",
        )
    }
    assert kept(kitchen)["2026-10-12"]["top"] == []


def test_the_top_ten_by_insert_and_renumber_hunks_go_to_the_home_once_a_week(kitchen):
    stand_in(kitchen, FILES)
    kitchen.poll()
    ((thread, message),) = reports(kitchen).values()
    assert thread == HOME
    assert message.splitlines() == [
        "collisions demo, week of 2026-10-12 (2026-10-05 to 2026-10-12): the top 10 of 13 files "
        "that conflicted, by insert and renumber hunks (`force_pushes.py --files`).",
        "1. `docs/list-11.md`: insert 11; #111",
        "2. `docs/list-10.md`: insert 10; #110",
        "3. `docs/list-09.md`: insert 9; #109",
        "4. `docs/list-08.md`: insert 8; #108",
        "5. `docs/list-07.md`: insert 7; #107",
        "6. `docs/list-06.md`: insert 6; #106",
        "7. `docs/list-05.md`: insert 5; #105",
        "8. `specs/Flow.tla`: renumber 4, edit 2; #7, #8, #9",
        "9. `docs/list-04.md`: insert 4; #104",
        "10. `docs/list-03.md`: insert 3; #103",
        "New to the top 10: no report before this one to compare with.",
    ]
    (argv,) = [json.loads(line) for line in kitchen.log("collisions")]
    assert argv == [
        str(kitchen.state),
        "--since",
        "2026-10-05T15:00:00Z",
        "--until",
        "2026-10-12T15:00:00Z",
        "--files",
        "--json",
    ]
    for later in (timedelta(hours=1), DAY, 6 * DAY):
        kitchen.poll(NOW + later)
    assert list(reports(kitchen)) == ["2026-10-12"]
    assert len(kitchen.log("collisions")) == 1
    assert kept(kitchen)["2026-10-12"]["message"] == message


def test_next_weeks_report_names_the_files_new_to_the_top_ten(kitchen):
    stand_in(kitchen, FILES)
    kitchen.poll()
    said(kitchen, [*FILES, hit("src/jbus/verbs.md", [200, 201], insert=30)])
    kitchen.poll(NOW + WEEK)
    message = reports(kitchen)["2026-10-19"][1]
    assert message.splitlines()[0].startswith(
        "collisions demo, week of 2026-10-19 (2026-10-12 to 2026-10-19): the top 10 of 14 files"
    )
    assert message.splitlines()[1] == "1. `src/jbus/verbs.md`: insert 30; #200, #201"
    assert message.splitlines()[-1] == "New to the top 10: `src/jbus/verbs.md`."
    assert sorted(kept(kitchen)) == ["2026-10-12", "2026-10-19"]


def test_a_week_with_conflicts_but_no_insert_or_renumber_hunk_is_one_line(kitchen):
    stand_in(kitchen, [hit("src/code.py", [5, 6], edit=40)])
    kitchen.poll()
    assert reports(kitchen)["2026-10-12"][1] == (
        "collisions demo, week of 2026-10-12 (2026-10-05 to 2026-10-12): 1 file conflicted, "
        "none by an insert or renumber hunk."
    )


def test_a_run_that_fails_records_nothing_and_the_next_pass_runs_it_again(kitchen):
    stand_in(kitchen, FILES)
    kitchen.set("collisions.json", "fail: gh is down")
    said_now = kitchen.poll()
    assert reports(kitchen) == {}
    assert not (kitchen.state / collisions.LEDGER).exists()
    assert any("did not run (fail: gh is down)" in line for line in said_now)
    said(kitchen, FILES)
    kitchen.poll(NOW + timedelta(hours=1))
    assert list(reports(kitchen)) == ["2026-10-12"]


def test_a_project_whose_checkout_has_no_script_sends_nothing(kitchen):
    kitchen.poll()
    assert reports(kitchen) == {}
    assert not (kitchen.state / collisions.LEDGER).exists()


def test_the_week_is_the_monday_in_the_users_zone(kitchen):
    """Sunday 23:30 ET is still the week before, though it is Monday in UTC."""
    user = jsettings.load()
    assert collisions.week_of(user.local(NOW - timedelta(hours=11, minutes=30))) == "2026-10-05"
    assert collisions.week_of(user.local(NOW)) == "2026-10-12"
