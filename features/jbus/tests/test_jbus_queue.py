"""Each column of the queue table has one writer, and a pass launches only what the user
approved, once. Like `test_jbus_kitchen.py`, the tests run the real command and the real pass
against a faked T3 Code server, `gh` and `jmerge`."""

import hashlib
import json
import threading
from datetime import timedelta

import pytest
from jsonschema import Draft202012Validator

import jbus
import test_tool_calls as tools
from jbus import cli, queue, wake
from test_jbus_kitchen import GO, NOW, PROJECT, QUARTER_PAST_FIVE, RESULT, SAID, Kitchen
from test_machine_sizes import fake_proc

AT = "2026-10-11 17:58 ET"
HEAD = (
    "| slug | priority | depends | merge_after | approved | brief_sha | entry | status | thread "
    "| pr | checks | updated | why | since |"
)
RULE = "|" + " --- |" * 14
SINCE = "since 2026-10-12 11:00 ET"
NO_BASIS = (
    "approve takes one basis, --word <id>, --answer <number>, --message <thread id>/<message "
    "id> or --page <session key>/<entry id>, or --rule <n> with --follows <parent slug>, and "
    "no --by and no --at: jbus writes who ran it and when"
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def brief(slug, more=""):
    """Return a brief with every field that `queue add` asks for, and `more` under them."""
    return (
        f'# {slug}: a task\nHome: mcp:a-home\nTask: "do {slug}"\nDone when:\n- it is done\n'
        f"Proves it: `make check`\nSize: S\nWhere: `src/{slug}/`, a new test\n"
        "Design: none, a test\nPull request: open one when done\nReview: review\n"
        f"Playbook: feature\n{more}"
    )


def widened(slug, line="One more line."):
    """Return the brief with one more `Done when:` item, which changes what it asks for."""
    return brief(slug).replace("- it is done\n", f"- it is done\n- {line}\n")


def sha12(text):
    return queue.brief_sha(text)[:12]


def go(kitchen, slug, sha=None, project="demo"):
    """Give the user's go for the brief that is stored now, or for the one whose sha is given."""
    sha = sha or sha12((kitchen.state_dir / project / "briefs" / f"{slug}.md").read_text())
    argv = ["--project", project, "queue", "approve", slug]
    return kitchen.main(*argv, "--word", kitchen.word(project), "--sha", sha)


def add(kitchen, slug, priority=1, depends="", approve=True, text=None, project="demo"):
    argv = ["--project", project, "queue", "add", slug, "--priority", str(priority)]
    code, said = kitchen.main(
        *argv, *(["--depends", depends] if depends else []), stdin=text or brief(slug)
    )
    assert code == 0, said
    if approve:
        assert go(kitchen, slug, project=project)[0] == 0


def queued_before(kitchen, slug, text, priority=1, depends="", approve=True):
    """Queue a row the way rows were queued before `jbus queue add` checked a brief. Its stored
    brief is `text`, which `add` would refuse now. Where `approve` is set, its go is for that
    text, as a go was then."""
    add(kitchen, slug, priority=priority, depends=depends, approve=approve)
    queue.brief_path(kitchen.state, slug).write_text(text)
    path = kitchen.state / "queue.json"
    table = json.loads(path.read_text())
    for row in table:
        if row["slug"] == slug and row.get("approval"):
            row["brief_sha"] = queue.brief_sha(text)
            for column in ("brief_sha", "scope", "meaning"):
                row["approval"].pop(column, None)
    path.write_text(json.dumps(table))


def rows(kitchen):
    return {row["slug"]: row for row in json.loads((kitchen.state / "queue.json").read_text())}


def gates(kitchen):
    return kitchen.lines("condition")


def test_add_approve_and_hold_write_the_chefs_columns_and_show_prints_the_table(kitchen):
    add(kitchen, "beta", priority=2, depends="alpha,gamma", approve=False)
    add(kitchen, "alpha", priority=1, approve=False)
    sha = queue.brief_sha(brief("alpha"))
    assert rows(kitchen)["beta"] == {
        "slug": "beta",
        "priority": 2,
        "depends": ["alpha", "gamma"],
        "approved": "",
        "brief_sha": "",
        "item": "w1",
        "status": "queued",
        "thread": "",
        "pr": "",
        "checks": "",
        "updated": "",
        "why": "",
        "since": "",
    }
    code, said = go(kitchen, "alpha", sha[:12])
    assert code == 0
    assert (rows(kitchen)["alpha"]["approved"], rows(kitchen)["alpha"]["brief_sha"]) == (
        GO,
        sha,
    )
    assert kitchen.main("queue", "show") == (0, said)
    assert said.splitlines() == [
        HEAD,
        RULE,
        f"| alpha | 1 |  |  | {GO} | {sha[:12]} |  | queued |  |  |  |  |  |  |",
        "| beta | 2 | alpha, gamma |  |  |  |  | queued |  |  |  |  |  |  |",
    ]
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    assert (rows(kitchen)["alpha"]["approved"], rows(kitchen)["alpha"]["brief_sha"]) == ("", "")


def finish(kitchen, **status):
    """Set the status a pass would have written, with no reason to wait."""
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        row["status"] = status.get(row["slug"], row["status"])
    table.write_text(json.dumps(listed))


def cells(said):
    return [line.split(" | ")[0].removeprefix("| ") for line in said.splitlines()[2:]]


def test_show_prints_the_rows_still_open_and_counts_the_finished_ones(kitchen):
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    finish(kitchen, alpha="merged", beta="done")
    code, said = kitchen.main("queue", "show")
    assert code == 0
    assert said.splitlines()[0] == HEAD
    assert cells(said) == ["gamma", "", "2 finished rows not shown: jbus queue show --all"]
    assert said.endswith("\n2 finished rows not shown: jbus queue show --all\n")


def test_show_all_prints_every_row_and_no_count(kitchen):
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    before = kitchen.main("queue", "show")[1]
    finish(kitchen, alpha="merged", beta="done")
    code, said = kitchen.main("queue", "show", "--all")
    assert code == 0
    assert cells(said) == ["alpha", "beta", "gamma"]
    assert said == before.replace("| queued |", "| merged |", 1).replace(
        "| queued |", "| done |", 1
    )


def test_a_row_at_left_or_finished_with_a_reason_to_wait_is_still_shown(kitchen):
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    finish(kitchen, alpha="left", beta="merged", gamma="merged")
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    listed[1]["why"] = "its worktree is kept"
    table.write_text(json.dumps(listed))
    said = kitchen.main("queue", "show")[1]
    assert cells(said) == ["alpha", "beta", "", "1 finished row not shown: jbus queue show --all"]


def test_a_verb_that_prints_the_table_after_prints_the_open_rows_too(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    finish(kitchen, alpha="merged")
    code, said = kitchen.main("queue", "hold", "beta")
    assert code == 0
    assert cells(said) == ["beta", "", "1 finished row not shown: jbus queue show --all"]


@pytest.mark.parametrize(
    "argv, stdin, says",
    [
        (
            ["approve", "alpha", "--by", "user", "--at", AT, "--sha", "0" * 12],
            "",
            f"refused: {NO_BASIS}",
        ),
        (["approve", "alpha", "--sha", "0" * 12], "", f"refused: {NO_BASIS}"),
        (
            ["approve", "alpha", "--word", SAID, "--at", AT, "--sha", "0" * 12],
            "",
            f"refused: {NO_BASIS}",
        ),
        (
            ["approve", "alpha", "--word", SAID, "--answer", "1", "--sha", "0" * 12],
            "",
            f"refused: {NO_BASIS}",
        ),
        (
            ["approve", "nope", "--word", SAID, "--sha", "0" * 12],
            "",
            "refused: the queue has no row nope",
        ),
        (["hold", "nope"], "", "refused: the queue has no row nope"),
        (["add", "gamma", "--priority", "1"], "", "refused: no brief on stdin"),
        (["add", "../up", "--priority", "1"], "a brief", "refused: ../up is not a slug"),
    ],
)
def test_a_verb_that_cannot_be_done_is_refused_and_changes_nothing(kitchen, argv, stdin, says):
    add(kitchen, "alpha", approve=False)
    before = (kitchen.state / "queue.json").read_text()
    assert kitchen.main("queue", *argv, stdin=stdin) == (1, says + "\n")
    assert (kitchen.state / "queue.json").read_text() == before


@pytest.mark.parametrize("column", ["status", "thread", "pr", "checks", "updated", "why", "since"])
def test_no_verb_sets_a_derived_column(kitchen, column):
    add(kitchen, "alpha", approve=False)
    before = (kitchen.state / "queue.json").read_text()
    says = f"refused: {column} is derived from T3 Code and GitHub, and no command writes it\n"
    for argv in (
        ["add", "alpha", "--priority", "1", f"--{column}", "merged"],
        ["approve", "alpha", "--by", "user", "--at", AT, "--sha", "0" * 12, f"--{column}=merged"],
        ["hold", "alpha", f"--{column}", "merged"],
    ):
        assert kitchen.main("queue", *argv, stdin="a brief") == (2, says)
    assert (kitchen.state / "queue.json").read_text() == before


def test_an_approval_is_refused_unless_it_names_the_sha_of_the_stored_brief(kitchen):
    add(kitchen, "alpha", approve=False)
    shown = sha12(brief("alpha"))
    before = (kitchen.state / "queue.json").read_text()
    assert go(kitchen, "alpha", "0" * 12) == (
        1,
        f"refused: alpha's brief is {shown}, not 000000000000\n",
    )
    assert (kitchen.state / "queue.json").read_text() == before
    assert go(kitchen, "alpha", shown)[0] == 0
    assert rows(kitchen)["alpha"]["approved"] == GO
    assert rows(kitchen)["alpha"]["brief_sha"] == queue.brief_sha(brief("alpha"))


def test_an_approval_with_no_sha_is_not_run(kitchen):
    add(kitchen, "alpha", approve=False)
    code, said = kitchen.main("queue", "approve", "alpha", "--by", "user", "--at", AT)
    assert code == 2 and "the following arguments are required: --sha" in said
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_brief_replaced_after_the_user_saw_it_is_not_the_brief_their_go_approves(kitchen):
    add(kitchen, "alpha", approve=False)
    shown = sha12(brief("alpha"))
    add(kitchen, "alpha", approve=False, text=brief("alpha", "And one thing nobody showed.\n"))
    stored = sha12(brief("alpha", "And one thing nobody showed.\n"))
    assert go(kitchen, "alpha", shown) == (1, f"refused: alpha's brief is {stored}, not {shown}\n")
    assert (rows(kitchen)["alpha"]["approved"], rows(kitchen)["alpha"]["brief_sha"]) == ("", "")
    kitchen.poll()
    assert kitchen.t3.launches == []


def batch(*parts):
    return "".join(parts)


def adds(slug, more="", text=None):
    return f"add {slug} {more}\n--- brief {slug}\n{text or brief(slug)}--- end\n"


def approves(slug, sha):
    return f"approve {slug} --word {SAID} --sha {sha}\n"


def stored(kitchen):
    """Return everything a queue verb writes: the table and the briefs beside it."""
    files = [kitchen.state / "queue.json", *sorted((kitchen.state / "briefs").glob("*.md"))]
    return {path.name: path.read_text() for path in files if path.exists()}


def test_a_batch_applies_every_verb_and_prints_one_line_for_each(kitchen):
    add(kitchen, "old")
    alpha, beta = sha12(brief("alpha")), sha12(brief("beta"))
    code, said = kitchen.main(
        "queue",
        "apply",
        stdin=batch(
            adds("alpha", "--priority 1"),
            "\n",
            adds("beta", "--priority 2 --depends alpha,old"),
            approves("alpha", alpha),
            "hold old\n",
        ),
    )
    assert (code, said.splitlines()) == (
        0,
        [
            f"added alpha: priority 1, brief {alpha}",
            f"added beta: priority 2, depends alpha, old, brief {beta}",
            f"approved alpha: brief {alpha}, {GO}",
            "held old",
        ],
    )
    table = rows(kitchen)
    assert (kitchen.state / "briefs/alpha.md").read_text() == brief("alpha")
    assert (table["alpha"]["approved"], table["alpha"]["brief_sha"][:12]) == (
        GO,
        alpha,
    )
    assert (table["beta"]["priority"], table["beta"]["depends"], table["beta"]["approved"]) == (
        2,
        ["alpha", "old"],
        "",
    )
    assert (table["old"]["approved"], table["old"]["brief_sha"]) == ("", "")
    kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]


def test_an_approve_in_a_batch_names_the_brief_added_earlier_in_the_same_batch(kitchen):
    add(kitchen, "alpha", approve=False)
    newer = brief("alpha", "As the user was shown it.\n")
    text = batch(adds("alpha", "--priority 3", newer), approves("alpha", sha12(newer)))
    assert kitchen.main("queue", "apply", stdin=text)[0] == 0
    row = rows(kitchen)["alpha"]
    assert (row["priority"], row["brief_sha"]) == (3, queue.brief_sha(newer))
    older = batch(adds("alpha", "--priority 3"), approves("alpha", sha12(newer)))
    assert kitchen.main("queue", "apply", stdin=older) == (
        1,
        f"refused: line 16: alpha's brief is {sha12(brief('alpha'))}, not {sha12(newer)},"
        " and nothing in the batch was applied\n",
    )
    assert (kitchen.state / "briefs/alpha.md").read_text() == newer


@pytest.mark.parametrize(
    "bad, says",
    [
        ("hold nope\n", "line 17: the queue has no row nope"),
        (
            approves("alpha", "0" * 12),
            f"line 17: alpha's brief is {sha12(brief('alpha'))}, not 0000",
        ),
        (f'approve alpha --by user --at "{AT}" --sha 0\n', f"line 17: {NO_BASIS}"),
        ("approve alpha --sha 0\n", f"line 17: {NO_BASIS}"),
        ("approve alpha --word nope --sha 0\n", "line 17: alpha's brief is"),
        (f"approve alpha --word {SAID}\n", "line 17: approve needs --sha"),
        ("add gamma --priority 1\nhold alpha\n", "line 17: add gamma has no --- brief gamma"),
        (
            "add gamma --priority 1\n--- brief gamma\nA brief.\n",
            "line 17: gamma's brief has no --- end",
        ),
        (
            "add gamma --priority 1\n--- brief gamma\nA brief.\n--- brief delta\nmore\n--- end\n",
            "line 17: gamma's brief has no --- end",
        ),
        (adds("gamma", "--priority soon"), "line 17: --priority is an integer, not soon"),
        (adds("gamma"), "line 17: add needs --priority"),
        (adds("../up", "--priority 1"), "line 17: ../up is not a slug"),
        ("hold alpha --status merged\n", "line 17: status is derived from T3 Code and GitHub"),
        ("hold alpha --at now\n", "line 17: hold takes no --at"),
        ("drop alpha\n", "line 17: drop is not add, approve, hold or remove"),
        ('hold "alpha\n', "line 17: No closing quotation"),
    ],
)
def test_a_batch_with_one_verb_that_cannot_be_done_writes_nothing(kitchen, bad, says):
    add(kitchen, "old")
    before = stored(kitchen)
    good = batch(adds("alpha", "--priority 1"), "hold old\n")
    code, said = kitchen.main(
        "queue", "apply", stdin=batch(good, bad, adds("beta", "--priority 2"))
    )
    assert code == 1 and said.startswith(f"refused: {says}"), said
    assert said.endswith(", and nothing in the batch was applied\n") and said.count("\n") == 1
    assert stored(kitchen) == before


def test_a_batch_with_no_verb_is_refused(kitchen):
    assert kitchen.main("queue", "apply", stdin="\n") == (1, "refused: no verb on stdin\n")


def scene(kitchen, status):
    """Make what T3 Code and GitHub say to give a row this status, and return the row's columns."""
    t3 = kitchen.t3
    if status == "queued":
        return {}
    if status == "pr":
        kitchen.set("open.json", [kitchen.opened("alpha", 9, "FAILURE")])
        return {
            "thread": t3.thread("alpha", "completed")["threadId"],
            "pr": "#9",
            "checks": "failed",
        }
    if status == "merged":
        kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
        return {"thread": t3.thread("alpha", "completed", settled=True)["threadId"], "pr": "#9"}
    if status == "gate":
        t3.thread("alpha", "running")
        t3.thread("alpha", "running")
        return {}
    given = {
        "launched": ("preparing", {}),
        "running": ("running", {}),
        "waiting": ("waiting", {}),
        "failed": ("interrupted", {}),
        "stale": ("completed", {}),
    }
    state, more = given[status]
    return {"thread": t3.thread("alpha", state, **more)["threadId"]}


@pytest.mark.parametrize(
    "status",
    ["queued", "launched", "running", "waiting", "pr", "merged", "failed", "stale", "gate"],
)
def test_a_pass_writes_the_derived_columns_from_t3_code_and_github(kitchen, status):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", RESULT if status in ("pr", "merged") else "")
    expected = scene(kitchen, status)
    kitchen.poll()
    row = rows(kitchen)["alpha"]
    blank = {"thread": "", "pr": "", "checks": ""}
    assert {c: row[c] for c in ("status", *blank)} == {"status": status, **blank, **expected}
    assert row["updated"] == ("" if status == "queued" else "2026-10-12 11:00 ET")


def test_a_hand_edit_of_a_derived_column_is_rewritten_and_the_chefs_columns_are_kept(kitchen):
    add(kitchen, "alpha", priority=3, depends="beta")
    chef = {
        c: rows(kitchen)["alpha"][c]
        for c in ("slug", "priority", "depends", "approved", "brief_sha")
    }
    table = list(rows(kitchen).values())
    table[0].update(status="merged", thread="mcp:made-up", pr="#99", checks="passed")
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    kitchen.poll()
    row = rows(kitchen)["alpha"]
    assert {c: row[c] for c in ("status", "thread", "pr", "checks")} == {
        "status": "queued",
        "thread": "",
        "pr": "",
        "checks": "",
    }
    assert {c: row[c] for c in chef} == chef


def test_a_changed_table_is_one_queue_event_and_a_quiet_pass_sends_none(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert kitchen.events("queue") == []
    kitchen.t3.thread("alpha", "running")
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    (event,) = kitchen.events("queue")
    assert (event["slug"], event["line"]) == ("", "queue demo: the table changed")
    assert "| running | mcp:thread-1 |  |  | 2026-10-12 11:03 ET |" in event["text"]


def twenty(kitchen):
    """Add a queue of 20 rows."""
    for number in range(1, 21):
        add(kitchen, f"row-{number:02}", priority=number, approve=False)


def table(kitchen):
    """Return the whole table, every row of it."""
    return queue.render(list(rows(kitchen).values()))


def test_a_queue_event_holds_the_row_that_changed_and_what_changed_in_it(kitchen):
    twenty(kitchen)
    kitchen.poll()
    assert kitchen.events("queue") == []
    kitchen.t3.thread("row-07", "running")
    kitchen.poll(NOW + timedelta(minutes=3))
    (event,) = kitchen.events("queue")
    assert event["line"] == "queue demo: the table changed"
    assert event["text"] == (
        "row-07: status queued -> running, thread (empty) -> mcp:thread-1\n\n"
        f"{HEAD}\n{RULE}\n"
        "| row-07 | 7 |  |  |  |  |  | running | mcp:thread-1 |  |  | 2026-10-12 11:03 ET |  |  |\n"
    )
    whole = table(kitchen)
    assert whole.count("| row-") == 20 and len(whole) == 1989
    assert event["text"].count("| row-") == 1 and len(event["text"]) == 372


def test_a_removal_is_a_queue_event_of_the_row_that_went(kitchen):
    twenty(kitchen)
    removal = ("queue", "remove", "row-07", "--by", "user", "--at", AT)
    assert kitchen.main(*removal)[0] == 0
    (event,) = kitchen.events("queue")
    assert (event["slug"], event["line"]) == (
        "row-07",
        f"queue demo: removed row-07, {AT} by user",
    )
    assert (
        event["text"]
        == f"{HEAD}\n{RULE}\n| row-07 | 7 |  |  |  |  |  | queued |  |  |  |  |  |  |\n"
    )


def test_the_daily_snapshot_holds_the_whole_table(kitchen):
    twenty(kitchen)
    kitchen.poll(QUARTER_PAST_FIVE)
    whole = table(kitchen)
    (event,) = kitchen.events("snapshot")
    assert event["line"] == "snapshot demo: 2026-10-12"
    assert whole.count("| row-") == 20 and event["text"].startswith(whole)


def test_an_approved_row_is_launched_as_the_home_launches_a_crewmate(kitchen, jstack_config):
    (jstack_config.parent / "roles").write_text("crew: codex a-model a-provider\n")
    add(kitchen, "alpha")
    said = kitchen.poll()
    (given,) = kitchen.t3.launches
    written = queue.body(brief("alpha"))
    assert given == {
        "projectId": PROJECT,
        "title": "crew: alpha",
        "workspaceStrategy": {
            "type": "worktree",
            "baseRef": "main",
            "branch": "alpha",
            "startFromOrigin": True,
        },
        "message": f"/crew alpha\n\n{written}",
        "runtimeMode": "full-access",
        "modelSelection": {"provider": "codex", "model": "a-model", "instanceId": "a-provider"},
    }
    schema = tools.strict(tools.SCHEMAS["t3_thread_launch"])
    assert [error.message for error in Draft202012Validator(schema).iter_errors(given)] == []
    assert (kitchen.home / "tasks/alpha.md").read_text() == written + "Thread: mcp:thread-1\n"
    assert "launched alpha: mcp:thread-1" in said
    sha = rows(kitchen)["alpha"]["brief_sha"]
    record = json.loads(
        (kitchen.state_dir / "launches/demo/alpha" / f"{sha[:12]}.json").read_text()
    )
    assert (record["key"], record["state"], record["thread"]) == (
        f"demo/alpha/{sha[:12]}",
        "launched",
        "mcp:thread-1",
    )
    assert (rows(kitchen)["alpha"]["status"], rows(kitchen)["alpha"]["thread"]) == (
        "launched",
        "mcp:thread-1",
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.t3.launches) == 1


def test_the_approved_brief_already_on_disk_is_launched_and_only_gains_its_thread_line(kitchen):
    add(kitchen, "alpha")
    (kitchen.home / "tasks/alpha.md").write_text(brief("alpha") + "\n")
    kitchen.poll()
    assert len(kitchen.t3.launches) == 1
    assert (kitchen.home / "tasks/alpha.md").read_text() == (
        brief("alpha") + "\nThread: mcp:thread-1\n"
    )


def test_a_brief_on_disk_that_is_not_the_approved_one_is_a_gate_and_is_left_alone(kitchen):
    """The crewmate reads the file, so a launch on another text would run what nobody approved."""
    add(kitchen, "alpha")
    (kitchen.home / "tasks/alpha.md").write_text("# alpha: as a home wrote it\n")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert gates(kitchen) == ["condition alpha: tasks/alpha.md differs from the approved brief"]
    assert kitchen.t3.launches == []
    assert (kitchen.home / "tasks/alpha.md").read_text() == "# alpha: as a home wrote it\n"


def test_a_hold_that_lands_while_a_pass_runs_stops_the_launch(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.on_list = lambda: queue.hold(kitchen.state, "alpha")
    said = kitchen.poll()
    assert "wait alpha: its row changed during the pass" in said
    assert kitchen.t3.launches == [] and gates(kitchen) == []
    assert rows(kitchen)["alpha"]["why"] == "not approved"
    assert not (kitchen.home / "tasks/alpha.md").exists()


def test_a_brief_changed_again_after_a_second_go_is_a_gate_again(kitchen):
    add(kitchen, "alpha")
    for line in ("One.", "Two."):
        add(kitchen, "alpha", approve=False, text=widened("alpha", line))
        kitchen.poll()
        kitchen.main("queue", "hold", "alpha")
        go(kitchen, "alpha")
        kitchen.config(dispatch=False)
        kitchen.poll(NOW + timedelta(minutes=3))
        kitchen.config()
    assert gates(kitchen) == ["condition alpha: brief changed after approval"] * 2


def test_an_approved_row_whose_slug_has_a_settled_thread_is_a_gate(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "failed", settled=True)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert gates(kitchen) == ["condition alpha: a settled thread already has this slug"]
    assert kitchen.t3.launches == [] and rows(kitchen)["alpha"]["status"] == "gate"


def test_a_server_error_on_a_launch_keeps_the_intent_and_is_looked_up(kitchen):
    """After a 5xx, nobody knows whether T3 Code made the thread, so jbus calls nothing again."""
    add(kitchen, "alpha")
    kitchen.t3.status = 503
    kitchen.poll()
    kitchen.t3.status = 200
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert gates(kitchen) == ["condition alpha: launch reply lost, 0 matching threads"]
    assert len(kitchen.t3.launches) == 1


def test_a_row_with_no_approval_is_never_launched(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta")
    assert kitchen.main("queue", "hold", "beta")[0] == 0
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert kitchen.t3.launches == [] and kitchen.lines() == []


def test_a_brief_changed_after_the_go_is_a_gate_until_it_is_approved_again(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "alpha", approve=False, text=widened("alpha"))
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert gates(kitchen) == ["condition alpha: brief changed after approval"]
    assert kitchen.t3.launches == [] and rows(kitchen)["alpha"]["status"] == "gate"
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll(NOW + timedelta(minutes=6))
    assert "One more line." in kitchen.t3.launches[0]["message"]


def test_a_row_waits_silently_until_everything_it_depends_on_is_merged(kitchen):
    add(kitchen, "beta", depends="alpha")
    kitchen.brief("alpha", RESULT)
    kitchen.poll()
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.t3.launches == [] and kitchen.lines() == []
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: beta"]


def test_a_dependency_merged_into_an_integration_branch_counts_as_merged(kitchen):
    """A train merges into its integration branch, not main. GitHub lists that merge with every
    other merge, and jbus launches the row that depends on it as it does after any merge."""
    add(kitchen, "beta", depends="alpha")
    kitchen.brief("alpha", RESULT)
    into_train = {**kitchen.merged("alpha", 7, "a" * 40), "baseRefName": "migration"}
    kitchen.set("merged.json", [into_train])
    kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: beta"]
    listed = [line for line in kitchen.log("gh") if "--state merged" in line]
    assert listed and not [line for line in listed if "--base" in line]


def test_a_row_whose_files_a_brief_still_out_names_is_launched_all_the_same(kitchen):
    add(kitchen, "alpha")
    kitchen.set(
        "claims.txt",
        "alpha not launched root Where: `src/alpha/`\n"
        "other running root Where: `docs/`, `src/alpha/one.py` (a fix)\n",
    )
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert gates(kitchen) == [] and "--claims" in kitchen.log("jmerge")
    assert len(kitchen.t3.launches) == 1


def test_a_claims_check_that_did_not_run_stops_no_launch_and_is_no_gate(kitchen):
    add(kitchen, "alpha")
    (kitchen.stub / "claims-fail").touch()
    said = kitchen.poll()
    assert [line for line in said if "jmerge --claims" in line] == []
    assert len(kitchen.t3.launches) == 1 and gates(kitchen) == []


def test_a_dependency_merged_long_ago_is_asked_for_by_name_and_stays_merged(kitchen):
    """The merged list is a window of a hundred pull requests, so jbus does not take a slug
    outside the window as unmerged."""
    add(kitchen, "alpha", approve=False)
    add(kitchen, "gamma", depends="alpha,beta")
    old = [
        {**kitchen.merged(slug, n, "a" * 40), "old": True}
        for slug, n in (("alpha", 7), ("beta", 8))
    ]
    kitchen.set("merged.json", old)
    kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: gamma"]
    assert (rows(kitchen)["alpha"]["status"], rows(kitchen)["alpha"]["pr"]) == ("merged", "#7")
    kitchen.poll(NOW + timedelta(minutes=3))
    asked = [line.split("--head ")[1].split()[0] for line in kitchen.log("gh") if "--head" in line]
    assert sorted(asked) == ["alpha", "beta", "gamma", "gamma"]
    assert rows(kitchen)["alpha"]["status"] == "merged"


def test_a_launch_t3_code_refuses_is_a_gate_in_its_words_and_holds_no_other_row(kitchen):
    add(kitchen, "alpha", priority=1)
    add(kitchen, "beta", priority=2)
    kitchen.t3.refuse = "capability_denied: approved for read-only access"
    kitchen.poll()
    gate, other = kitchen.events("condition")
    assert other["line"] == "condition beta: T3 Code refused the launch"
    assert gate["line"] == "condition alpha: T3 Code refused the launch"
    assert gate["text"] == "t3_thread_launch: capability_denied: approved for read-only access"
    assert list((kitchen.state_dir / "launches/demo/alpha").glob("*.json")) == []
    assert not (kitchen.home / "tasks/alpha.md").exists()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]
    kitchen.t3.refuse = ""
    kitchen.t3.threads.clear()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.t3.launches[-1]["title"] == "crew: alpha" and len(gates(kitchen)) == 2


def test_a_reply_that_stays_lost_holds_its_own_slug_and_no_other_row(kitchen):
    add(kitchen, "alpha", priority=1)
    kitchen.t3.lose = "before"
    kitchen.poll()
    kitchen.t3.lose = None
    add(kitchen, "beta", priority=2)
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert gates(kitchen) == ["condition alpha: launch reply lost, 0 matching threads"]
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]


@pytest.mark.parametrize("off", ["config", "stop", "max_running"])
def test_dispatch_off_a_stop_file_or_the_limit_reached_launch_nothing(kitchen, off):
    add(kitchen, "alpha")
    if off == "config":
        kitchen.config(dispatch=False)
    elif off == "stop":
        kitchen.state_dir.mkdir(exist_ok=True)
        (kitchen.state_dir / "stop").touch()
    else:
        kitchen.brief("other")
        kitchen.t3.thread("other", "running")
    kitchen.poll()
    assert kitchen.t3.launches == [] and gates(kitchen) == []
    assert rows(kitchen)["alpha"]["status"] == "queued"
    kitchen.config(max_running=2)
    (kitchen.state_dir / "stop").unlink(missing_ok=True)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.t3.launches) == 1


@pytest.mark.parametrize(("written", "cap"), [(None, 12), (3, 3), (1, 1)])
def test_a_config_with_no_max_running_runs_the_crew_cap_the_machine_derives(
    kitchen, monkeypatch, tmp_path, written, cap
):
    """On a machine with 12 processors and 32 GiB, `jgauge.sizes` derives `max_running` as one
    crew for each processor."""
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 12, 32)))
    kitchen.config(max_running=written)
    assert jbus.load(kitchen.config_dir).max_running == cap


