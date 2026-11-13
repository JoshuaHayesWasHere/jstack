"""A scout's request is a row of the queue: `jbus queue add` takes it when its text is a request (a
`Request:` line and no `Task:` line), checks it against the template, and keeps it as a row of
role `scout`. It is approved as any row is, the entry's go included, and waits on its `--depends`
as any row does. A pass launches it read-only, as `/scout <slug>` in a detached worktree jbus
makes, with no branch, and the row is done once its Report says so. Like `test_jbus_kitchen.py`,
the tests run the real commands and the real pass against a faked T3 Code server, `gh` and
`jmerge`."""

import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

import jroles.mirror
from crew_branches import git_said
from jbriefs import parse
from jbus import queue, restated
from jgauge import slot, waiters
from test_jbus_entry_go import PLAN, plan_go
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_queue import brief, go, rows
from test_jbus_slot_wake import Slots

AT = "2026-10-12 10:58 ET"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def request(slug, more="", asked="find out what X does", title="what X does"):
    """Return a request in the shape of `features/scout/templates/scout-request.md`, with
    `Home: uncategorized` unless `more` names a home of its own."""
    home = "" if "Home:" in more else "Home: uncategorized\n"
    return (
        f"# {slug}: {title}\n"
        f'Request: "{asked}"\n'
        "Why: a test needs a row the queue takes\n"
        "Questions:\n"
        "- What calls X? Start at `src/x.py`.\n"
        "Deliver:\n"
        '- Under "## Report" in this file: the findings with their evidence.\n'
        "Playbook: none\n"
        "Out of bounds: read-only. Run nothing that writes.\n"
        f"{home}{more}"
    )


def add(kitchen, slug, *flags, text=None):
    argv = ["queue", "add", slug, "--priority", "1", *flags]
    return kitchen.main(*argv, stdin=request(slug) if text is None else text)


def launches(kitchen):
    return [one for one in kitchen.t3.launches if one["title"].startswith("scout: ")]


def titles(kitchen):
    """The title of each launch of a row's thread, leaving out the catch-all's home that the
    pass keeps running beside them."""
    return [one["title"] for one in kitchen.t3.launches if not one["title"].startswith("home: ")]


def scout_thread(kitchen, slug):
    (thread,) = [t for t in kitchen.t3.threads if t["title"] == f"scout: {slug}"]
    return thread


def reported(kitchen, slug, status="done", heading="## Report"):
    path = kitchen.home / "scouts" / f"{slug}.md"
    path.write_text(path.read_text() + f"\n{heading}\nStatus: {status}\nFindings: X calls Y.\n")


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
    code, said = add(
        kitchen,
        "alpha",
        text=request("alpha", 'Task: "do alpha"\nWhy: a test needs a row the queue takes\n'),
    )

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
    assert made["workspaceStrategy"] == strategy(kitchen, "alpha")
    assert made["message"] == "/scout alpha"
    thread = scout_thread(kitchen, "alpha")
    assert thread["branch"] is None
    assert f"launched scout alpha: {thread['threadId']}" in said
    kept = (kitchen.home / "scouts" / "alpha.md").read_text()
    assert kept == request("alpha") + f"Thread: {thread['threadId']}\n"
    assert not (kitchen.home / "tasks" / "alpha.md").exists()
    assert titles(kitchen) == ["scout: alpha"]
    assert rows(kitchen)["alpha"]["status"] == "launched"
    assert rows(kitchen)["alpha"]["thread"] == thread["threadId"]
    assert rows(kitchen)["beta"]["status"] == "queued"

    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(launches(kitchen)) == 1


def scout_tree(kitchen, slug):
    """The scout's worktree `jbus.crewtree` makes, beside the crews' under T3 Code's home."""
    return Path(os.environ["T3CODE_HOME"]) / "worktrees" / kitchen.checkout.name / f"scout+{slug}"


def strategy(kitchen, slug):
    return {"type": "existing_worktree", "worktreePath": str(scout_tree(kitchen, slug))}


