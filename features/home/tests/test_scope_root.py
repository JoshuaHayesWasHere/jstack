"""The root home's side of a scoped home. The root home makes a scope with one block. When the user
asks for status, it reads each scope's handoff and open plan entries. The tests take every block
and the command from the home skill and run them in a temporary repo."""

import json
import os
import shutil
import subprocess
from datetime import date

import pytest

import test_home_thread
from jbriefs.home import scopes
from jbriefs.skills import listed
from test_home_thread import NAME, Scene
from test_scoped_home import ROOT, SCOPE, SCOPED, Homes
from test_tool_calls import Call, errors

NEW = "release"
PREFIX = "rl-"
OWNS = 'how a release is cut, in the user\'s words: "one command, and a tag"'
MAKES = "launch: "
MAKING = 'echo "made: scope'
STATUS = "open plan entries"
CLOSED = "third"


@pytest.fixture
def homes(tmp_path):
    """A repo whose root home and one scoped home have both started."""
    homes = Homes(tmp_path)
    homes.home_starts(ROOT, "")
    homes.home_starts(SCOPED, SCOPE)
    return homes


def make(homes, thread=ROOT, scope=NEW, prefix=PREFIX, owns=OWNS):
    """What the block that makes a scope prints when the home whose thread id is `thread` runs
    the block."""
    filled = {"<scope>": scope, "<prefix>": prefix, "<what the scope owns>": owns}
    return homes.step(MAKING, thread, **filled).stdout.splitlines()


def test_the_root_home_makes_a_scope_with_its_plan_and_its_prefix(homes):
    """The block dates the plan with the day it runs on. The test accepts the day it started and
    the next day, since the block may run after midnight."""
    before = homes.state()
    first = date.today().isoformat()
    made, launch = make(homes)
    (today,) = {first, date.today().isoformat()} & {
        line.partition("(")[2].partition(",")[0]
        for line in (homes.home_dir / NEW / "plan.md").read_text().splitlines()
        if line.startswith("Goal (")
    }
    assert made.startswith(f"made: scope {NEW}")
    assert launch.startswith(MAKES)
    assert homes.changed(before) == [f"{NEW}/plan.md", f"{NEW}/prefix"]
    assert (homes.home_dir / NEW / "plan.md").read_text() == (
        f"# {NAME}, {NEW}: plan\n\nGoal ({today}, the user): {OWNS}\n"
    )
    assert (homes.home_dir / NEW / "prefix").read_text() == f"{PREFIX}\n"


def test_the_launch_it_prints_is_a_call_the_tool_takes_and_starts_that_scope_s_home(homes):
    _, launch = make(homes)
    sent = json.loads(launch.removeprefix(MAKES))
    assert errors(Call("home: making a scope", "`t3_thread_launch`", ""), sent) == []
    assert sent == {
        "title": f"home: {NAME} {NEW}",
        "workspaceStrategy": {"type": "root"},
        "message": f"/home {NEW}",
    }
    skill, _, typed = sent["message"].removeprefix("/").partition(" ")
    assert skill in listed("skill")
    assert homes.which_home(typed) == [f"scope {NEW}", f"title: {sent['title']}"]


def test_the_launch_is_json_whatever_the_repo_is_called(tmp_path, monkeypatch):
    name = 'a "demo" repo\\ of sorts'
    monkeypatch.setattr(test_home_thread, "NAME", name)
    scene = Scene(tmp_path)
    (scene.home_dir / "plan.md").write_text("")
    scene.home_starts(ROOT, "")
    found = test_home_thread.block("home", MAKING)
    for mark, text in {"<scope>": NEW, "<prefix>": PREFIX, "<what the scope owns>": OWNS}.items():
        found = found.replace(mark, text)
    _, launch = scene.run("home", found, scene.main, ROOT).stdout.splitlines()
    assert json.loads(launch.removeprefix(MAKES))["title"] == f"home: {name} {NEW}"