@pytest.mark.parametrize("written", [0, -2])
def test_a_max_running_under_1_is_refused_with_one_line(kitchen, written):
    kitchen.config(max_running=written)
    with pytest.raises(jbus.Refused) as refused:
        jbus.load(kitchen.config_dir)
    path = kitchen.config_dir / "config.toml"
    assert str(refused.value) == (
        f"refused: max_running in {path} is {written}, and the number of max_running is 1 or more"
    )


def test_a_pass_with_no_max_running_launches_every_row_that_shares_no_file(kitchen):
    kitchen.config(max_running=None)
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug)
    said = kitchen.poll()
    assert sorted(given["title"] for given in kitchen.t3.launches) == [
        "crew: alpha",
        "crew: beta",
        "crew: gamma",
    ]
    assert not any(line.startswith("max_running is") for line in said)


def test_each_row_the_cap_holds_is_said_with_when_it_began_to_wait(kitchen):
    kitchen.config(max_running=1)
    for priority, slug in enumerate(("first", "second", "third"), start=1):
        add(kitchen, slug, priority=priority)
    said = kitchen.poll()
    assert [line for line in said if line.startswith("max_running is")] == [
        f"max_running is 1 across all projects: second waits, {SINCE}",
        f"max_running is 1 across all projects: third waits, {SINCE}",
    ]
    later = NOW + timedelta(minutes=3)
    said = kitchen.poll(later)
    assert [line for line in said if line.startswith("max_running is")] == [
        f"max_running is 1 across all projects: second waits, {SINCE}",
        f"max_running is 1 across all projects: third waits, {SINCE}",
    ]


