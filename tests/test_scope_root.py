"""The root home's side of a scoped home: it makes a scope by one block, reads each scope's
handoff and open plan entries when the user asks for status, and before a launch runs
`jmerge --claims` in place of reading every brief. Every block and the command are lifted from
the home skill and run in a temporary repo."""

import json
import os
import shutil
import subprocess
from datetime import date

import pytest

import test_home_thread
from test_claims import PULLS, WHERE, brief, result
from test_home_merge import ME, OTHER, Home
from test_home_thread import NAME, Scene
from test_scoped_home import ROOT, SCOPE, SCOPED, Homes
from test_tool_calls import SKILLS, Call, errors

NEW = "release"
PREFIX = "rl-"
OWNS = 'how a release is cut, in the user\'s words: "one command, and a tag"'
MAKES = "launch: "
STATUS = "open plan entries"
CLAIMS = "jmerge --claims\n"
CLOSED = "third"


@pytest.fixture
def homes(tmp_path):
    """A repo whose root home and one scoped home have both started."""
    homes = Homes(tmp_path)
    homes.home_starts(ROOT, "")
    homes.home_starts(SCOPED, SCOPE)
    return homes


def make(homes, thread=ROOT, scope=NEW, prefix=PREFIX, owns=OWNS):
    """What the block that makes a scope prints, run by the home whose thread id is `thread`."""
    filled = {"<scope>": scope, "<prefix>": prefix, "<what the scope owns>": owns}
    return homes.step(MAKES, thread, **filled).stdout.splitlines()


def test_the_root_home_makes_a_scope_with_its_plan_and_its_section_of_the_shared_notes(homes):
    """The block dates the plan and the notes with the day it runs on, which may be the next
    one by the time it runs."""
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
    assert homes.changed(before) == ["notes.md", f"{NEW}/plan.md"]
    assert (homes.home_dir / NEW / "plan.md").read_text() == (
        f"# {NAME}, {NEW}: plan\n\nGoal ({today}, the user): {OWNS}\n"
    )
    notes = (homes.home_dir / "notes.md").read_text()
    assert notes.startswith(before["notes.md"].decode())
    heading, *section = notes.removeprefix(before["notes.md"].decode()).strip().splitlines()
    assert heading == f"## Scoped home: {NEW}, {today}"
    said = "\n".join(section)
    assert OWNS in said
    assert f"`{PREFIX}*.md`" in said and f"`/home {NEW}`" in said and f"`{NEW}/`" in said


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
    assert (SKILLS / skill / "SKILL.md").is_file()
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
        ({"scope": "notes.md"}, "notes.md is there already"),
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
    make(homes, scope="pstack", prefix="ps-")
    with (homes.home_dir / "notes.md").open("a") as notes:
        notes.write("- Its briefs and requests are `tasks/rs-*.md` and `scouts/rs-*.md`.\n")
        notes.write("- Its briefs are `old-er-*.md` in the shared `tasks/`.\n")
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


def test_a_scope_that_could_not_be_written_whole_is_taken_back(homes):
    notes = homes.home_dir / "notes.md"
    notes.chmod(0o444)
    before = homes.state()
    (said,) = make(homes)
    assert said.startswith("not made: ") and said.endswith("Nothing is written.")
    assert homes.changed(before) == []
    assert not (homes.home_dir / NEW).exists()
    notes.chmod(0o644)
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


def test_on_status_the_root_reads_each_scope_s_handoff_and_open_plan_entries(homes):
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
        f"=== scope {CLOSED}: no home thread\n"
        "# the third home: handoff\n\n"
        "The scope is closed.\n"
        f"=== scope {CLOSED}: open plan entries\n"
        "none\n"
    )
    assert homes.changed(before) == []


def test_a_scope_just_made_has_no_handoff_yet(homes):
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


def test_the_launch_check_prints_the_files_every_brief_still_out_holds(tmp_path):
    home = Home(tmp_path)
    (home.state / "home-id").write_text(f"{ME}\n")
    scope = home.state / "pstack"
    scope.mkdir()
    (scope / "home-id").write_text(f"{OTHER}\n")
    (home.tasks / "alpha.md").write_text(brief("alpha", home=ME))
    (home.tasks / "beta.md").write_text(brief("beta", thread=False))
    (home.tasks / "ps-gamma.md").write_text(
        brief("ps-gamma", home=OTHER, where="`playbooks/`", result=result(PULLS.format(12)))
    )
    (home.tasks / "merged.md").write_text(brief("merged", result=result(PULLS.format(7))))
    (home.stub / "list.json").write_text(json.dumps([{"number": 12, "url": PULLS.format(12)}]))
    kept = {path: path.read_bytes() for path in home.state.rglob("*") if path.is_file()}
    said = home.run(about=CLAIMS)
    assert (home.stderr, home.code) == ("", 0)
    assert said == [
        f"alpha out root Where: {WHERE}",
        f"beta not launched root Where: {WHERE}",
        "ps-gamma pull request 12 pstack Where: `playbooks/`",
    ]
    assert {path: path.read_bytes() for path in home.state.rglob("*") if path.is_file()} == kept


def test_the_launch_check_waits_when_github_cannot_be_asked(tmp_path):
    home = Home(tmp_path)
    (home.tasks / "alpha.md").write_text(brief("alpha"))
    assert home.run(about=CLAIMS) == ["wait: could not ask GitHub"]
    assert home.code == 1


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
