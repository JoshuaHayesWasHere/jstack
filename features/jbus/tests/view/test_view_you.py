"""The You panel: what needs the user, across projects, oldest first."""

import json
import shutil
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jbus import questions, queue, waiting, work
from jbus import roles as threads
from jbus.view.panels.you import panel as panel_you
from jbus.view.panels.you.panel import ACTS, ANSWERS, APPROVES, OPENS, THREADS
from test_jbus_kitchen import GATE as PIPED
from view.scene import (
    GATE,
    PULL,
    ROOT,
    SHELF,
    Scene,
    Served,
    ago,
    et,
    homed,
    iso,
    item,
    row,
    stacked,
)

HOLDING = "Holds: publishes\nFail-safe: the dry run of the post, in the plan\n"


def a_brief(scene, slug, title, task):
    (scene.state / "briefs").mkdir(exist_ok=True)
    (scene.state / "briefs" / f"{slug}.md").write_text(f"# {slug}: {title}\nTask: {task}\n")


def needing(scene):
    """One need of each of the six kinds, over two projects, each an item of its project's list
    of what waits on the user: a setup 7 hours old, a question that holds, a row to approve with
    a brief and a row behind it, a row at a gate of `pantry`, a leftover, and a held pull request.
    `demo` also has a row at a gate that its list does not hold, which is no need."""
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
    kinds = ["config", "approve", "gate", "left", "row", "hold"]
    assert [one["kind"] for one in needs] == kinds
    assert [one["project"] for one in needs] == ["demo"] * 4 + ["pantry", "demo"]
    assert [one["since"] for one in needs] == sorted(one["since"] for one in needs)
    assert {one["verb"] for one in needs} <= {
        *(one.verb for one in waiting.KINDS),
        panel_you.ANSWER,
    }
    assert [one["verb"] for one in needs] == [
        "Set up",
        "Approve launch",
        "Answer",
        "Close it",
        "Fix brief",
        "Review merge",
    ]
    assert [set(one) ^ set(panel_you._NEED) for one in needs] == [set()] * len(needs)
    assert all("jbus " not in one["what"] + one["why"] for one in needs)
    by = {one["kind"]: one for one in needs}
    assert by["approve"]["what"] == "tea-kettle: boil the water first"
    assert by["approve"]["why"] == "nobody has approved it"
    assert by["approve"]["unblocks"] == ["tea-cups"]
    assert by["approve"]["open"] == "#/demo/you/approve/tea-kettle"
    assert by["approve"]["since"] == iso(ago(hours=5))
    brief = queue.brief_path(scene.state, "tea-kettle")
    assert by["approve"]["brief_at"] == iso(datetime.fromtimestamp(brief.stat().st_mtime, UTC))
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
        "github",
    ]
    assert {one["name"]: one["verb"] for one in kinds}["gate"] == "Accept default"
    added = waiting.Kind("chore", "Chores for you", "Do it", 9)
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


def test_thirteen_waiting_and_one_with_no_default_path_is_the_only_one_that_needs_you(
    tmp_path, monkeypatch
):
    """The scene has eleven questions that go ahead on their default. It also has a gate of a
    home's file with a default, and an approval, of the one row of the queue, which is the
    user's to approve. The page's count is one.
    Each one is due when it was asked, since the first pass that sees it closes it."""
    scene = Scene(tmp_path, monkeypatch)
    asked = [ago(minutes=10 * at) for at in range(11)]
    for at, when_asked in enumerate(asked):
        lines = PIPED.format(n="<n>", asked=f"which tin {at}?", status="open", slug="jam-jar")
        questions.ask(scene.state, scene.home, "jam-jar", lines, when_asked)
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
    assert len(demo["waiting"]) == 13
    assert [one["kind"] for one in stack["needs"]] == ["approve"]
    assert [one["waits"] for one in stack["projects"] if one["name"] == "demo"] == [1]
    answerable = [one for one in stack["proceeds"] if one["answerable"]]
    assert len(stack["proceeds"]) == 12 and len(answerable) == 11
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