def test_rows_launch_lowest_priority_first_and_one_at_a_time(kitchen):
    add(kitchen, "later", priority=5)
    add(kitchen, "sooner", priority=2)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: sooner"]


def test_two_passes_at_once_launch_one_thread(kitchen):
    add(kitchen, "alpha")
    kitchen.set("jmerge-sleep", "0.3")
    passes = [threading.Thread(target=kitchen.poll) for _ in range(2)]
    for one in passes:
        one.start()
    for one in passes:
        one.join()
    kitchen.set("jmerge-sleep", "0")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.t3.launches) == 1


def test_a_reply_lost_after_the_thread_was_made_adopts_that_thread(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.lose = "after"
    said = kitchen.poll()
    sha = rows(kitchen)["alpha"]["brief_sha"][:12]
    record = kitchen.state_dir / "launches/demo/alpha" / f"{sha}.json"
    assert json.loads(record.read_text())["state"] == "intent"
    assert any(line.startswith("launch alpha: no reply") for line in said)
    kitchen.t3.lose = None
    assert "adopted alpha: mcp:thread-1" in kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert json.loads(record.read_text())["thread"] == "mcp:thread-1"
    assert ("t3_thread_read", {"threadId": "mcp:thread-1", "limit": 1}) in kitchen.t3.calls
    assert len(kitchen.t3.launches) == 1 and gates(kitchen) == []
    assert rows(kitchen)["alpha"]["thread"] == "mcp:thread-1"


@pytest.mark.parametrize("others, count", [(0, 0), (1, 2)])
def test_a_lost_reply_with_no_thread_or_several_is_a_gate_and_no_retry(kitchen, others, count):
    add(kitchen, "alpha")
    kitchen.t3.lose = "after" if others else "before"
    kitchen.poll()
    for _ in range(others):
        kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.t3.thread("alpha-two", "running", settled=True)
    kitchen.t3.lose = None
    for minutes in (3, 6, 9):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert gates(kitchen)[0] == f"condition alpha: launch reply lost, {count} matching threads"
    assert len(kitchen.t3.launches) == 1
    assert rows(kitchen)["alpha"]["status"] == "gate"


@pytest.mark.parametrize("ref", ["refs/heads/alpha", "refs/remotes/origin/alpha"])
def test_a_branch_already_there_with_no_launch_record_is_a_gate(kitchen, ref):
    add(kitchen, "alpha")
    kitchen.git("update-ref", ref, "HEAD")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert gates(kitchen) == ["condition alpha: branch alpha is there with no launch record"]
    assert kitchen.t3.launches == []
    assert not (kitchen.home / "tasks/alpha.md").exists()


def test_a_branch_pushed_since_the_last_fetch_is_a_gate(kitchen):
    """jbus asks the remote, not the copy of its branches that the main checkout last fetched."""
    add(kitchen, "alpha")
    kitchen.git("push", "-q", "origin", "HEAD:refs/heads/alpha")
    kitchen.git("update-ref", "-d", "refs/remotes/origin/alpha")
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: branch alpha is there with no launch record"]
    assert kitchen.t3.launches == []


def test_a_remote_that_cannot_be_asked_is_a_gate(kitchen):
    add(kitchen, "alpha")
    kitchen.git("remote", "set-url", "origin", str(kitchen.root / "gone.git"))
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: the remote could not be asked for a branch alpha"]
    assert kitchen.t3.launches == []


def test_a_key_with_a_thread_is_never_launched_again(kitchen):
    add(kitchen, "alpha")
    kitchen.poll()
    kitchen.t3.threads.clear()
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert len(kitchen.t3.launches) == 1
    assert (rows(kitchen)["alpha"]["status"], rows(kitchen)["alpha"]["thread"]) == (
        "launched",
        "mcp:thread-1",
    )


def reasons(kitchen, now=NOW):
    """Run one pass, and return what it recorded on `Pass.reasons`."""
    seen, second_half = {}, cli.second_half

    def kept(half, client):
        second_half(half, client)
        seen.update(half.run.reasons)

    kitchen.monkeypatch.setattr(cli, "second_half", kept)
    kitchen.poll(now)
    kitchen.monkeypatch.setattr(cli, "second_half", second_half)
    return seen


def test_a_row_that_is_launched_has_no_reason_and_one_never_approved_has_none(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert reasons(kitchen) == {}
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]


def test_a_changed_brief_is_recorded_with_the_sha_it_has_now(kitchen):
    add(kitchen, "alpha")
    changed = widened("alpha")
    add(kitchen, "alpha", approve=False, text=changed)
    assert reasons(kitchen) == {"alpha": wake.Changed(sha12(changed))}


def test_a_row_that_depends_is_recorded_with_the_slugs_that_are_not_merged(kitchen):
    add(kitchen, "delta", depends="alpha,beta,gamma")
    kitchen.brief("alpha", RESULT)
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    assert reasons(kitchen) == {"delta": wake.Depends(("beta", "gamma"))}


def test_the_row_the_limit_stops_and_every_row_after_it_wait_for_a_slot(kitchen):
    kitchen.brief("other")
    kitchen.t3.thread("other", "running")
    add(kitchen, "alpha", priority=1)
    add(kitchen, "beta", priority=2)
    add(kitchen, "gamma", priority=3, approve=False)
    assert reasons(kitchen) == {"alpha": wake.Slot(), "beta": wake.Slot()}


def test_a_row_with_no_room_and_every_row_after_it_wait_for_a_slot(kitchen):
    kitchen.config(max_running=5)
    add(kitchen, "alpha", priority=1)
    add(kitchen, "beta", priority=2)
    kitchen.machine(load="30.00")
    assert reasons(kitchen) == {"alpha": wake.Slot(), "beta": wake.Slot()}
    assert kitchen.t3.launches == []


def test_any_other_gate_has_no_reason_but_the_gate_and_holds_no_other_row(kitchen):
    kitchen.config(max_running=5)
    add(kitchen, "alpha", priority=1)
    add(kitchen, "beta", priority=2)
    kitchen.t3.thread("alpha", "failed", settled=True)
    assert reasons(kitchen) == {}
    assert (rows(kitchen)["alpha"]["status"], rows(kitchen)["alpha"]["why"]) == (
        "gate",
        "a gate the Chef has",
    )
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: beta"]


def two(kitchen, a=0, b=0, **top):
    """Add a second project, and approve `a` rows and `b` rows in the two projects: a1, a2, and
    b1, b2."""
    other = kitchen.second()
    kitchen.config(**top)
    for project, letter, count in (("demo", "a", a), ("other", "b", b)):
        for place in range(1, count + 1):
            add(kitchen, f"{letter}{place}", priority=place, project=project)
    return other


def launches(kitchen):
    return [given["title"].removeprefix("crew: ") for given in kitchen.t3.launches]


def sent(other, kind="condition"):
    """Return the lines of the second project's events of a kind, as its log has them."""
    every = wake.Box(other.state, jbus.load().project(other.name)).log()
    return [event["line"] for event in every if event["event"] == kind]


def rotation(kitchen):
    return kitchen.state_dir / "rotation.json"


def test_crews_out_in_one_project_fill_the_cap_for_every_project(kitchen):
    other = two(kitchen, b=1, max_running=8)
    for place in range(8):
        kitchen.t3.thread(f"out{place}", "running")
    said = kitchen.poll()
    assert kitchen.t3.launches == []
    assert f"max_running is 8 across all projects: b1 waits, {SINCE}" in said
    assert gates(kitchen) == [] and sent(other) == []
    assert not rotation(kitchen).exists()


def test_the_free_slots_are_what_every_project_together_leaves(kitchen):
    other = two(kitchen, a=2, b=2, max_running=3)
    kitchen.t3.thread("out-a", "running")
    kitchen.t3.thread("out-b", "waiting", project=other.project)
    kitchen.poll()
    assert launches(kitchen) == ["a1"]


def test_the_projects_take_turns_and_a_turn_launches_one_row(kitchen):
    other = two(kitchen, a=4, b=4, max_running=4)
    kitchen.poll()
    assert launches(kitchen) == ["a1", "b1", "a2", "b2"]
    assert [given["projectId"] for given in kitchen.t3.launches] == [PROJECT, other.project] * 2
    assert (other.home / "tasks/b2.md").exists() and not (other.home / "tasks/b3.md").exists()


def test_a_project_with_nothing_ready_leaves_its_turns_to_the_other(kitchen):
    two(kitchen, b=4, max_running=4)
    add(kitchen, "a1", approve=False)
    kitchen.poll()
    assert launches(kitchen) == ["b1", "b2", "b3", "b4"]


def test_a_project_whose_only_row_is_gated_sends_the_gate_once_and_leaves_its_turns(kitchen):
    two(kitchen, a=1, b=4, max_running=4)
    kitchen.t3.thread("a1", "failed", settled=True)
    kitchen.poll()
    assert launches(kitchen) == ["b1", "b2", "b3", "b4"]
    assert gates(kitchen) == ["condition a1: a settled thread already has this slug"]


def test_the_turn_order_is_kept_from_one_pass_to_the_next(kitchen):
    two(kitchen, a=2, b=1, max_running=1)
    for minutes, launched, then in ((0, "a1", "other"), (3, "b1", "demo"), (6, "a2", "other")):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert launches(kitchen)[-1] == launched
        assert json.loads(rotation(kitchen).read_text()) == {"next": then}
        kitchen.t3.threads[-1]["status"] = "completed"
    assert launches(kitchen) == ["a1", "b1", "a2"]


@pytest.mark.parametrize(
    "written, first",
    [
        (None, "a1"),
        ("not json", "a1"),
        ("[]", "a1"),
        ('{"next": "gone"}', "a1"),
        ('{"next": "other"}', "b1"),
    ],
)
def test_a_rotation_file_that_names_no_project_starts_at_the_first(kitchen, written, first):
    two(kitchen, a=1, b=1, max_running=1)
    if written is not None:
        kitchen.state_dir.mkdir(exist_ok=True)
        rotation(kitchen).write_text(written)
    kitchen.poll()
    assert launches(kitchen) == [first]


def test_a_t3_code_that_does_not_answer_for_one_project_launches_nothing_in_any(kitchen):
    other = two(kitchen, a=1, b=1, max_running=4)
    kitchen.t3.down.add(other.project)
    said = kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.t3.launches == []
    why = "T3 Code at /mcp could not be reached: Remote end closed connection without response"
    assert [line for line in said if line.startswith("wait: ")] == [
        f"wait: crews out not known (other: {why})"
    ]
    assert sent(other) == ["condition other: T3 Code could not be asked"] and gates(kitchen) == []
    kitchen.t3.down.clear()
    kitchen.poll(NOW + timedelta(minutes=6))
    assert launches(kitchen) == ["a1", "b1"]


def test_a_project_whose_github_does_not_answer_still_counts_its_crews(kitchen):
    other = two(kitchen, a=3, b=1, max_running=3)
    for slug in ("out1", "out2"):
        kitchen.t3.thread(slug, "running", project=other.project)
    (kitchen.stub / "gh-down-other").touch()
    said = kitchen.poll()
    assert launches(kitchen) == ["a1"]
    assert "wait other: could not ask GitHub: gh exited 1: it said nothing" in said
    assert f"max_running is 3 across all projects: a2 waits, {SINCE}" in said


def test_no_room_on_the_machine_ends_the_turns_for_every_project(kitchen):
    other = two(kitchen, a=1, b=1, max_running=4)
    kitchen.machine(load="30.00")
    said = kitchen.poll()
    assert kitchen.t3.launches == []
    assert [line.partition(": ")[0] for line in said if "no room" in line] == ["wait a1"]
    assert json.loads((kitchen.state / "room.json").read_text())["passes"] == 1
    assert not (other.state / "room.json").exists()
    kitchen.machine()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert launches(kitchen) == ["a1", "b1"]


@pytest.mark.parametrize("stop", ["cap", "room", "t3"])
def test_a_row_ahead_of_the_first_that_waits_for_a_slot_is_gated_with_no_slot_free(kitchen, stop):
    other = two(kitchen, a=1, max_running=1 if stop == "cap" else 4)
    add(kitchen, "settled", priority=1, project="other")
    add(kitchen, "ready", priority=2, project="other")
    add(kitchen, "later", priority=3, project="other")
    kitchen.t3.thread("settled", "failed", settled=True, project=other.project)
    kitchen.t3.thread("later", "failed", settled=True, project=other.project)
    if stop == "cap":
        kitchen.t3.thread("out", "running")
    elif stop == "room":
        kitchen.machine(load="30.00")
    else:
        kitchen.t3.down.add(PROJECT)
    said = kitchen.poll()
    assert kitchen.t3.launches == []
    assert sent(other) == ["condition settled: a settled thread already has this slug"]
    assert (f"max_running is 1 across all projects: ready waits, {SINCE}" in said) == (
        stop == "cap"
    )


@pytest.mark.parametrize("off", ["config", "stop"])
def test_dispatch_off_sends_no_gate_whether_or_not_the_crews_out_are_known(kitchen, off):
    other = two(kitchen, a=1, dispatch=off != "config")
    if off == "stop":
        kitchen.state_dir.mkdir(exist_ok=True)
        (kitchen.state_dir / "stop").touch()
    kitchen.t3.thread("a1", "failed", settled=True)
    jbus.write_json(kitchen.state / "room.json", {"slug": "a1", "passes": 3, "since": "then"})
    kitchen.t3.down.add(other.project)
    said = kitchen.poll()
    assert gates(kitchen) == [] and kitchen.t3.launches == []
    assert any(line.endswith("nothing is launched") for line in said)
    assert not (kitchen.state / "room.json").exists()


def readdressed(slug, home="mcp:another-home", thread=""):
    """Return the brief as a new home queues it again, with another `Home:` line and a `Thread:`
    line added."""
    text = brief(slug).replace("Home: mcp:a-home\n", f"Home: {home}\n")
    return text.replace("Where:", f"Thread: {thread}\nWhere:") if thread else text


@pytest.mark.parametrize(
    "again",
    [
        readdressed("alpha"),
        readdressed("alpha", home="mcp:a-home", thread="mcp:a-thread"),
        readdressed("alpha", thread="mcp:a-thread"),
    ],
    ids=["home", "thread", "both"],
)
def test_a_brief_queued_again_with_another_home_or_thread_line_is_still_approved(kitchen, again):
    """A new home rewrites `Home:` in every brief it takes over, and that does not make another
    brief."""
    add(kitchen, "alpha")
    approved = rows(kitchen)["alpha"]["brief_sha"]
    add(kitchen, "alpha", approve=False, text=again)
    assert (kitchen.state / "briefs/alpha.md").read_text() == again
    assert rows(kitchen)["alpha"]["brief_sha"] == approved
    said = kitchen.poll()
    assert gates(kitchen) == []
    assert "launched alpha: mcp:thread-1" in said and len(kitchen.t3.launches) == 1


def test_a_thread_line_changed_in_the_head_leaves_the_approval_standing(kitchen):
    add(kitchen, "alpha", text=readdressed("alpha", thread="mcp:a-thread"))
    add(kitchen, "alpha", approve=False, text=readdressed("alpha", thread="mcp:another-thread"))
    kitchen.poll()
    assert gates(kitchen) == [] and len(kitchen.t3.launches) == 1


@pytest.mark.parametrize(
    "again",
    [
        brief("alpha").replace("a new test", "another test"),
        widened("alpha"),
        brief("alpha").replace("Size: S", "Size: L"),
        brief("alpha").replace('Task: "do alpha"', 'Task: "do alpha twice"'),
    ],
    ids=["where", "done when", "size", "task"],
)
def test_a_change_to_the_goal_or_the_scope_still_voids_the_approval(kitchen, again):
    add(kitchen, "alpha")
    add(kitchen, "alpha", approve=False, text=again)
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: brief changed after approval"]
    assert kitchen.t3.launches == []


def test_a_row_approved_by_the_sha_of_the_whole_text_is_approved_while_the_text_is_the_same(
    kitchen,
):
    """The sha once covered every line of the brief, the `Home:` and `Thread:` lines included. A
    row that the user approved in that time holds the sha of the whole text."""
    kitchen.config(max_running=6)
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug)
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        row["brief_sha"] = hashlib.sha256(brief(row["slug"]).encode()).hexdigest()
        for column in ("brief_sha", "scope", "meaning"):
            row["approval"].pop(column)
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    add(kitchen, "beta", approve=False, text=readdressed("beta"))
    assert rows(kitchen)["beta"]["brief_sha"] == queue.brief_sha(brief("beta"))
    add(kitchen, "gamma", approve=False, text=readdressed("gamma") + "One more line.\n")
    kitchen.poll()
    assert sorted(given["title"] for given in kitchen.t3.launches) == ["crew: alpha", "crew: beta"]
    assert gates(kitchen) == ["condition gamma: brief changed after approval"]