@pytest.mark.parametrize(
    ("asked", "why"),
    [
        ({"scope": "tasks"}, "tasks is a directory every home of a demo repo shares"),
        ({"scope": "scouts"}, "scouts is a directory every home of a demo repo shares"),
        ({"scope": "reports"}, "reports is a directory every home of a demo repo shares"),
        ({"scope": "log"}, "log is a directory every home of a demo repo shares"),
        ({"scope": "off"}, "off is a file of a demo repo's own directory"),
        ({"scope": "merge.log"}, "merge.log is a file of a demo repo's own directory"),
        ({"scope": SCOPE}, f"{SCOPE} is already a scope of a demo repo"),
        ({"scope": "standing.md"}, "standing.md is there already"),
        ({"scope": "../other"}, "../other is not a name a scope can have"),
        ({"scope": ".hidden"}, ".hidden is not a name a scope can have"),
        ({"scope": "two words"}, "two words is not a name a scope can have"),
        ({"scope": "<scope>"}, "the scope's name is not filled in"),
        ({"scope": ""}, "the scope's name is not filled in"),
        ({"prefix": "<prefix>"}, "the slug prefix is not filled in"),
        ({"prefix": "rl"}, "the slug prefix rl is not"),
        ({"prefix": "Rl-"}, "the slug prefix Rl- is not"),
        ({"prefix": "sc-"}, "a brief or a request already starts with sc-"),
        ({"prefix": "ps-"}, "the slug prefix ps- is another home's"),
        ({"prefix": "ps-x-"}, "the slug prefix ps-x- starts with ps-"),
        ({"prefix": "rs-"}, "the slug prefix rs- is another home's"),
        ({"prefix": "old-"}, "the slug prefix old- is the start of old-er-"),
        ({"owns": "<what the scope owns>"}, "what the scope owns is not filled in"),
        ({"owns": ""}, "what the scope owns is not filled in"),
    ],
)
def test_a_scope_that_cannot_be_made_is_refused_and_nothing_is_written(homes, asked, why):
    homes.sent("tasks", "sc-open", f"Home: {SCOPED}")
    (homes.home_dir / "standing.md").write_text("")
    make(homes, scope="pstack", prefix="ps-")
    for scope, prefix in (("review-speed", "rs-"), ("older", "old-er-")):
        (homes.home_dir / scope).mkdir()
        (homes.home_dir / scope / "prefix").write_text(f"{prefix}\n")
    before = homes.state()
    (said,) = make(homes, **asked)
    assert said.startswith(f"not made: {why}")
    assert said.endswith("Nothing is written.")
    assert homes.changed(before) == []


def test_a_scoped_home_that_is_asked_for_a_scope_is_refused_and_nothing_is_written(homes):
    before = homes.state()
    (said,) = make(homes, thread=SCOPED)
    assert said.startswith(f"not made: this is the home of the scope {SCOPE}")
    assert said.endswith("Nothing is written.")
    assert homes.changed(before) == []


def test_a_scope_that_could_not_be_written_is_refused_and_nothing_is_written(homes):
    homes.home_dir.chmod(0o555)
    before = homes.state()
    try:
        (said,) = make(homes)
    finally:
        homes.home_dir.chmod(0o755)
    assert said.startswith("not made: ") and said.endswith("Nothing is written.")
    assert homes.changed(before) == []
    assert not (homes.home_dir / NEW).exists()
    made, _ = make(homes)
    assert made.startswith(f"made: scope {NEW}")


def status(homes, thread=ROOT):
    return homes.step(STATUS, thread).stdout


