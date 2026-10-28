"""A scout's request is a row of the queue: `jbus queue add` takes it when its text is a request
(a `Request:` line and no `Task:` line), checks it against the template, and keeps it as a row of
role `scout`. It is approved as any row is, the entry's go included, and waits on its `--depends`
as any row does. A pass launches it read-only, as `/scout <slug>` in the main checkout with no
branch, and the row is done once its Report says so. Like `test_jbus_kitchen.py`, the tests run
the real commands and the real pass against a faked T3 Code server, `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

from jbriefs import parse
from jbus import queue
from test_jbus_entry_go import PLAN, plan_go
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, go, rows


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def request(slug, more="", asked="find out what X does", title="what X does"):
    """Return a request in the shape of `features/scout/templates/scout-request.md`."""
    return (
        f"# {slug}: {title}\n"
        f'Request: "{asked}"\n'
        "Questions:\n"
        "- What calls X? Start at `src/x.py`.\n"
        "Deliver:\n"
        '- Under "## Report" in this file: the findings with their evidence.\n'
        "Playbook: none\n"
        "Out of bounds: read-only. Run nothing that writes.\n"
        f"{more}"
    )


def add(kitchen, slug, *flags, text=None):
    argv = ["queue", "add", slug, "--priority", "1", *flags]
    return kitchen.main(*argv, stdin=request(slug) if text is None else text)


def launches(kitchen):
    return [one for one in kitchen.t3.launches if one["title"].startswith("scout: ")]


def scout_thread(kitchen, slug):
    (thread,) = [t for t in kitchen.t3.threads if t["title"] == f"scout: {slug}"]
    return thread


def reported(kitchen, slug, status="done"):
    path = kitchen.home / "scouts" / f"{slug}.md"
    path.write_text(path.read_text() + f"\n## Report\nStatus: {status}\nFindings: X calls Y.\n")


def test_a_request_is_queued_as_a_scout_row_and_waits_for_a_go(kitchen):
    code, said = add(kitchen, "alpha")

    assert code == 0, said
    (row,) = queue.load(kitchen.state)
    assert (row["slug"], row["role"], row["approved"]) == ("alpha", queue.SCOUT, "")
    assert queue.brief(kitchen.state, "alpha") == request("alpha")
    assert "| alpha | 1 |" in said and "| scout |" in said
    kitchen.poll()
    assert launches(kitchen) == []
    assert not list(kitchen.state.glob("scouts.*"))


def test_a_crew_brief_is_still_a_crew_row(kitchen):
    assert kitchen.main("queue", "add", "beta", "--priority", "1", stdin=brief("beta"))[0] == 0

    (row,) = queue.load(kitchen.state)
    assert queue.role(row) == "crew"


@pytest.mark.parametrize("line", ["Size: S", "Pull request: open one"])
def test_a_request_with_a_crewmates_line_is_refused_and_names_the_line(kitchen, line):
    label = line.split(":")[0]

    code, said = add(kitchen, "alpha", text=request("alpha", f"{line}\n"))

    assert code == 1
    assert f"- a {label}: line, which only a crewmate's brief has" in said
    assert said.startswith("refused: alpha's request has 1 fault, and nothing is queued")
    assert queue.load(kitchen.state) == []


def test_a_request_with_a_task_line_is_a_brief_and_is_refused_as_one(kitchen):
    code, said = add(kitchen, "alpha", text=request("alpha", 'Task: "do alpha"\n'))

    assert code == 1
    assert said.startswith("refused: alpha's brief has")
    assert queue.load(kitchen.state) == []


@pytest.mark.parametrize(
    "broken, fault",
    [
        (
            request("alpha").replace("Questions:\n- What calls X? Start at `src/x.py`.\n", ""),
            "no Questions: line",
        ),
        (
            request("alpha").replace(
                "Questions:\n- What",
                "Questions:\n- <a question the report must answer, with where to start looking>"
                "\n- What",
            ),
            "Questions: line is the template's own text",
        ),
        (
            request("alpha").replace("read-only. Run", "Run"),
            "Out of bounds: line does not start read-only",
        ),
        (
            request("alpha").replace("# alpha:", "# beta:"),
            "first line is not # alpha: <what to find out>",
        ),
    ],
)
def test_a_request_not_in_the_templates_shape_is_refused(kitchen, broken, fault):
    code, said = add(kitchen, "alpha", text=broken)

    assert code == 1
    assert f"- {fault}" in said
    assert queue.load(kitchen.state) == []


def test_angle_brackets_that_are_not_the_templates_own_text_are_taken(kitchen):
    asked = "find out why a < b and c > d fails in Map<String, Int> handling"

    assert add(kitchen, "alpha", text=request("alpha", asked=asked))[0] == 0


def test_a_request_line_over_the_limit_is_refused(kitchen):
    asked = "x" * (parse.LONGEST + 1)

    code, said = add(kitchen, "alpha", text=request("alpha", asked=asked))

    assert code == 1
    longest = f"over the {parse.LONGEST} it may have"
    assert f"- Request: line is {parse.LONGEST + 3} characters, {longest}" in said
    assert add(kitchen, "alpha", text=request("alpha", asked="x" * (parse.LONGEST - 2)))[0] == 0


def test_a_task_line_over_the_limit_is_refused_by_queue_add_too(kitchen):
    long = brief("alpha").replace('"do alpha"', "y" * (parse.LONGEST + 1))

    code, said = kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=long)

    assert code == 1
    assert f"brief's Task: line is {parse.LONGEST + 1} characters" in said
    assert queue.load(kitchen.state) == []


def test_a_row_keeps_its_role_when_it_is_added_again(kitchen):
    add(kitchen, "alpha")

    code, said = kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=brief("alpha"))

    assert code == 1
    assert said.startswith("refused: alpha is a scout's row, and its brief is a crewmate's")


def test_a_pass_launches_an_approved_scout_read_only_with_no_branch(kitchen):
    add(kitchen, "alpha")
    assert add(kitchen, "beta", text=request("beta", asked="find out what Y does"))[0] == 0
    assert go(kitchen, "alpha")[0] == 0

    said = kitchen.poll()

    (made,) = launches(kitchen)
    assert made["title"] == "scout: alpha"
    assert made["workspaceStrategy"] == {"type": "root"}
    assert made["message"] == "/scout alpha"
    thread = scout_thread(kitchen, "alpha")
    assert thread["branch"] is None
    assert f"launched scout alpha: {thread['threadId']}" in said
    kept = (kitchen.home / "scouts" / "alpha.md").read_text()
    assert kept == request("alpha") + f"Thread: {thread['threadId']}\n"
    assert not (kitchen.home / "tasks" / "alpha.md").exists()
    assert [one["title"] for one in kitchen.t3.launches] == ["scout: alpha"]
    assert rows(kitchen)["alpha"]["status"] == "launched"
    assert rows(kitchen)["alpha"]["thread"] == thread["threadId"]
    assert rows(kitchen)["beta"]["status"] == "queued"

    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(launches(kitchen)) == 1


def test_a_scout_row_waits_on_its_depends_and_launches_on_the_first_pass_after_it_merges(kitchen):
    """The Done when of scout-row: a design pass queued with `--depends a` under an entry with a
    go launches `/scout <slug>` on the first pass after `a` merges, and not before."""
    kitchen.config(max_running=8)
    assert kitchen.main(*"queue add a --priority 1 --entry epic".split(), stdin=brief("a"))[0] == 0
    built = request("look", "Builds on: a: what it changed\n")
    assert add(kitchen, "look", "--depends", "a", "--entry", "epic", text=built)[0] == 0
    assert plan_go(kitchen)[0] == 0
    assert rows(kitchen)["look"]["approved"]

    kitchen.poll()
    assert [one["title"] for one in kitchen.t3.launches] == ["crew: a"]
    kitchen.set("open.json", [kitchen.opened("a", 10)])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert launches(kitchen) == []
    assert rows(kitchen)["look"]["why"] == "depends on a"

    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("a", 10, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    (made,) = launches(kitchen)
    assert (made["title"], made["message"]) == ("scout: look", "/scout look")
    assert made["workspaceStrategy"] == {"type": "root"}


def test_a_scout_row_is_done_on_its_report_and_a_row_that_depends_on_it_then_launches(kitchen):
    kitchen.config(max_running=8)
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    built = brief("build", "Builds on: look: its Report\n")
    argv = ["queue", "add", "build", "--priority", "1", "--depends", "look"]
    assert kitchen.main(*argv, stdin=built)[0] == 0
    assert go(kitchen, "build")[0] == 0
    kitchen.poll()
    assert [one["title"] for one in kitchen.t3.launches] == ["scout: look"]

    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["look"]["status"] == "done"
    assert "crew: build" in [one["title"] for one in kitchen.t3.launches]


def test_a_request_whose_title_changed_after_its_go_does_not_launch(kitchen):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    changed = request("alpha", title="what Y does")

    code, said = add(kitchen, "alpha", text=changed)

    assert code == 0, said
    assert "its go does not hold for it: approve it again" in said
    kitchen.poll()
    assert launches(kitchen) == []


def test_a_request_on_disk_that_differs_from_the_queued_one_does_not_launch(kitchen):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    (kitchen.home / "scouts" / "alpha.md").write_text(request("alpha", asked="something else"))

    kitchen.poll()

    assert launches(kitchen) == []
    assert rows(kitchen)["alpha"]["status"] == "queued"


def test_a_lost_launch_reply_is_adopted_and_never_launched_again(kitchen):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.t3.lose = "after"

    kitchen.poll()
    assert rows(kitchen)["alpha"]["thread"] == ""
    kitchen.t3.lose = None
    said = kitchen.poll(NOW + timedelta(minutes=3))

    assert len(launches(kitchen)) == 1
    thread = scout_thread(kitchen, "alpha")
    assert f"adopted scout alpha: {thread['threadId']}" in said
    (path,) = (kitchen.state_dir / "launches" / "demo" / "alpha").glob("*.json")
    record = json.loads(path.read_text())
    assert (record["role"], record["thread"], record["adopted"]) == (
        "scout",
        thread["threadId"],
        True,
    )
    assert rows(kitchen)["alpha"]["thread"] == thread["threadId"]


def test_the_scout_verbs_are_gone(kitchen):
    code, _ = kitchen.main("scout", "show")

    assert code == 2