def test_a_launch_sends_no_line_the_approved_sha_leaves_out(kitchen):
    """jbus does not hash what follows `Home:` or `Thread:`, so jbus neither sends nor writes
    that text."""
    add(kitchen, "alpha")
    unsaid = readdressed("alpha", home="mcp:a-home and more", thread="mcp:a-thread and also this")
    add(kitchen, "alpha", approve=False, text=unsaid)
    kitchen.poll()
    (given,) = kitchen.t3.launches
    written = queue.body(brief("alpha"))
    assert given["message"] == f"/crew alpha\n\n{written}"
    assert (kitchen.home / "tasks/alpha.md").read_text() == written + "Thread: mcp:thread-1\n"


def test_a_brief_on_disk_with_another_thread_line_is_launched_and_gets_the_launchs_line(kitchen):
    add(kitchen, "alpha", text=readdressed("alpha", thread="mcp:a-thread"))
    on_disk = readdressed("alpha", thread="mcp:an-earlier-launch")
    (kitchen.home / "tasks/alpha.md").write_text(on_disk)
    kitchen.poll()
    assert gates(kitchen) == [] and len(kitchen.t3.launches) == 1
    assert (kitchen.home / "tasks/alpha.md").read_text() == on_disk.replace(
        "mcp:an-earlier-launch", "mcp:thread-1"
    )