def listed_trees(kitchen):
    """Each worktree git lists, as its path and its HEAD line or `detached`."""
    listed = git_said(kitchen, "worktree", "list", "--porcelain").split("\n\n")
    return {one.splitlines()[0].removeprefix("worktree "): one.splitlines()[2:] for one in listed}


def test_a_scout_launches_into_a_detached_worktree_with_its_settings_and_loses_it_once_done(
    kitchen,
):
    """jbus makes the scout's worktree before its launch: detached at origin's main, with no
    branch, holding the scout's settings file and the `.gitignore` that keeps it out of git, and
    launches into it with `existing_worktree`. The scout still writes its Report under the home's
    state directory, and once that Report says `Status: done` and the thread is no longer at
    work, the next pass removes the worktree. A pass after that changes nothing."""
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll()

    (made,) = launches(kitchen)
    tree = scout_tree(kitchen, "alpha")
    assert made["workspaceStrategy"] == strategy(kitchen, "alpha")
    assert listed_trees(kitchen)[str(tree)] == ["detached"]
    assert git_said(kitchen, "-C", str(tree), "rev-parse", "HEAD") == git_said(
        kitchen, "rev-parse", "origin/main"
    )
    settings = jroles.mirror.worktree_settings(jroles.mirror.Main.of(Path.home()), "scout")
    assert json.loads((tree / ".claude" / "settings.json").read_text()) == settings
    assert settings["permissions"] == {"deny": ["Artifact", "AskUserQuestion"]}
    assert (tree / ".claude" / ".gitignore").read_text() == "*\n"
    assert git_said(kitchen, "-C", str(tree), "status", "--porcelain") == ""
    assert git_said(kitchen, "branch", "--list", "--format=%(refname)", "alpha") == ""

    kitchen.poll(NOW + timedelta(minutes=3))
    assert tree.is_dir() and len(launches(kitchen)) == 1

    reported(kitchen, "alpha")
    scout_thread(kitchen, "alpha")["status"] = "running"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert tree.is_dir()

    scout_thread(kitchen, "alpha")["status"] = "completed"
    scout_thread(kitchen, "alpha")["settled"] = True
    said = kitchen.poll(NOW + timedelta(minutes=9))
    assert rows(kitchen)["alpha"]["status"] == "done"
    assert not tree.exists() and str(tree) not in listed_trees(kitchen)
    assert "removed scout alpha's worktree" in said
    assert kitchen.lines("condition") == []

    said = kitchen.poll(NOW + timedelta(minutes=12))
    assert not any("removed scout" in line for line in said)
    assert len(launches(kitchen)) == 1


def test_a_scout_launch_t3_code_refuses_leaves_no_worktree(kitchen):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    kitchen.poll()
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the scout's launch"]
    assert not scout_tree(kitchen, "alpha").exists()
    assert str(scout_tree(kitchen, "alpha")) not in listed_trees(kitchen)


def tracked_settings(kitchen):
    """Commit a `.claude/settings.json` of the project's own to origin's main."""
    clone = kitchen.root / "elsewhere"
    git_said(kitchen, "clone", "-q", str(kitchen.origin), str(clone))
    (clone / ".claude").mkdir()
    (clone / ".claude" / "settings.json").write_text("{}\n")
    git_said(kitchen, "-C", str(clone), "add", "-f", ".claude/settings.json")
    git_said(kitchen, "-C", str(clone), "commit", "-q", "-m", "its own settings")
    git_said(kitchen, "-C", str(clone), "push", "-q", "origin", "main")


