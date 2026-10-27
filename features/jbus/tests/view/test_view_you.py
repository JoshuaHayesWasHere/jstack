"""The You panel: what needs the user, across projects, oldest first."""

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from jbus import questions, threads, waiting, work
from jbus.view.panels.you import panel as panel_you
from jbus.view.panels.you.panel import ACTS, ANSWERS, APPROVES, OPENS, THREADS
from test_jbus_kitchen import GATE as PIPED
from view.scene import (
    GATE,
    PULL,
    RACK,
    ROOT,
    SHELF,
    Scene,
    Served,
    ago,
    et,
    homed,
    iso,
    item,
    out,
    row,
    stacked,
)

HOLDING = "Holds: publishes\nFail-safe: the dry run of the post, in the plan\n"


def a_brief(scene, slug, title, task):
    (scene.state / "briefs").mkdir(exist_ok=True)
    (scene.state / "briefs" / f"{slug}.md").write_text(f"# {slug}: {title}\nTask: {task}\n")


def needing(scene):
    """One need of each of the six kinds, over two projects: a setup 7 hours old, a question
    that holds, a row to approve with a brief and a row behind it, a row at a gate of each
    project, a leftover, and a held pull request. The rows are the user's in `work.json`."""
    stacked(scene)
    rows = json.loads((scene.state / "queue.json").read_text())
    for one in rows:
        if one["slug"] == "rye-loaf":
            one["why"] = "Left: a note"
    scene.queue(rows)
    a_brief(scene, "tea-kettle", "boil the water first", "Boil the water. Then pour it.")
    a_brief(scene, "oat-honey", "stir the honey in", "Stir it.")
    lines = PIPED.format(n="<n>", asked="post the menu?", status="open", slug="jam-jar")
    held = questions.ask(scene.state, scene.home, "jam-jar", lines + HOLDING, ago(hours=3))[0]
    scene.waiting(
        [
            item("config", "config:server", "server is not set", hours=7),
            item(
                "approve",
                "approve:tea-kettle",
                "approve tea-kettle: jbus queue approve --sha 1",
                slug="tea-kettle",
                hours=5,
            ),
            item("left", "left:rye-loaf", "left rye-loaf: a note", minutes=100, slug="rye-loaf"),
            item("hold", "#14", f"hold 14 {PULL.format(14)}: needs the user's word", minutes=12)
            | {"number": 14},
        ]
    )
    return held.number


