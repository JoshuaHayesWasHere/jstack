"""A `Status:` line that says `done` and a note in parentheses is done to every reader in jbus,
as `jbriefs.status` reads it: a scout's row ends done, not left, and a crew's Result leaves
nothing."""

from datetime import timedelta

import pytest

from jbus import homestatus, mirror, stale, watch, work
from test_jbus_entry_go import PLAN
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import go, rows
from test_jbus_scout import add, judged, reported, scout_thread

NOTED = "done (both ran the same cases)"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def test_a_scout_whose_report_says_done_with_a_note_ends_done_not_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status=NOTED)
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "done"
    assert judged(kitchen, "look")["scout"] == "report in"


def test_a_scout_whose_report_says_done_with_a_clause_stays_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status="done, mostly")
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "left"


RESULT = f"## Result\nStatus: {NOTED}\nBranch: look   Pull request: none\nLeft: none\n"


def test_a_crews_result_that_says_done_with_a_note_leaves_nothing():
    assert watch.left(RESULT) == ""
    assert watch.written(RESULT) == work.Written.CLEAN


def test_a_paused_result_with_a_note_waits_on_its_rows():
    result = "## Result\nStatus: paused (until a-b merges)\nWaits on: a-b\n"
    assert mirror.paused_on(result, {"a-b"}) == ("a-b",)


def test_a_home_marks_a_merged_result_done_with_a_note_read_without_showing_it(
    tmp_path, monkeypatch
):
    state = tmp_path / "demo"
    (state / "tasks").mkdir(parents=True)
    (state / "beta").mkdir()
    (state / "beta" / "plan.md").write_text("# beta: plan\n")
    (state / "beta" / "read-seen").write_text("")
    for slug, status in (("noted", NOTED), ("mostly", "done, mostly")):
        (state / "tasks" / f"{slug}.md").write_text(
            f"# {slug}\nHome: beta\n\n## Result\nStatus: {status}\nLeft: none\n"
        )
    (state / "merge.log").write_text(
        '2026-10-13 17:00 merged 1 noted abc "a title", revert: gh pr revert x\n'
        '2026-10-13 17:01 merged 2 mostly abd "a title", revert: gh pr revert y\n'
    )
    monkeypatch.setattr(homestatus.paths, "repo_name", lambda: state.name)

    said = homestatus.run(str(state / "beta"), installed=False, only_gates=False)

    assert "tasks/noted.md: ## Result" not in said
    assert "tasks/mostly.md: ## Result" in said


def test_a_result_that_says_done_with_a_full_stop_is_clean_to_stale():
    assert stale._clean("## Result\nStatus: done.\nLeft: none.\n")
    assert not stale._clean("## Result\nStatus: done, mostly\nLeft: none\n")