def test_a_row_or_thread_the_pass_marks_as_the_users_and_no_list_holds_is_no_need(scene, served):
    """Needs you is jbus's list of what waits on the user and nothing else. A task that `work.json`
    marks as the user's, hung, lost or waiting on a request, is the system's to fix while the list
    does not hold it, so it is no need and adds nothing to the count."""
    rows = [
        row(f"yours-{value}", since=et(ago(minutes=10 + at))) | {"value": value, "who": "user"}
        for at, value in enumerate(YOURS)
    ]
    rows[YOURS.index("lost")]["facts"] = {"thread": "missing", "launch": "launched"}
    scene.queue(rows)
    scene.waiting([])
    stack = served.json("/stack.json")
    assert stack["needs"] == []
    assert stack["projects"][0]["waits"] == 0


def test_an_item_of_the_list_that_names_a_row_needs_the_user_in_the_row_s_words(scene, served):
    """An item of the list that names a row is a need whatever `work.json` says of the row, and
    says what holds the row in the task's words, since when the row is in that state."""
    scene.queue([row("jam-jar", "gate", why="a gate the Chef has", since=et(ago(minutes=40)))])
    scene.waiting(
        [
            item("row", "row:jam-jar", "condition jam-jar: which tin?", slug="jam-jar"),
            item("config", "config:t3", "no sign-in to T3 Code"),
        ]
    )
    needs = {one["key"]: one for one in served.json("/stack.json")["needs"]}
    assert sorted(needs) == ["config:t3", "row:jam-jar"]
    jar = needs["row:jam-jar"]
    assert (jar["verb"], jar["open"]) == ("Fix brief", "#/demo/you/row/jam-jar")
    assert jar["since"] == iso(ago(minutes=40))
    assert "jbus " not in jar["what"] + jar["why"]


def test_each_need_of_a_row_carries_the_home_of_its_row(scene, served):
    """A need of an item that names a row belongs to a home as every other need does: a row of a
    scoped home's brief to that home, and a row of a brief with no `Home:` line to the root."""
    homed(scene)
    scene.waiting(
        [
            item("row", "row:jam-lid", "condition jam-lid: which lid?", slug="jam-lid"),
            item("approve", "approve:tea-kettle", "approve tea-kettle: it", slug="tea-kettle"),
        ]
    )
    needs = {one["key"]: one["home"] for one in served.json("/stack.json")["needs"]}
    assert (needs["row:jam-lid"], needs["approve:tea-kettle"]) == (SHELF, ROOT)


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