def test_the_sha_a_brief_is_approved_by_is_the_one_add_prints_and_every_list_shows(kitchen):
    """One function says which lines count, so jbus never refuses the command that a list prints."""
    text = readdressed("alpha", thread="mcp:a-thread")
    shown = queue.brief_sha(brief("alpha"))[:12]
    added = f"add alpha --priority 1\n--- brief alpha\n{text}--- end\n"
    assert kitchen.main("queue", "apply", stdin=added) == (
        0,
        f"added alpha: priority 1, brief {shown}\n",
    )
    kitchen.poll()
    listed = json.loads((kitchen.state / "waiting-on-user.json").read_text())
    assert [one["line"].partition(" --sha ")[2].split()[0] for one in listed] == [shown]
    whole = hashlib.sha256(text.encode()).hexdigest()[:12]
    assert go(kitchen, "alpha", whole) == (1, f"refused: alpha's brief is {shown}, not {whole}\n")
    assert go(kitchen, "alpha", shown)[0] == 0
    assert rows(kitchen)["alpha"]["brief_sha"] == queue.brief_sha(text)
    assert queue.approved_text(rows(kitchen)["alpha"], brief("alpha"))
    assert not queue.approved_text(rows(kitchen)["alpha"], widened("alpha", "More."))
    assert queue.approved_text(rows(kitchen)["alpha"], brief("alpha", "More.\n"))


