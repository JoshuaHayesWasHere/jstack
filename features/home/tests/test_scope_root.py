"""The root home's side of a scoped home. The root home makes a scope with one block. When the user
asks for status, it reads each scope's handoff and open plan entries. Before a launch it runs
`jmerge --claims` to name the overlaps, in place of reading every brief. The tests take every block
and the command from the home skill and run them in a temporary repo."""

import json
import os
import shutil
import subprocess
from datetime import date

import pytest

import test_home_thread
from jbriefs.skills import listed
from test_claims import PULLS, brief, result
from test_home_merge import ME, OTHER, Home, block, paths
from test_home_thread import NAME, Scene
from test_scoped_home import ROOT, SCOPE, SCOPED, Homes
from test_tool_calls import Call, errors

NEW = "release"
PREFIX = "rl-"
OWNS = 'how a release is cut, in the user\'s words: "one command, and a tag"'
MAKES = "launch: "
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
    return homes.step(MAKES, thread, **filled).stdout.splitlines()


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
    found = test_home_thread.block("home", MAKES)
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


def test_a_thread_that_is_no_home_makes_no_scope(homes):
    before = homes.state()
    ran = homes.step(
        MAKES,
        "mcp:a-crewmate",
        **{"<scope>": NEW, "<prefix>": PREFIX, "<what the scope owns>": OWNS},
    )
    assert ran.returncode == 1
    assert ran.stdout.startswith("no home:")
    assert homes.changed(before) == []


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


def test_on_status_a_repo_with_no_scope_prints_nothing(tmp_path):
    scene = Scene(tmp_path)
    for shared in ("tasks", "scouts", "reports", "log"):
        (scene.home_dir / shared).mkdir()
        (scene.home_dir / shared / "plan.md").write_text("# plan: a file with that name\n")
    scene.home_starts(ROOT, "")
    ran = scene.run("home", test_home_thread.block("home", STATUS), scene.main, ROOT)
    assert (ran.returncode, ran.stdout) == (0, "")


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


def launch_check(home, slug):
    """The home skill's launch check, run from the main checkout with the block at the top."""
    return home.sh(f"{paths()}\n{block('overlaps ').replace('<slug>', slug)}")


def test_the_launch_check_names_the_briefs_of_every_home_on_the_task_s_files(tmp_path):
    home = Home(tmp_path)
    (home.state / "home-id").write_text(f"{ME}\n")
    scope = home.state / "pstack"
    scope.mkdir()
    (scope / "home-id").write_text(f"{OTHER}\n")
    (home.tasks / "task.md").write_text(brief("task", thread=False, where="`playbooks/a.md`"))
    (home.tasks / "alpha.md").write_text(brief("alpha", home=ME))
    (home.tasks / "ps-gamma.md").write_text(
        brief("ps-gamma", home=OTHER, where="`playbooks/`", result=result(PULLS.format(12)))
    )
    (home.tasks / "merged.md").write_text(
        brief("merged", where="`playbooks/`", result=result(PULLS.format(7)))
    )
    (home.stub / "list.json").write_text(json.dumps([{"number": 12, "url": PULLS.format(12)}]))
    kept = {path: path.read_bytes() for path in home.state.rglob("*") if path.is_file()}
    said = launch_check(home, "task")
    assert (home.stderr, home.code) == ("", 0)
    assert said[:-1] == ["overlaps ps-gamma (#12) on `playbooks/a.md`: the second to merge rebases"]
    assert said[-1].startswith("go: ")
    assert {path: path.read_bytes() for path in home.state.rglob("*") if path.is_file()} == kept


def test_the_launch_check_waits_when_github_cannot_be_asked(tmp_path):
    home = Home(tmp_path)
    (home.tasks / "alpha.md").write_text(brief("alpha"))
    assert launch_check(home, "task") == [
        "wait: could not ask GitHub: gh exited 1: it said nothing"
    ]


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

    assert zsh(STATUS) == ""
    filled = {"<scope>": NEW, "<prefix>": PREFIX, "<what the scope owns>": OWNS}
    made, launch = zsh(MAKES, **filled).splitlines()
    assert made.startswith(f"made: scope {NEW}")
    assert json.loads(launch.removeprefix(MAKES))["message"] == f"/home {NEW}"
    assert zsh(STATUS).startswith(f"=== scope {NEW}: no home thread\n")
    (said,) = zsh(MAKES, **{**filled, "<scope>": "other"}).splitlines()
    assert said.startswith(f"not made: the slug prefix {PREFIX} is another home's")