def test_the_stack_lists_what_needs_the_user_across_projects_oldest_first(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    number = needing(scene)
    served = Served(scene)
    try:
        needs = served.json("/stack.json")["needs"]
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    kinds = ["config", "gate", "approve", "row", "left", "row", "hold"]
    assert [one["kind"] for one in needs] == kinds
    assert [one["project"] for one in needs] == ["demo"] * 5 + ["pantry", "demo"]
    assert [one["since"] for one in needs] == sorted(one["since"] for one in needs)
    assert {one["verb"] for one in needs} <= {
        *(one.verb for one in waiting.KINDS),
        panel_you.ANSWER,
    }
    assert [one["verb"] for one in needs] == [
        "Set up",
        "Answer",
        "Approve launch",
        "Fix brief",
        "Close it",
        "Fix brief",
        "Review merge",
    ]
    assert all(set(one) == set(panel_you._NEED) for one in needs)
    assert all("jbus " not in one["what"] + one["why"] for one in needs)
    by = {one["kind"]: one for one in needs}
    assert by["approve"]["what"] == "tea-kettle: boil the water first"
    assert by["approve"]["why"] == "nobody has approved it"
    assert by["approve"]["unblocks"] == ["tea-cups"]
    assert by["approve"]["open"] == "#/demo/you/approve/tea-kettle"
    assert by["hold"]["what"] == "Pull request #14: oat-honey: stir the honey in"
    assert by["hold"]["why"] == "needs user, touches skills/crew/SKILL.md"
    assert by["hold"]["since"] == iso(ago(minutes=12))
    assert by["left"]["open"] == "#/demo/you/left/rye-loaf"
    assert (by["hold"]["risk"], by["hold"]["answerable"]) == ("merge to main", False)
    assert by["hold"]["open"] == "#/demo/you/hold/14"
    assert (by["gate"]["what"], by["gate"]["risk"]) == ("post the menu?", "publishes")
    assert (by["gate"]["answerable"], by["gate"]["default"]) == (True, "the first one")
    assert by["gate"]["open"] == f"#/demo/gate/{number}"
    assert by["gate"]["due"] is None
    assert by["row"]["project"] == "pantry"
    assert by["row"]["open"] == "#/pantry/you/row/fig-tart"
    assert {one["risk"] for one in needs if one["kind"] not in ("gate", "hold")} == {"reversible"}
    assert {kind: one["slug"] for kind, one in by.items()} == {
        "config": "",
        "approve": "tea-kettle",
        "gate": "jam-jar",
        "left": "rye-loaf",
        "row": "fig-tart",
        "hold": "oat-honey",
    }
    assert demo["needs"] == [one for one in needs if one["project"] == "demo"]


def test_the_kinds_are_in_state_json_as_the_page_shows_them_and_an_added_kind_with_them(
    served, monkeypatch
):
    """The drawer of what waits on the user lists the kinds by their `shown` place, and an
    item's button is its kind's verb. So a kind added to `waiting.KINDS` shows in the drawer
    with no other edit."""
    kinds = served.json("/state.json?project=demo")["kinds"]
    assert [one["name"] for one in kinds] == [
        "row",
        "left",
        "hold",
        "approve",
        "gate",
        "config",
        "held",
    ]
    assert {one["name"]: one["verb"] for one in kinds}["gate"] == "Accept default"
    added = waiting.Kind("chore", "Chores for you", "Do it", 7)
    monkeypatch.setattr(waiting, "KINDS", (*waiting.KINDS, added))
    assert served.json("/state.json?project=demo")["kinds"][-1] == asdict(added)
    assert waiting.kind("chore:sweep") == "chore"


def test_the_roles_are_in_state_json_and_stack_json_and_an_added_role_with_them(
    served, monkeypatch
):
    """The page and its panels name a thread's role from these. So a role added to
    `threads.ROLES` shows in both with no other edit, and a thread's title gives its role."""
    roles = served.json("/state.json?project=demo")["roles"]
    assert [one["name"] for one in roles] == ["crew", "scout", "reviewer", "home", "other"]
    assert served.json("/stack.json")["roles"] == roles
    added = threads.Role("chef", "chef: ", "home", "chef", "chef", "chefs", "Cooks.")
    monkeypatch.setattr(threads, "ROLES", (*threads.ROLES[:-1], added, threads.ROLES[-1]))
    assert asdict(added) in served.json("/state.json?project=demo")["roles"]
    assert served.json("/stack.json")["roles"][-2] == asdict(added)
    assert threads.role_of("chef: oat-milk") == ("chef", "oat-milk")
    crews = (state for facts in work.every() if (state := work.judge(facts)).pattern.who == "crew")
    assert work.holder(next(crews), role="chef").who == "home"


def test_fourteen_waiting_and_one_with_no_default_path_is_the_only_one_that_needs_you(
    tmp_path, monkeypatch
):
    """The scene has eleven questions that go ahead on their default, and a link's conflict,
    whose question goes to its home. It also has a gate of a home's file with a default, and an
    approval, of the one row of the queue, which is the user's to approve. The page's count is
    one.
    Each one is due when it was asked, since the first pass that sees it closes it."""
    scene = Scene(tmp_path, monkeypatch)
    asked = [ago(minutes=10 * at) for at in range(11)]
    for at, when_asked in enumerate(asked):
        lines = PIPED.format(n="<n>", asked=f"which tin {at}?", status="open", slug="jam-jar")
        questions.ask(scene.state, scene.home, "jam-jar", lines, when_asked)
    link = PIPED.format(n="<n>", asked=f"oat-honey {questions.LINK}", status="open", slug="oat")
    questions.ask(scene.state, scene.home, "oat-honey", link, ago(hours=1))
    (scene.home / "gates.md").write_text(
        GATE.format(n=40, asked="a lump?", status="open", default="one")
    )
    scene.waiting([item("approve", "approve:tea-kettle", "approve tea-kettle: jbus queue approve")])
    scene.queue([row("tea-kettle", approved="", why="not approved")])
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert len(demo["waiting"]) == 14
    assert [one["kind"] for one in stack["needs"]] == ["approve"]
    assert [one["waits"] for one in stack["projects"] if one["name"] == "demo"] == [1]
    answerable = [one for one in stack["proceeds"] if one["answerable"]]
    assert len(stack["proceeds"]) == 12 and len(answerable) == 11
    assert not any(questions.LINK in one["what"] for one in stack["proceeds"])
    assert sorted(one["due"] for one in answerable) == sorted(
        iso(when_asked + questions.QUIET) for when_asked in asked
    )
    (home,) = [one for one in stack["proceeds"] if not one["answerable"]]
    assert (home["what"], home["due"]) == ("a lump?", None)
    assert home["default"] == "one. It stands until the home closes it."
    assert [one["due"] for one in stack["proceeds"][:11]] == sorted(
        one["due"] for one in answerable
    )
    assert {one["verb"] for one in answerable} == {"Accept default"}
    assert home["verb"] == "Answer"


YOURS = [pattern.value for pattern in work.PATTERNS if pattern.who == "user"]


def test_every_row_the_pass_marks_as_the_users_needs_the_user(scene, served):
    """Needs you is every line of `work.json` whose holder is the user, whatever the list of
    what waits on the user has. So a hung, lost or waiting task needs the user as much as one
    at a gate, each with what holds it and since when."""
    rows = [
        row(f"yours-{value}", since=et(ago(minutes=10 + at))) | {"value": value, "who": "user"}
        for at, value in enumerate(YOURS)
    ]
    lost = rows[YOURS.index("lost")]
    lost["facts"] = {"thread": "missing", "launch": "launched"}
    rows.append(row("crews-own", "running", thread="mcp:crew") | {"value": "working"})
    scene.queue(rows)
    scene.waiting([])
    needs = served.json("/stack.json")["needs"]
    tasks = {one["slug"]: one for one in served.json("/state.json?project=demo")["tasks"]}
    found = {one["key"].rpartition(":")[2]: one for one in needs}
    assert sorted(found) == sorted(f"yours-{value}" for value in YOURS)
    for value in YOURS:
        one, task = found[f"yours-{value}"], tasks[f"yours-{value}"]
        assert one["since"] == task["since"] == iso(ago(minutes=10 + YOURS.index(value)))
        cause = one["why"] or (one["what"] if one["what"] != task["slug"] else "")
        assert cause, f"{value}: Needs you does not say what holds it"
        assert one["open"] == f"#/demo/task/yours-{value}"
    assert found["yours-hung"]["why"] == "its turn has written nothing, and may be hung"
    assert found["yours-lost"]["why"] == "T3 Code has no such thread, and it wrote nothing"
    assert found["yours-waiting"]["why"] == "the thread waits on a request"
    assert served.json("/stack.json")["projects"][0]["waits"] == len(YOURS)


def test_a_waiting_item_of_a_row_the_pass_does_not_mark_as_the_users_is_no_need(scene, served):
    """The list of what waits on the user is no second source for a row: an item of a row
    the pass judged its crewmate's needs nothing of the user."""
    scene.queue([row("jam-jar", "running", thread="mcp:0000") | {"value": "working"}])
    scene.waiting(
        [
            item("left", "left:jam-jar", "left jam-jar: a note", slug="jam-jar"),
            item("config", "config:t3", "no sign-in to T3 Code"),
        ]
    )
    needs = served.json("/stack.json")["needs"]
    assert [one["key"] for one in needs] == ["config:t3"]


def test_a_thread_of_no_row_that_the_pass_marks_as_the_users_needs_the_user(scene, served):
    """A scout's thread that ended with no Report is the user's, and so a need, since when it
    last wrote."""
    lost = work.judge(
        work.Facts(
            work.Row.ABSENT,
            work.Thread.COMPLETED,
            work.Launch.LAUNCHED,
            work.Written.NONE,
            work.Pull.NONE,
            work.Question.NONE,
            work.Answered.BOTH,
        )
    )
    assert lost.value == "lost"
    about = {"key": "mcp:scout: tin", "kind": "thread", "slug": "tin", "thread": "mcp:scout: tin"}
    line = work.entry(
        lost, work.holder(lost, role="scout"), **about, role="scout", title="scout: tin"
    )
    kept = json.loads((scene.state / "work.json").read_text())
    scene.write("work.json", kept | {"work": [*kept["work"], line]})
    scene.passed(seconds_ago=20, threads=[out("scout: tin", "ended", "completed", minutes=30)])
    needs = served.json("/stack.json")["needs"]
    (one,) = [one for one in needs if one["key"] == "mcp:scout: tin"]
    assert one["what"] == "scout: tin"
    assert one["since"] == iso(ago(minutes=30))
    assert one["why"]


def test_each_need_of_work_carries_the_home_of_its_row_or_thread(scene, served):
    """A need built from a line of `work.json` belongs to a home as every other need does: a
    row of a scoped home's brief to that home, a row of a brief with no `Home:` line to the
    root, and a thread to the home of the task or request it is about."""
    homed(scene)
    waits = work.judge(
        work.Facts(
            work.Row.ABSENT,
            work.Thread.COMPLETED,
            work.Launch.LAUNCHED,
            work.Written.NONE,
            work.Pull.NONE,
            work.Question.NONE,
            work.Answered.BOTH,
        )
    )
    about = {"key": "mcp:scout: look", "kind": "thread", "slug": "look"}
    line = work.entry(
        waits, work.holder(waits, role="scout"), **about, role="scout", title="scout: look"
    )
    kept = json.loads((scene.state / "work.json").read_text())
    scene.write("work.json", kept | {"work": [*kept["work"], line]})
    needs = {one["key"]: one["home"] for one in served.json("/stack.json")["needs"]}
    assert needs["row:jam-lid"] == SHELF
    assert needs["approve:tea-kettle"] == ROOT
    assert needs["mcp:scout: look"] == RACK


CLOSED = """# {name}: handoff

Scope closed: 2026-10-20, its plan has no open entry and no home was started after this one.
Was home: mcp:{name}
"""


def test_a_retired_scopes_gates_wait_on_nobody_and_a_file_gate_stands_until_its_home_closes_it(
    scene, served
):
    """A scope is retired when its handoff says it closed and no home was started for it since:
    its `home-id` names no thread. Its open gates go with it, so neither queue lists them, and its
    answered ones stay on the record of gates. A scope
    started again after it closed is live. A file gate has no timer, so its default says it
    stands until the home of its file closes it."""
    homes = {name: scene.home / name for name in ("shelf", "old-shelf", "back-shelf")}
    for name, where in homes.items():
        where.mkdir()
        if name != "shelf":
            (where / "handoff.md").write_text(CLOSED.format(name=name))
    (homes["shelf"] / "home-id").write_text("mcp:shelf\n")
    (homes["back-shelf"] / "home-id").write_text("mcp:back-shelf-again\n")
    for number, name in enumerate(homes, start=40):
        (homes[name] / "gates.md").write_text(
            GATE.format(n=number, asked=f"which {name} jar?", status="open", default="the jam")
            + GATE.format(n=number + 10, asked=f"is {name} full?", status="open", default="")
            + GATE.format(
                n=number + 20, asked=f"was {name} swept?", status="answered: yes", default=""
            )
        )
    stack = served.json("/stack.json")
    proceeds = {one["what"]: one["default"] for one in stack["proceeds"]}
    assert proceeds == {
        "tea or coffee?": "tea. It stands until the home closes it.",
        "which shelf jar?": "the jam. It stands until the home of shelf closes it.",
        "which back-shelf jar?": "the jam. It stands until the home of back-shelf closes it.",
    }
    asks = [one["what"] for one in stack["needs"] if one["kind"] == "gate"]
    assert sorted(asks) == ["is back-shelf full?", "is shelf full?"]
    gates = served.json("/state.json?project=demo")["gates"]
    assert [one["question"] for one in gates if one["home"] == "old-shelf"] == [
        "was old-shelf swept?"
    ]


def test_a_hold_no_thread_works_on_is_a_need_of_the_user_s(scene, served):
    """A hold that woke its home (`clock.held`) is on Needs you, with its rows and reason."""
    line = "held one, two: 31 minutes by main is red at abcdef123456, its fix merges first"
    scene.waiting([item("held", "held:0123456789ab", line, minutes=1)])
    needs = served.json("/state.json?project=demo")["needs"]
    (need,) = [one for one in needs if one["kind"] == "held"]
    assert "one, two" in need["what"] and "main is red" in need["what"]
    assert need["verb"] == "Pick it up"


DRAWN = r"""
const vm = require("vm"), fs = require("fs");
const page = {
  document: { addEventListener() {} }, panel() {}, PROJECT: "", NOW: 0, ms: () => null,
  esc: String, name: String, parse: (open) => ({ project: "demo", target: open }),
  href: (project, target) => "/" + project + "/" + target,
};
vm.createContext(page);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), page);
const needs = JSON.parse(fs.readFileSync(0, "utf8")), drawn = {};
for (const at of ["", "demo"]) {
  page.PROJECT = at;
  for (const [kind, w] of Object.entries(needs)) {
    page.FORM = {};
    drawn[kind + "@" + (at || "stack")] = vm.runInContext("needRow", page)(w, false);
  }
}
process.stdout.write(JSON.stringify(drawn));
"""


def test_each_act_the_inbox_serves_draws_one_filled_control():
    """Whatever a need asks of the user, its row draws one primary action and no second: an
    answer with a default and one without, an approval, the link to its home's thread, and a
    need with no act of its own, which opens where it is. An act kind added to the server shows
    here first."""
    if not shutil.which("node"):
        pytest.skip("no node on PATH to run the panel's script in")
    need = {"project": "demo", "key": "k", "what": "w", "open": "gate/3", "item": "", "sha": ""}
    need |= {"default": "it waits", "risk": "reversible", "unblocks": [], "since": ""}
    needs = {
        "answer with a default": need
        | {"act": ANSWERS, "answerable": True, "verb": "Accept default"},
        "answer with none": need | {"act": ANSWERS, "answerable": True, "verb": "Answer"},
        "approve": need | {"act": APPROVES, "item": "tea-kettle", "verb": "Approve"},
        "thread": need | {"act": THREADS, "thread": "t3code://thread/1", "verb": "Write"},
        "no act": need | {"act": OPENS, "verb": "Set it up"},
    }
    assert set(ACTS.values()) | {ANSWERS, THREADS} == {one["act"] for one in needs.values()}
    script = Path(panel_you.__file__).with_suffix(".js")
    done = subprocess.run(
        ["node", "-e", DRAWN, str(script)],
        input=json.dumps(needs),
        capture_output=True,
        text=True,
        check=True,
    )
    drawn = json.loads(done.stdout)
    assert {kind: html.count('class="btn fill"') for kind, html in drawn.items()} == {
        kind: 1 for kind in drawn
    }