def test_merge_after_is_written_by_add_shown_and_set_anew_by_the_next_add(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "gamma", approve=False)
    argv = ["queue", "add", "beta", "--priority", "2", "--merge-after", "alpha,gamma"]
    code, said = kitchen.main("--project", "demo", *argv, stdin=brief("beta"))
    assert code == 0
    assert rows(kitchen)["beta"]["merge_after"] == ["alpha", "gamma"]
    assert "| beta | 2 |  | alpha, gamma |" in said
    add(kitchen, "beta", approve=False)
    assert "merge_after" not in rows(kitchen)["beta"]


def test_a_batch_line_takes_merge_after(kitchen):
    add(kitchen, "alpha", approve=False)
    text = batch(adds("beta", "--priority 2 --merge-after alpha"))
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert (code, said.splitlines()[0]) == (
        0,
        f"added beta: priority 2, merges after alpha, brief {sha12(brief('beta'))}",
    )
    assert rows(kitchen)["beta"]["merge_after"] == ["alpha"]


@pytest.mark.parametrize(
    ("slug", "given", "refused"),
    [
        ("beta", "beta", "beta cannot merge after itself"),
        ("beta", "nobody", "beta cannot merge after nobody: the queue has no row nobody"),
        (
            "alpha",
            "beta",
            "alpha cannot merge after beta: beta is already behind alpha by merge_after or depends",
        ),
        (
            "gamma",
            "beta",
            "gamma cannot merge after beta: beta is already behind gamma by merge_after or depends",
        ),
    ],
)
def test_an_order_that_could_never_be_kept_is_refused_and_nothing_is_queued(
    kitchen, slug, given, refused
):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    add(kitchen, "gamma", approve=False)
    kitchen.main(
        "--project",
        "demo",
        "queue",
        "add",
        "beta",
        "--priority",
        "1",
        "--merge-after",
        "alpha",
        stdin=brief("beta"),
    )
    kitchen.main(
        "--project",
        "demo",
        "queue",
        "add",
        "alpha",
        "--priority",
        "1",
        "--depends",
        "",
        stdin=brief("alpha"),
    )
    before = stored(kitchen)
    if slug == "gamma":
        kitchen.main(
            "--project",
            "demo",
            "queue",
            "add",
            "beta",
            "--priority",
            "1",
            "--depends",
            "gamma",
            stdin=brief("beta"),
        )
        before = stored(kitchen)
    argv = ["queue", "add", slug, "--priority", "1", "--merge-after", given]
    code, said = kitchen.main("--project", "demo", *argv, stdin=brief(slug))
    assert code != 0
    assert said.startswith(f"refused: {refused}")
    assert stored(kitchen) == before


