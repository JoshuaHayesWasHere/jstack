"""`jbus plan` counts a plan entry's status from its queue rows when it reads the plan, and `jbus
queue add --entry` is what ties a row to its entry. Like `test_jbus_kitchen.py`, the tests run
the real command against the kitchen's config, state and home directory."""

import json

import pytest

from jbus import plan as plans
from jbus import queue
from test_jbus_kitchen import Kitchen
from test_jbus_queue import HEAD, RULE, add, adds, brief, rows

PLAN = """\
# demo: plan

## epic: one path for each fact
Stage: planned
Done when:
- it works
Decisions:
- 2026-10-13: "yes, as planned"

## parked-one: a thing for later
Stage: parked

## bare: an entry with nothing under it
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def seen(kitchen, **columns):
    """Set the columns a pass would have derived: `slug=(status, pr)` or `slug=status`."""
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        found = columns.get(row["slug"].replace("-", "_"))
        if found:
            status, pr = (found, "") if isinstance(found, str) else found
            row.update(status=status, pr=pr)
    table.write_text(json.dumps(listed))


def plan(kitchen, *argv):
    code, said = kitchen.main("plan", *argv)
    assert code == 0, said
    return said.splitlines()


def test_add_keeps_the_entry_it_was_given_and_a_row_with_none_is_its_own(kitchen):
    code, said = kitchen.main(
        "queue", "add", "part-1", "--priority", "1", "--entry", "epic", stdin=brief("part-1")
    )
    assert code == 0
    add(kitchen, "alone", approve=False)
    assert rows(kitchen)["part-1"]["entry"] == "epic"
    assert "entry" not in rows(kitchen)["alone"]
    assert said.splitlines()[:3] == [
        HEAD,
        RULE,
        "| part-1 | 1 |  |  |  |  | epic | queued |  |  |  |  |  |  |",
    ]
    add(kitchen, "part-1", approve=False)
    assert rows(kitchen)["part-1"]["entry"] == "epic"
    kitchen.main(
        "queue", "add", "part-1", "--priority", "1", "--entry", "part-1", stdin=brief("part-1")
    )
    assert "entry" not in rows(kitchen)["part-1"]


def test_a_batch_adds_a_row_with_its_entry_and_a_bad_entry_is_refused(kitchen):
    code, said = kitchen.main("queue", "apply", stdin=adds("part-1", "--priority 1 --entry epic"))
    assert (code, said.split(", brief ")[0]) == (0, "added part-1: priority 1, entry epic")
    assert rows(kitchen)["part-1"]["entry"] == "epic"
    refused = kitchen.main(
        "queue", "add", "part-2", "--priority", "1", "--entry", "../up", stdin=brief("part-2")
    )
    assert refused == (1, "refused: --entry is a plan entry's slug, not ../up\n")
    assert sorted(rows(kitchen)) == ["part-1"]


def test_a_table_from_before_the_column_loads_as_it_is(kitchen):
    add(kitchen, "epic")
    before = (kitchen.state / "queue.json").read_text()
    assert '"entry"' not in before
    assert plan(kitchen)[0] == "epic | one path for each fact | 0 of 1 merged, 1 queued"
    assert (kitchen.state / "queue.json").read_text() == before


def test_an_entry_with_rows_is_counted_from_them_and_one_with_none_shows_its_stage(kitchen):
    for number in range(1, 8):
        code, _ = kitchen.main(
            "queue",
            "add",
            f"part-{number}",
            "--priority",
            str(number),
            "--entry",
            "epic",
            stdin=brief(f"part-{number}"),
        )
        assert code == 0
    seen(
        kitchen,
        part_1="merged",
        part_2="merged",
        part_3="merged",
        part_4="merged",
        part_5=("pr", "#383"),
        part_6="running",
    )
    assert plan(kitchen) == [
        "epic | one path for each fact | "
        "4 of 7 merged, #383 at pr, 1 queued not approved, 1 running",
        "parked-one | a thing for later | parked",
        "bare | an entry with nothing under it | no stage",
    ]


def test_an_entry_whose_rows_are_all_over_is_closed_by_its_section_as_it_is(kitchen):
    for slug in ("part-1", "part-2"):
        kitchen.main("queue", "add", slug, "--priority", "1", "--entry", "epic", stdin=brief(slug))
    seen(kitchen, part_1="merged", part_2=("pr", "#9"))
    assert kitchen.main("plan", "close", "epic") == (
        1,
        "refused: epic has rows that are not over: part-2 (pr)\n",
    )
    assert (kitchen.home / "plan.md").read_text() == PLAN
    seen(kitchen, part_2="done")
    assert plan(kitchen)[0] == "epic | one path for each fact | all 2 rows finished: close it"
    done = kitchen.home / "plan-done.md"
    assert kitchen.main("plan", "close", "epic") == (
        0,
        f"closed epic: its section is in {done}\n",
    )
    section = PLAN.split("\n\n", 1)[1].split("## parked-one")[0]
    assert done.read_text() == section
    assert (kitchen.home / "plan.md").read_text() == PLAN.replace(section, "")
    assert plan(kitchen) == [
        "parked-one | a thing for later | parked",
        "bare | an entry with nothing under it | no stage",
    ]
    assert kitchen.main("plan", "close", "bare")[0] == 0
    assert done.read_text() == section + "## bare: an entry with nothing under it\n"
    assert kitchen.main("plan", "close", "epic") == (
        1,
        f"refused: {kitchen.home / 'plan.md'} has no entry epic\n",
    )


def test_a_typed_status_line_is_passed_over_with_rows_and_shown_as_typed_with_none(kitchen):
    text = (
        "# demo: plan\n\n"
        "## epic: one path\nStatus: with crewmate (thread mcp:1)\nDecisions:\n"
        '- 2026-10-12: "Status: planned, as I said"\n\n'
        "## old: a thing from before\nStatus: done (pull request 7 merged)\n"
    )
    (kitchen.home / "plan.md").write_text(text)
    add(kitchen, "epic")
    assert plan(kitchen) == [
        "epic | one path | 0 of 1 merged, 1 queued",
        "old | a thing from before | (typed) Status: done (pull request 7 merged)",
    ]
    assert (kitchen.home / "plan.md").read_text() == text


def test_a_scoped_homes_plan_is_read_by_its_scope(kitchen):
    scope = kitchen.home / "speed"
    scope.mkdir()
    (scope / "plan.md").write_text("# speed: plan\n\n## rs-one: a faster review\nStage: scouting\n")
    assert plan(kitchen, "--scope", "speed") == ["rs-one | a faster review | scouting"]
    assert kitchen.main("--project", "demo", "plan", "--scope", "nope") == (
        1,
        f"refused: no plan at {kitchen.home / 'nope' / 'plan.md'}\n",
    )
    assert kitchen.main("plan", "close", "rs-one", "--scope", "speed")[0] == 0
    assert (scope / "plan-done.md").read_text() == "## rs-one: a faster review\nStage: scouting\n"
    assert kitchen.main("plan", "--scope", "speed") == (0, f"no entry in {scope / 'plan.md'}\n")


def test_a_plan_of_seventeen_entries_prints_under_2500_characters(kitchen):
    """The plan has the live plan's shape: long one-lines, typed lines of a thousand characters,
    and one entry of seven rows."""
    parts = ["# demo: plan\n\nA paragraph that opens the plan.\n"]
    for number in range(17):
        slug = f"an-entry-of-the-plan-{number:02}"
        title = f"what entry {number} is for, " + "said at some length " * 5
        typed = "Status: with crewmate, and then " + "a long account of what happened " * 40
        parts.append(f"## {slug}: {title.strip()}\n{typed.strip()}\nDone when:\n- it works\n")
    (kitchen.home / "plan.md").write_text("\n".join(parts))
    for number in range(7):
        slug = f"part-{number}"
        kitchen.main(
            "queue",
            "add",
            slug,
            "--priority",
            "1",
            "--entry",
            "an-entry-of-the-plan-03",
            stdin=brief(slug),
        )
    seen(kitchen, **{f"part_{number}": ("pr", f"#{380 + number}") for number in range(6)})
    code, said = kitchen.main("plan")
    assert code == 0
    assert len(said.splitlines()) == 17
    assert len(said) < 2500
    assert said.splitlines()[3] == (
        "an-entry-of-the-plan-03 | what entry 3 is for, said at some length said at some... | "
        "0 of 7 merged, #380 at pr, #381 at pr, #382 at pr, #383 a..."
    )
    assert said.splitlines()[0] == (
        "an-entry-of-the-plan-00 | what entry 0 is for, said at some length said at some... | "
        "(typed) Status: with crewmate, and then a long account of..."
    )


def test_a_finished_row_with_something_left_is_not_counted_as_finished():
    entry = plans.Entry("epic", "one path", "planned", "")
    listed = [
        {"slug": "a", "status": "merged", "pr": "#3", "why": ""},
        {"slug": "b", "status": "done", "why": ""},
        {"slug": "c", "status": "merged", "pr": "#12", "why": "its worktree is kept"},
        {"slug": "d", "status": "done", "why": "its Result leaves something"},
        {"slug": "e", "status": "pr", "pr": "#4", "why": "checks"},
        {"slug": "f", "status": "queued", "approved": "his word", "why": ""},
    ]
    assert plans.status(entry, listed) == (
        "1 of 6 merged, 1 done, #4 at pr, #12 at merged, 1 queued, 1 done and waiting"
    )
    assert plans.status(entry, listed[:1]) == "its row finished: close it"


def test_a_plan_asked_for_in_a_repo_the_config_does_not_name_is_refused(kitchen, tmp_path):
    """Every repo has the same home skill, so jbus does not show this project's plan to a home in
    another repo."""
    other = tmp_path / "another-repo"
    kitchen.git("init", "-q", str(other), cwd=tmp_path)
    kitchen.monkeypatch.chdir(other)
    refused = (1, "refused: no project for this repo (another-repo)\n")
    assert kitchen.main("plan") == refused
    assert kitchen.main("plan", "close", "bare") == refused
    assert (kitchen.home / "plan.md").read_text() == PLAN
    assert kitchen.main("--project", "demo", "plan")[1].splitlines()[2] == (
        "bare | an entry with nothing under it | no stage"
    )


def test_a_follow_up_that_names_no_entry_is_counted_for_its_parents(kitchen):
    """A `cleanup-P`, a row with a `Follows: P` line and a fix jbus filed for P do work for P's
    entry, and so does a follow-up of one of them. A row given its own entry keeps it."""
    assert (
        kitchen.main(
            "queue", "add", "part-1", "--priority", "1", "--entry", "epic", stdin=brief("part-1")
        )[0]
        == 0
    )
    add(kitchen, "cleanup-part-1", approve=False)
    add(kitchen, "cleanup-cleanup-part-1", approve=False)
    add(kitchen, "beta", approve=False, text=brief("beta", "Follows: part-1\n"))
    fix = brief("main-red-a", "Follows: part-1\n").replace(
        'Decisions: "review it once"', f"Decisions: {queue.FILED}main"
    )
    queue.add(kitchen.state, "main-red-a", 0, [], fix, ran_by=queue.PASS)
    code, said = kitchen.main(
        "queue",
        "add",
        "gamma",
        "--priority",
        "1",
        "--entry",
        "parked-one",
        stdin=brief("gamma", "Follows: part-1\n"),
    )
    assert code == 0, said
    assert plan(kitchen)[:2] == [
        "epic | one path for each fact | 0 of 5 merged, 5 queued not approved",
        "parked-one | a thing for later | 0 of 1 merged, 1 queued not approved",
    ]
    assert (
        "| cleanup-part-1 | 1 |  |  |  |  | epic (its parent's) |"
        in kitchen.main("queue", "show")[1]
    )


def test_a_row_queued_before_its_parent_or_before_the_column_is_counted_after_a_pass(kitchen):
    add(kitchen, "cleanup-part-2", approve=False)
    assert plan(kitchen)[0] == "epic | one path for each fact | planned"
    assert (
        kitchen.main(
            "queue", "add", "part-2", "--priority", "1", "--entry", "epic", stdin=brief("part-2")
        )[0]
        == 0
    )
    assert (
        plan(kitchen)[0] == "epic | one path for each fact | 0 of 2 merged, 2 queued not approved"
    )
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        row.pop("parent_entry", None)
    table.write_text(json.dumps(listed))
    seen(kitchen, part_2=("merged", "#7"), cleanup_part_2=("merged", "#8"))
    assert plan(kitchen)[0] == "epic | one path for each fact | its row finished: close it"
    kitchen.poll()
    assert rows(kitchen)["cleanup-part-2"]["parent_entry"] == "epic"
    seen(kitchen, part_2=("merged", "#7"), cleanup_part_2=("merged", "#8"))
    assert plan(kitchen)[0] == (
        "epic | one path for each fact | 0 of 2 merged, #7 at merged, #8 at merged"
    )


def test_a_renamed_follow_up_still_counts_for_its_parents_entry(kitchen):
    assert (
        kitchen.main(
            "queue", "add", "part-1", "--priority", "1", "--entry", "epic", stdin=brief("part-1")
        )[0]
        == 0
    )
    add(kitchen, "beta", approve=False, text=brief("beta", "Follows: part-1\n"))
    code, said = kitchen.main("queue", "rename", "beta", "beta-two")
    assert code == 0, said
    assert "entry" not in rows(kitchen)["beta-two"]
    assert (
        plan(kitchen)[0] == "epic | one path for each fact | 0 of 2 merged, 2 queued not approved"
    )