@pytest.fixture
def no_jbus(homes, monkeypatch):
    """A machine where jbus is not installed: the root reads no queue row."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return homes


def test_on_status_the_root_reads_each_scope_s_handoff_and_open_plan_entries(no_jbus):
    homes = no_jbus
    (homes.scope_dir / "plan.md").write_text(
        "# the second home: plan\n\n"
        "Goal (2026-10-10, the user): faster reviews\n\n"
        "## sc-open: a task that is out\n"
        "Status: with crewmate (thread mcp:one)\n"
        "Done when:\n- it holds\n\n"
        "## sc-done: a task that merged\n"
        "Status: done (pull request 7 merged)\n"
        "Done when:\n- it held\n"
        "Decisions:\n- Status: planned, as the user first said\n\n"
        "## sc-next: a task with no status yet\n"
        "Done when:\n- it will hold\n"
    )
    closed = homes.home_dir / CLOSED
    closed.mkdir()
    (closed / "plan.md").write_text(
        "# the third home: plan\n\n## th-only: its one task\nStatus: done (pull request 9)\n"
    )
    (closed / "handoff.md").write_text("# the third home: handoff\n\nThe scope is closed.\n")
    (homes.home_dir / "tasks" / "plan.md").write_text("# plan: a brief with that slug\n")
    before = homes.state()
    assert status(homes) == (
        f"=== scope {SCOPE}: home thread {SCOPED}\n"
        "# the second home: handoff\n\n"
        "Was home: mcp:the-last-scoped-home\n"
        f"=== scope {SCOPE}: open plan entries\n"
        "sc-open: a task that is out\n"
        "Status: with crewmate (thread mcp:one)\n"
        "sc-next: a task with no status yet\n"
        f"=== scope {SCOPE}: queue rows\n"
        "no jbus: jbus is not installed here, so it holds no row\n"
        f"=== scope {CLOSED}: no home thread\n"
        "# the third home: handoff\n\n"
        "The scope is closed.\n"
        f"=== scope {CLOSED}: open plan entries\n"
        "none\n"
        f"=== scope {CLOSED}: queue rows\n"
        "no jbus: jbus is not installed here, so it holds no row\n"
        "=== scope uncategorized: no home thread\n"
        "no handoff yet\n"
        "=== scope uncategorized: open plan entries\n"
        "none\n"
        "=== scope uncategorized: queue rows\n"
        "no jbus: jbus is not installed here, so it holds no row\n"
    )
    assert homes.changed(before) == []


def test_a_scope_just_made_has_no_handoff_yet(no_jbus):
    homes = no_jbus
    make(homes)
    said = status(homes)
    assert (
        f"=== scope {NEW}: no home thread\nno handoff yet\n"
        f"=== scope {NEW}: open plan entries\nnone\n"
    ) in said


def test_on_status_a_root_with_no_other_child_reads_its_catch_all_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    scene = Scene(tmp_path)
    for shared in ("tasks", "scouts", "reports", "log"):
        (scene.home_dir / shared).mkdir()
        (scene.home_dir / shared / "plan.md").write_text("# plan: a file with that name\n")
    scene.home_starts(ROOT, "")
    ran = scene.run("home", test_home_thread.block("home", STATUS), scene.main, ROOT)
    assert (ran.returncode, ran.stdout) == (
        0,
        "=== scope uncategorized: no home thread\n"
        "no handoff yet\n"
        "=== scope uncategorized: open plan entries\n"
        "none\n"
        "=== scope uncategorized: queue rows\n"
        "no jbus: jbus is not installed here, so it holds no row\n",
    )


def test_the_scopes_the_root_reads_on_status_are_the_scopes_jbus_queues_for(no_jbus):
    """One rule says what a scope is: a directory of the state with a `plan.md`, but for the
    directories every home shares. A scope just made, with no thread yet, is one; an archived
    scope and a directory with only a `home-id` are none."""
    homes = no_jbus
    state = homes.home_dir
    made = {
        "just-made": {"plan.md": "# a plan\n"},
        "handed-off": {"plan.md": "# a plan\n", "handoff.md": "Was home: mcp:gone\n"},
        "archived": {"plan-archived.md": "# a plan\n", "handoff.md": "Was home: mcp:old\n"},
        "no-plan": {"home-id": "mcp:stray\n"},
        **{
            shared: {"plan.md": "# plan: a file with that name\n"}
            for shared in ("tasks", "scouts", "reports", "log")
        },
    }
    for name, files in made.items():
        (state / name).mkdir(exist_ok=True)
        for file, text in files.items():
            (state / name / file).write_text(text)
    read = [
        line.removeprefix("=== scope ").removesuffix(": open plan entries")
        for line in status(homes).splitlines()
        if line.endswith(": open plan entries")
    ]
    assert read == [scope.name for scope, _, _ in scopes(state)]
    assert read == sorted(["handed-off", "just-made", SCOPE])


def test_on_status_a_scoped_home_reads_no_other_scope(homes):
    assert status(homes, SCOPED) == ""


def test_on_status_the_root_reads_each_scope_s_queue_rows(homes, monkeypatch):
    """The rows of `jbus queue show` whose brief is the scope's, by its `Home:` line."""
    stub = homes.user / "bin"
    stub.mkdir()
    table = (
        "| slug | priority | status | pr | why |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| sc-open | 3 | running |  |  |\n"
        "| sc-pr | 3 | review | https://example.test/pull/7 | a reviewer is out |\n"
        "| root-row | 0 | running |  |  |\n"
    )
    (stub / "jbus").write_text(f"#!/bin/sh\ncat << 'EOF'\n{table}EOF\n")
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    homes.sent("tasks", "sc-open", f"Home: {SCOPE}")
    homes.sent("tasks", "sc-pr", f"Home: {SCOPE}")
    homes.sent("tasks", "root-row")
    said = status(homes)
    assert (
        f"=== scope {SCOPE}: queue rows\n"
        "sc-open | running |  | \n"
        "sc-pr | review | https://example.test/pull/7 | a reviewer is out\n"
    ) in said
    assert "root-row" not in said


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
def test_the_blocks_run_in_zsh_where_a_pattern_that_matches_nothing_stops_a_call(tmp_path):
    scene = Scene(tmp_path)
    (scene.home_dir / "plan.md").write_text("")
    (scene.home_dir / "tasks").mkdir()
    scene.home_starts(ROOT, "")

    def zsh(holding, **filled):
        found = test_home_thread.block("home", holding)
        for mark, text in filled.items():
            found = found.replace(mark, text)
        top = f"{test_home_thread.paths('home')}\n{test_home_thread.finds_this_home(ROOT)}"
        ran = subprocess.run(
            ["zsh", "-c", f"{top}\n{found}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(scene.user)},
            cwd=scene.main,
        )
        assert (ran.stderr, ran.returncode) == ("", 0)
        return ran.stdout

    assert zsh(STATUS).startswith("=== scope uncategorized: no home thread\n")
    filled = {"<scope>": NEW, "<prefix>": PREFIX, "<what the scope owns>": OWNS}
    made, launch = zsh(MAKING, **filled).splitlines()
    assert made.startswith(f"made: scope {NEW}")
    assert json.loads(launch.removeprefix(MAKES))["message"] == f"/home {NEW}"
    assert zsh(STATUS).startswith(f"=== scope {NEW}: no home thread\n")
    (said,) = zsh(MAKING, **{**filled, "<scope>": "other"}).splitlines()
    assert said.startswith(f"not made: the slug prefix {PREFIX} is another home's")


CATCHALL = "uncategorized"


@pytest.fixture
def older(homes):
    """A repo whose root home started before the root's start made `uncategorized`, so the
    catch-all is still to be made by the block that makes a scope."""
    (homes.home_dir / CATCHALL / "plan.md").unlink()
    return homes


@pytest.mark.usefixtures("older")
def test_uncategorized_is_made_with_no_prefix_and_owns_every_slug_no_other_prefix_claims(homes):
    """The catch-all takes no prefix: the block writes its plan, says what it owns, and writes no
    `prefix` file. jbus may have made its directory already, for the files of its rows, and the
    block keeps them. `/home uncategorized` then starts its home like any scope's, and every brief
    no other scope claims is its own."""
    from jbriefs import home as rule

    (homes.home_dir / CATCHALL).mkdir(exist_ok=True)
    (homes.home_dir / CATCHALL / "blockers.json").write_text("{}\n")
    before = homes.state()
    made, launch = make(homes, scope=CATCHALL, prefix="", owns="")
    assert made == (
        f"made: scope {CATCHALL}, with {homes.home_dir / CATCHALL / 'plan.md'} and no prefix: it"
        " owns every slug no other scope's prefix claims"
    )
    assert launch.startswith(MAKES)
    assert homes.changed(before) == [f"{CATCHALL}/plan.md"]
    assert (homes.home_dir / CATCHALL / "blockers.json").read_text() == "{}\n"
    assert (
        (homes.home_dir / CATCHALL / "plan.md")
        .read_text()
        .endswith(f"the user): every row no other scope of {NAME} claims\n")
    )
    assert homes.which_home(CATCHALL) == [f"scope {CATCHALL}", f"title: home: {NAME} {CATCHALL}"]
    for line in ("", "Home: root\n", "Home: gone\n", f"Home: {CATCHALL}\n"):
        assert rule.home_of(homes.home_dir, f"# rl-x\n{line}") == homes.home_dir / CATCHALL


@pytest.mark.usefixtures("older")
def test_uncategorized_given_a_prefix_is_refused_and_nothing_is_written(homes):
    before = homes.state()
    (said,) = make(homes, scope=CATCHALL, prefix="un-")
    assert said.startswith("not made: uncategorized takes no prefix")
    assert homes.changed(before) == []


@pytest.mark.usefixtures("older")
def test_with_uncategorized_made_two_other_scopes_still_may_not_overlap(homes):
    """The catch-all's missing prefix overlaps no other, and the rule between the other scopes
    holds as it did."""
    made, _ = make(homes, scope=CATCHALL, prefix="", owns="")
    assert made.startswith(f"made: scope {CATCHALL}")
    assert not (homes.home_dir / CATCHALL / "prefix").exists()
    made, _ = make(homes, scope="pstack", prefix="ps-")
    assert made.startswith("made: scope pstack")
    before = homes.state()
    (said,) = make(homes, scope="pstack-x", prefix="ps-x-")
    assert said.startswith("not made: the slug prefix ps-x- starts with ps-")
    assert homes.changed(before) == []


QUEUES = 'jbus queue add "$slug"'
WORD = "mcp:the-root-home/msg-7"


@pytest.fixture
def stubbed(homes, monkeypatch):
    """A jbus that has a plan for this repo and writes each `queue add` it is given to a file."""
    stub = homes.user / "bin"
    stub.mkdir()
    called = homes.user / "called"
    (stub / "jbus").write_text(
        f'#!/bin/sh\nif [ "$1" = plan ]; then exit 0; fi\necho "$*: $(head -n 1)" >> "{called}"\n'
    )
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    return homes, called


def queues(homes, thread=ROOT, kind="tasks", slug="sc-row", child=SCOPE, message=WORD):
    filled = {
        "<tasks or scouts>": kind,
        "<slug>": slug,
        "<child>": child,
        "<n>": "3",
        "<entry>": "epic",
        "<thread id>/<message id>": message,
    }
    return homes.step(QUEUES, thread, **filled).stdout


@pytest.mark.parametrize("kind", ["tasks", "scouts"])
def test_the_root_queues_a_row_in_its_child_with_for_and_the_users_message(stubbed, kind):
    homes, called = stubbed
    homes.sent(kind, "sc-row", f"Home: {SCOPE}")
    assert queues(homes, kind=kind) == f"queued: the row sc-row, in {SCOPE}, approved on {WORD}\n"
    assert called.read_text() == (
        f"queue add sc-row --priority 3 --entry epic --from {ROOT} --for {SCOPE} "
        f"--message {WORD}: # sc-row: a title\n"
    )


@pytest.mark.parametrize(
    ("thread", "child", "home", "message", "why"),
    [
        (ROOT, "root", "root", WORD, "the root queues no row of its own"),
        (ROOT, "", SCOPE, WORD, "the root queues no row of its own"),
        (ROOT, "nosuch", "nosuch", WORD, "nosuch is no child home of"),
        (ROOT, SCOPE, "root", WORD, f"has Home: root, not {SCOPE}: write Home: {SCOPE}"),
        (ROOT, SCOPE, SCOPE, "msg-7", "msg-7 is not the user's message"),
        (ROOT, SCOPE, SCOPE, "<thread id>/<message id>", "is not filled in"),
        (SCOPED, SCOPE, SCOPE, WORD, f"this is the home of the scope {SCOPE}"),
    ],
)
def test_the_root_queues_nothing_without_a_child_its_brief_names(
    stubbed, thread, child, home, message, why
):
    homes, called = stubbed
    homes.home_starts(SCOPED, SCOPE)
    homes.sent("tasks", "sc-row", f"Home: {home}")
    said = queues(homes, thread=thread, child=child, message=message)
    assert said.startswith("not queued: ") and why in said
    assert not called.exists()