def test_a_depends_edge_that_closes_a_merge_after_chain_is_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    argv = ["queue", "add", "beta", "--priority", "2", "--merge-after", "alpha"]
    assert kitchen.main("--project", "demo", *argv, stdin=brief("beta"))[0] == 0
    before = stored(kitchen)
    argv = ["queue", "add", "alpha", "--priority", "1", "--depends", "beta"]
    code, said = kitchen.main("--project", "demo", *argv, stdin=brief("alpha"))
    assert code != 0
    assert said.startswith(
        "refused: alpha cannot depend on beta: beta is already behind alpha "
        "by merge_after or depends"
    )
    assert stored(kitchen) == before


def test_hold_marks_the_row_and_approve_lifts_the_mark(kitchen):
    add(kitchen, "alpha")
    assert "held" not in rows(kitchen)["alpha"]
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    assert rows(kitchen)["alpha"]["held"] is True
    assert go(kitchen, "alpha")[0] == 0
    assert "held" not in rows(kitchen)["alpha"]
    add(kitchen, "beta", approve=False)
    assert "held" not in rows(kitchen)["beta"]


def test_a_row_another_merges_after_is_not_removed(kitchen):
    add(kitchen, "alpha", approve=False)
    argv = ["queue", "add", "beta", "--priority", "2", "--merge-after", "alpha"]
    kitchen.main("--project", "demo", *argv, stdin=brief("beta"))
    code, said = kitchen.main(
        "queue", "remove", "alpha", "--by", "user", "--at", "2026-10-11 17:58 ET"
    )
    assert code != 0
    assert "beta wait on alpha: remove them first" in said