def gone_default(kitchen):
    git_said(kitchen, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")


def no_default(kitchen):
    git_said(kitchen, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")


@pytest.mark.parametrize(
    "breaks",
    [tracked_settings, gone_default, no_default],
    ids=["the base tracks its settings file", "origin lacks the default branch", "no default"],
)
def test_a_scout_whose_worktree_cannot_be_made_is_a_condition_and_launches_nothing(kitchen, breaks):
    """A scout's worktree that cannot be made, or would show jbus's file as a change, launches
    no scout, writes no request under `scouts/`, and leaves no worktree."""
    breaks(kitchen)
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.poll()
    assert launches(kitchen) == []
    assert kitchen.lines("condition") == ["condition alpha: the scout's worktree could not be made"]
    assert not scout_tree(kitchen, "alpha").exists()
    assert str(scout_tree(kitchen, "alpha")) not in listed_trees(kitchen)
    assert not (kitchen.home / "scouts" / "alpha.md").exists()


PRIME = "claudeAgent_claude_prime"


def test_a_scout_launches_on_the_first_instance_of_its_pool_that_can_sign_in(
    kitchen, jstack_config
):
    """`jbus.scouts` skips an instance T3 Code says is not authenticated, and launches nothing
    while no instance of the pool can sign in."""
    (jstack_config.parent / "roles").write_text(
        f"scout: claudeAgent claude-sonnet-5-5 claudeAgent,{PRIME}\n"
    )
    for instance in ("claudeAgent", PRIME):
        kitchen.t3.constraints[instance] = ["Provider is not authenticated."]
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    said = kitchen.poll()
    assert launches(kitchen) == []
    assert any("wait scout alpha: no launch: claudeAgent cannot sign in" in one for one in said)
    kitchen.t3.constraints[PRIME] = []
    kitchen.poll(NOW + timedelta(minutes=3))
    (made,) = launches(kitchen)
    assert made["modelSelection"]["instanceId"] == PRIME


FABLE = "claude-fable-5-2"


@pytest.mark.parametrize(("more", "model"), [(f"Model: {FABLE}\n", FABLE), ("", "claude-opus-5-5")])
def test_a_requests_model_line_sets_the_model_its_scout_launches_on(
    kitchen, jstack_config, more, model
):
    """A request's `Model:` line names the model its scout launches on, over the role map's
    `scout` line, which still gives the provider, the pool and the options. A request without the
    line launches on the role map's model."""
    (jstack_config.parent / "roles").write_text(
        f"scout: claudeAgent claude-opus-5-5 claudeAgent,{PRIME} effort=low\n"
    )
    assert add(kitchen, "alpha", text=request("alpha", more=more))[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll()
    (made,) = launches(kitchen)
    assert made["modelSelection"] == {
        "provider": "claudeAgent",
        "model": model,
        "instanceId": "claudeAgent",
        "options": [{"id": "effort", "value": "low"}],
    }


def test_a_requests_model_line_with_no_scout_line_in_the_role_map_launches_nothing(kitchen):
    """With no `scout` line the role map names no provider, so the model a request names has
    nothing to launch on: the pass records a condition and launches nothing."""
    assert add(kitchen, "alpha", text=request("alpha", more=f"Model: {FABLE}\n"))[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll()
    assert launches(kitchen) == []
    assert kitchen.lines("condition") == [
        "condition alpha: the request names a model and the role map has no scout line"
    ]


@pytest.mark.parametrize("line", ["Model:\n", f"Model: {FABLE} please\n"])
def test_a_requests_model_line_that_is_not_one_model_is_refused(kitchen, line):
    code, said = add(kitchen, "alpha", text=request("alpha", more=line))
    assert code == 1
    assert "Model: line is not one model id" in said


def test_a_scout_row_waits_on_its_depends_and_launches_on_the_first_pass_after_it_merges(kitchen):
    """The Done when of scout-row: a design pass queued with `--depends a` under an entry with a
    go launches `/scout <slug>` on the first pass after `a` merges, and not before."""
    kitchen.config(max_running=8)
    added = kitchen.main(
        "queue", "add", "a", "--priority", "1", "--entry", "epic", stdin=brief("a")
    )
    assert added[0] == 0
    built = request("look", "Builds on: a: what it changed\n")
    assert add(kitchen, "look", "--depends", "a", "--entry", "epic", text=built)[0] == 0
    assert plan_go(kitchen)[0] == 0
    assert rows(kitchen)["look"]["approved"]

    kitchen.poll()
    assert titles(kitchen) == ["crew: a"]
    kitchen.set("open.json", [kitchen.opened("a", 10)])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert launches(kitchen) == []
    assert rows(kitchen)["look"]["why"] == "depends on a"

    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("a", 10, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    (made,) = launches(kitchen)
    assert (made["title"], made["message"]) == ("scout: look", "/scout look")
    assert made["workspaceStrategy"] == strategy(kitchen, "look")


def test_a_scout_row_is_done_on_its_report_and_a_row_that_depends_on_it_then_launches(kitchen):
    kitchen.config(max_running=8)
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    built = brief("build", "Builds on: look: its Report\n")
    argv = ["queue", "add", "build", "--priority", "1", "--depends", "look"]
    assert kitchen.main(*argv, stdin=built)[0] == 0
    assert go(kitchen, "build")[0] == 0
    kitchen.poll()
    assert titles(kitchen) == ["scout: look"]

    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["look"]["status"] == "done"
    assert "crew: build" in titles(kitchen)


def judged(kitchen, slug):
    """Return the row's line of `work.json`, as the last pass wrote it."""
    kept = json.loads((kitchen.state / "work.json").read_text())
    return {one["key"]: one for one in kept["work"] if one["kind"] == "row"}[slug]


def test_a_scout_row_in_work_json_is_queued_then_scouting_then_report_in(kitchen):
    """The tree reads a scout row's `scout` from `work.json`: queued until it launches, scouting
    while its thread works or its Report does not say done, and report in once its Report says
    `Status: done`. A Report that does not say done is the row's leftover only once its thread
    ended: while the thread works, the scout is at work. The row's other fields, which jview and
    the digest read, say what they did."""
    add(kitchen, "look")
    kitchen.poll()
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("queued", "unapproved", "user")
    assert rows(kitchen)["look"]["status"] == "queued"

    assert go(kitchen, "look")[0] == 0
    kitchen.poll(NOW + timedelta(minutes=3))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"]) == ("scouting", "launching")
    assert rows(kitchen)["look"]["status"] == "launched"

    scout_thread(kitchen, "look")["status"] = "running"
    kitchen.poll(NOW + timedelta(minutes=6))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("scouting", "working", "scout")
    assert rows(kitchen)["look"]["status"] == "running"

    reported(kitchen, "look", status="not done")
    kitchen.poll(NOW + timedelta(minutes=8))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("scouting", "working", "scout")
    assert rows(kitchen)["look"]["status"] == "running"

    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=9))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("scouting", "leftover", "home")
    assert rows(kitchen)["look"]["status"] == "left"

    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look")
    kitchen.poll(NOW + timedelta(minutes=12))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("report in", "working", "scout")
    assert rows(kitchen)["look"]["status"] == "running"

    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=15))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("report in", "done", "ok")
    assert rows(kitchen)["look"]["status"] == "done"


def test_a_done_scout_row_whose_request_file_is_gone_and_thread_archived_stays_done(kitchen):
    """Closing a home can take a done scout's `scouts/<slug>.md` with it. The queue has the row
    at done, so `work.json` reads it done on every pass after, and never launching."""
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["look"]["status"] == "done"

    (kitchen.home / "scouts" / "look.md").unlink()
    scout_thread(kitchen, "look")["archived"] = True
    for minutes in (6, 9):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        line = judged(kitchen, "look")
        assert (line["value"], line["who"]) == ("done", "ok"), line
        assert rows(kitchen)["look"]["status"] == "done"


@pytest.mark.parametrize("left", ["none", "scope", "root", "both"])
def test_a_done_scout_row_of_a_closed_scope_reads_one_home_and_done_on_every_pass(kitchen, left):
    """A scope's `/handoff` archives its plan, and its done scouts' request files may go with it,
    or stay, in the root's `scouts/` or the scope's own. Every pass after reads the row in one home,
    the catch-all that a closed scope's rows fall to, and at done."""
    scope = kitchen.home / "promo"
    scope.mkdir()
    (scope / "plan.md").write_text(PLAN)
    assert add(kitchen, "look", text=request("look", "Home: promo\n"))[0] == 0
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["look"]["status"] == "done"
    assert judged(kitchen, "look")["home"] == "promo"

    (scope / "plan.md").rename(scope / "plan-archived.md")
    written = (kitchen.home / "scouts" / "look.md").read_text()
    (kitchen.home / "scouts" / "look.md").unlink()
    if left in ("scope", "both"):
        (scope / "scouts").mkdir()
        (scope / "scouts" / "look.md").write_text(written)
    if left in ("root", "both"):
        (kitchen.home / "scouts" / "look.md").write_text(written)
    scout_thread(kitchen, "look")["archived"] = True
    seen = []
    for minutes in (6, 9, 12):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        line = judged(kitchen, "look")
        seen.append((line["home"], line["value"], line["who"]))
    assert seen == [("uncategorized", "done", "ok")] * 3


def test_a_scout_row_whose_followup_report_says_done_is_done_and_report_in(kitchen):
    """A home closes a scout whose Report was blocked by appending `## Report, follow-up (…)`, as
    jbus's leftover message tells it to. That last Report is the one the row is judged by, as a
    crew's follow-up Result is, so the row ends done and its scout state is report in."""
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "completed"
    reported(kitchen, "look", status="blocked, the bench is down")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert (judged(kitchen, "look")["scout"], rows(kitchen)["look"]["status"]) == (
        "scouting",
        "left",
    )

    reported(kitchen, "look", heading="## Report, follow-up (2026-11-08, the bench is back)")
    kitchen.poll(NOW + timedelta(minutes=6))
    line = judged(kitchen, "look")
    assert (line["scout"], line["value"], line["who"]) == ("report in", "done", "ok")
    assert rows(kitchen)["look"]["status"] == "done"


def test_a_done_scout_row_with_no_thread_has_no_scout_state_from_any_writer(kitchen):
    """T3 Code's tree shows a row with a `scout` whatever its value, and a row leaves it once its
    thread is archived. A scout row the queue has at done with no thread, as one is once its request
    file went and its thread was archived (`crewthread.crew`), has no thread to archive, so `work.json` gives it no `scout` and it leaves the tree as a done
    crew row does. One that names a thread keeps `report in`. The pass and a write of the queue that
    restates the line agree, and the line a write of the queue makes for a row with none, which it
    judges as if nothing launched (`restated.fresh`), is a queued scout's until the next pass."""
    kitchen.config(max_running=8)
    for slug in ("look", "kept"):
        assert add(kitchen, slug, text=request(slug, asked=f"find out what {slug} does"))[0] == 0
        assert go(kitchen, slug)[0] == 0
    kitchen.poll()
    for slug in ("look", "kept"):
        reported(kitchen, slug)
        scout_thread(kitchen, slug)["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert (judged(kitchen, "look")["scout"], judged(kitchen, "kept")["scout"]) == ("report in",) * 2
    (kitchen.home / "scouts" / "look.md").unlink()
    scout_thread(kitchen, "look")["archived"] = True
    kitchen.poll(NOW + timedelta(minutes=6))
    passed, kept = judged(kitchen, "look"), judged(kitchen, "kept")
    assert (passed["value"], passed["thread"], "scout" in passed) == ("done", "", False)
    assert (kept["value"], kept["scout"]) == ("done", "report in")

    stale = {**passed, "scout": "report in", "value": "working"}
    again = restated.restate(stale, scout=True)
    assert {**again, "confirmed": ""} == {**passed, "confirmed": ""}

    work = json.loads((kitchen.state / "work.json").read_text())
    work["work"] = [one for one in work["work"] if one.get("key") != "look"]
    (kitchen.state / "work.json").write_text(json.dumps(work))
    assert add(kitchen, "other", text=request("other", asked="find out what Z does"))[0] == 0
    assert judged(kitchen, "look")["scout"] == "queued"
    kitchen.poll(NOW + timedelta(minutes=9))
    assert judged(kitchen, "look") == {**passed, "confirmed": judged(kitchen, "look")["confirmed"]}


def test_a_scout_row_a_crewmates_brief_took_over_has_no_scout_state(kitchen):
    """Once the brief a scout delivered takes its row over, the row is a crewmate's and is closed
    as a scout's, so `work.json` gives it no `scout`."""
    kitchen.config(max_running=8)
    add(kitchen, "look")
    go(kitchen, "look")
    kitchen.poll()
    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert judged(kitchen, "look")["scout"] == "report in"

    assert kitchen.main("queue", "add", "look", "--priority", "1", stdin=brief("look"))[0] == 0
    kitchen.poll(NOW + timedelta(minutes=6))

    assert "scout" not in judged(kitchen, "look")


def test_the_brief_a_scout_delivers_at_its_slug_takes_over_its_row_once_its_report_is_done(kitchen):
    kitchen.config(max_running=8)
    add(kitchen, "look", "--entry", "epic")
    go(kitchen, "look")
    kitchen.poll()
    code, said = kitchen.main("queue", "add", "look", "--priority", "1", stdin=brief("look"))
    assert code == 1
    assert said.startswith("refused: look is a scout's row, and its brief is a crewmate's")

    reported(kitchen, "look")
    scout_thread(kitchen, "look")["settled"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["look"]["status"] == "done"
    code, said = kitchen.main("queue", "add", "look", "--priority", "1", stdin=brief("look"))

    assert code == 0, said
    (row,) = queue.load(kitchen.state)
    assert queue.role(row) == queue.CREW
    assert (row["approved"], row["status"], row["thread"], row["entry"]) == (
        "",
        "queued",
        "",
        "epic",
    )
    kitchen.poll(NOW + timedelta(minutes=6))
    assert titles(kitchen) == ["scout: look"]
    assert go(kitchen, "look")[0] == 0
    kitchen.poll(NOW + timedelta(minutes=9))
    assert titles(kitchen) == ["scout: look", "crew: look"]
    assert rows(kitchen)["look"]["status"] == "launched"
    crew = [t for t in kitchen.t3.threads if t["title"] == "crew: look"][0]
    assert rows(kitchen)["look"]["thread"] == crew["threadId"]
    assert (kitchen.home / "scouts" / "look.md").exists()


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


@pytest.mark.parametrize("status", ["preparing", "running", "waiting"])
def test_a_launched_scout_row_whose_thread_is_at_work_is_not_removed(kitchen, status):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.poll()
    thread = scout_thread(kitchen, "alpha")
    thread["status"] = status
    before = (kitchen.state / "queue.json").read_text()

    code, said = kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", AT)

    assert (code, said.splitlines()[0]) == (
        1,
        f"refused: alpha is out: its thread {thread['threadId']} is {status}",
    )
    assert (kitchen.state / "queue.json").read_text() == before


def test_a_launched_scout_row_whose_thread_ended_is_removed(kitchen):
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.poll()
    scout_thread(kitchen, "alpha")["status"] = "completed"

    code, said = kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", AT)

    assert code == 0, said
    assert "alpha" not in rows(kitchen)


def test_the_scout_verbs_are_gone(kitchen):
    code, _ = kitchen.main("scout", "show")

    assert code == 2


@pytest.mark.parametrize("waits", [True, False], ids=["a slot wait", "no wait"])
def test_a_scout_thread_that_ended_its_turn_on_a_slotwait_is_not_left(kitchen, waits):
    """cicd-good-broken-pr-tests-scout, 2026-11-05: the scout ended its turn on "Waiting on a test
    slot", and the next pass marked its row left with "its thread is gone". A thread with a
    registered wait is waiting (`jbus.watch._scouted`): jbus wakes it when a slot is free
    (`slotwait`)."""
    slots = Slots(slot.locks_dir())
    slots.hold("full")
    add(kitchen, "alpha")
    go(kitchen, "alpha")
    kitchen.poll()
    thread = scout_thread(kitchen, "alpha")
    thread |= {"status": "completed", "updatedAt": iso(NOW - timedelta(minutes=40))}
    kitchen.t3.at_work.discard(thread["threadId"])
    if waits:
        waiters.register(slot.locks_dir(), thread["threadId"], "full", 2, ["make", "check"], NOW)
    try:
        for minutes in (3, 60, 180):
            kitchen.poll(NOW + timedelta(minutes=minutes))
            row = rows(kitchen)["alpha"]
            assert (row["status"] == "left") is not waits, row["why"]
    finally:
        slots.close()