def test_a_file_gate_that_holds_for_a_door_is_a_need_and_not_a_gate_that_takes_its_default(
    scene, served
):
    """A gate of a home's file whose `Holds:` line names a door waits for the user as a question
    jbus holds that holds does: it is a need with that door as its risk, whatever its default,
    and it does not go ahead on its default, nor does its default say it stands."""
    (scene.home / "gates.md").write_text(
        GATE.format(n=40, asked="drop the old tables?", status="open", default="drop them")
        + "Holds: deletes data\nFail-safe: the dump of the tables, in the plan\n"
    )
    stack = served.json("/stack.json")
    assert stack["proceeds"] == []
    (need,) = [one for one in stack["needs"] if one["what"] == "drop the old tables?"]
    assert (need["kind"], need["risk"], need["default"]) == ("gate", "deletes data", "drop them")
    assert need["doors"] == ["deletes data"]


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
    answer, an approval, the link to its home's thread, and a
    need with no act of its own, which opens where it is. An act kind added to the server shows
    here first."""
    if not shutil.which("node"):
        pytest.skip("no node on PATH to run the panel's script in")
    need = {"project": "demo", "key": "k", "what": "w", "open": "gate/3", "slug": "", "sha": ""}
    need |= {"default": "it waits", "risk": "reversible", "unblocks": [], "since": ""}
    needs = {
        "answer": need | {"act": ANSWERS, "answerable": True, "verb": "Answer"},
        "approve": need | {"act": APPROVES, "sha": "0123456789ab", "verb": "Approve"},
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


MOMENT = Path(__file__).parent.parent / "fixtures" / "waiting" / "2026-10-26T125904Z.json"
"""jbus's `waiting` event of 2026-10-26 12:59:04Z on jstack, as it was logged: ten waits, six of
them questions whose default the thread already acted on (reports/jv-glance/state/events.jsonl)."""
LIST_KINDS = {"condition": "row", "left": "left", "held": "held"}


def replayed(scene, event):
    """Put the moment of a `waiting` event back in the scene: each question it lists is asked
    again, as its thread piped it, and every other line it lists is an item of the list, of the
    kind its first word names. A line marked `-` is gone, and is not put back."""
    now = [line[2:] for line in event["text"].splitlines() if not line.startswith("-")]
    items = []
    for line in now:
        said, _, rest = line.partition(": ")
        word, _, subject = said.partition(" ")
        if word == "question":
            asked = rest.partition(" Its default is acted on already")[0]
            piped = PIPED.format(n="<n>", asked=asked, status="open", slug="jam-jar")
            questions.ask(scene.state, scene.home, "jam-jar", piped, ago(minutes=30))
            continue
        kind = LIST_KINDS[word]
        found = item(kind, f"{kind}:{subject}", line, slug=subject, minutes=40)
        items.append(found | ({"rows": [subject], "home": ""} if kind == "held" else {}))
    scene.waiting(items)
    return now


def test_the_waiting_event_of_a_busy_moment_is_four_needs_and_one_line_of_defaults(scene, served):
    """Needs you is jbus's list of what waits on the user, the list its `waiting` event logs, and
    nothing else: each item that is not on its default is one need, and every widget that counts
    Needs you counts those. The gates already on their default are no need. They are counted
    apart, as one line. At 12:59:04Z jbus listed ten waits: four need Josh and six take their
    default."""
    event = json.loads(MOMENT.read_text())
    (scene.home / "gates.md").unlink(missing_ok=True)
    assert event["event"] == waiting.EVENT and event["at"] == "2026-10-26T12:59:04+00:00"
    listed = replayed(scene, event)
    assert len(listed) == 10
    stack = served.json("/stack.json")
    demo = served.json("/state.json?project=demo")
    keys = {one["key"] for one in stack["needs"]}
    assert keys == {
        "row:ux-flow-model",
        "left:bl-lands",
        "left:cleanup-ux-flow-status",
        "held:cleanup-ux-homes-board-pr",
    }
    assert {one["key"] for one in demo["needs"]} == keys
    assert len(stack["proceeds"]) == len(demo["proceeds"]) == 6
    assert all(one["kind"] == "gate" for one in stack["proceeds"])
    (project,) = stack["projects"]
    assert project["waits"] == 4
    assert sum(home["waits"] for home in project["homes"]) == 4
    (you,) = [one for one in stack["slow"]["stages"] if one["key"] == "you"]
    assert you["rows"] == 4
    board = served.json("/panel/pipeline.json")["data"]
    (stage,) = [one for one in board["stages"] if one["key"] == "you"]
    assert stage["count"] == 4


DEFAULTS = r"""
const vm = require("vm"), fs = require("fs");
const page = {
  document: { addEventListener() {} }, panel() {}, PROJECT: "demo",
  esc: String, href: (project, target) => "#/" + project + "/" + target,
};
vm.createContext(page);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), page);
const said = {};
for (const n of [0, 1, 6]) {
  said[n] = vm.runInContext("defaultLine", page)({ proceeds: Array(n).fill({}) });
}
process.stdout.write(JSON.stringify(said));
"""


def test_the_gates_on_their_default_are_one_line_that_asks_nothing():
    """The project's Needs you draws the gates already on their default as one line, which opens
    the list of gates and has no control that answers one. With none, it draws nothing."""
    if not shutil.which("node"):
        pytest.skip("no node on PATH to run the panel's script in")
    script = Path(panel_you.__file__).with_suffix(".js")
    done = subprocess.run(
        ["node", "-e", DEFAULTS, str(script)], capture_output=True, text=True, check=True
    )
    said = json.loads(done.stdout)
    assert said["0"] == ""
    assert "1 takes its default" in said["1"] and "6 take their default" in said["6"]
    assert 'href="#/demo/you:gate"' in said["6"]
    assert "button" not in said["6"] and "data-accept" not in said["6"]


def test_a_spent_allowance_is_one_need_that_opens_and_clears_by_itself(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    line = "GitHub refused it for its API rate limit: its core window has 0 of 5000 calls left"
    scene.waiting([item("github", "github:demo", line, minutes=4)])
    served = Served(scene)
    try:
        needs = served.json("/state.json?project=demo")["needs"]
    finally:
        served.close()
    (need,) = needs
    assert (need["kind"], need["what"], need["verb"]) == ("github", line, "See when it resets")
    assert (need["act"], need["thread"]) == (OPENS, "")
    assert need["default"] == panel_you.IDLE["github"]
    assert need["open"] == "#/demo/you/github"
