"""`jbus.dispatch` launches an approved row only on a machine with room, and reports each spell with
no room once. It writes the thread it launched or adopted on the one `Thread:` line of the brief.
Like `test_jbus_kitchen.py`, the tests run the real pass against the fakes.
"""

import json
import os
import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

import jroles.mirror
from crew_branches import git_said
from jbriefs.home import home_of
from jbriefs.parse import thread_of
from jbus import children, cleanup, queue
from jmerge import judgement
from test_jbus_kitchen import NOW, RESULT, approved, complete, go, queued, review, sends
from test_room import FRESH

FULL = "load 30.00 is at or over 200% of 12 cores"


LATER = [NOW + timedelta(minutes=3 * n) for n in range(40)]


def test_a_machine_with_room_launches(kitchen):
    approved(kitchen, "alpha")
    said = kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]
    assert not any("no room" in line for line in said) and kitchen.lines("note") == []


def test_a_launched_crew_has_its_scratch_folder_on_disk_before_its_thread_starts(kitchen):
    approved(kitchen, "alpha")
    kitchen.poll()
    assert (kitchen.root / "scratch" / kitchen.checkout.name / "alpha").is_dir()


def test_a_machine_with_no_room_launches_no_row_that_pass_and_sends_nothing(kitchen):
    kitchen.config(max_running=5)
    approved(kitchen, "alpha", priority=1)
    approved(kitchen, "beta", priority=2)
    kitchen.machine(load="30.00")
    said = kitchen.poll()
    assert [line for line in said if "alpha" in line] == [f"wait alpha: no room: {FULL}"]
    assert not any("beta" in line for line in said)
    assert kitchen.t3.launches == [] and not (kitchen.home / "tasks/alpha.md").exists()
    assert list((kitchen.state_dir / "launches").glob("*/*/*.json")) == []
    assert kitchen.lines("gate") == []
    assert not any("no room" in event["line"] + event["text"] for event in kitchen.events())
    kitchen.machine()
    kitchen.poll(LATER[1])
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]


def test_a_plan_past_its_cushion_waits_as_a_full_machine_does(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(plan={**FRESH, "five_hour": ("100", 3600 + 59)})
    assert (
        "wait alpha: no room: the five-hour limit is 100% used, at or over 90%,"
        " and resets in 1 h 0 min"
    ) in kitchen.poll()
    assert kitchen.t3.launches == []


def test_the_tenth_pass_with_no_room_is_one_gate_and_the_eleventh_is_none(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:9]:
        kitchen.poll(moment)
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[9])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 10 passes: {FULL}"]
    kitchen.poll(LATER[10])
    assert len(kitchen.lines("condition")) == 1 and kitchen.t3.launches == []


def test_room_passes_in_the_config_is_how_many_passes_wait_before_the_gate(kitchen):
    kitchen.config(room_passes=2)
    approved(kitchen, "alpha")
    kitchen.machine(memory=1048576)
    kitchen.poll(LATER[0])
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[1])
    assert kitchen.lines("condition") == [
        "condition alpha: no room for 2 passes: 1.0 GB of memory available, under 6"
    ]


def test_a_pass_with_room_starts_the_count_again(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:9]:
        kitchen.poll(moment)
    kitchen.machine()
    kitchen.t3.refuse = "no"
    kitchen.poll(LATER[9])
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the launch"]
    kitchen.machine(load="30.00")
    for moment in LATER[10:19]:
        kitchen.poll(moment)
    assert len(kitchen.lines("condition")) == 1
    kitchen.poll(LATER[19])
    assert kitchen.lines("condition")[1:] == [f"condition alpha: no room for 10 passes: {FULL}"]


def test_a_pass_in_which_the_row_does_not_reach_the_check_starts_the_count_again(kitchen):
    kitchen.config(room_passes=3)
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    kitchen.poll(LATER[0])
    kitchen.poll(LATER[1])
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    kitchen.poll(LATER[2])
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll(LATER[3])
    kitchen.poll(LATER[4])
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[5])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 3 passes: {FULL}"]


def test_room_passes_lowered_under_a_row_that_waits_still_gates_once(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:6]:
        kitchen.poll(moment)
    kitchen.config(room_passes=5)
    kitchen.poll(LATER[6])
    kitchen.poll(LATER[7])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 7 passes: {FULL}"]


def test_a_second_spell_with_no_room_is_a_gate_of_its_own(kitchen):
    kitchen.config(room_passes=1)
    approved(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    for n, load in enumerate(["30.00", "0.42", "30.00"]):
        kitchen.machine(load=load)
        kitchen.poll(LATER[n])
    gate = f"condition alpha: no room for 1 passes: {FULL}"
    assert kitchen.lines("condition") == [gate, "condition alpha: T3 Code refused the launch", gate]


@pytest.mark.parametrize("jgauge", ["missing", "fails", "says something else"])
def test_a_room_check_that_cannot_run_waits(kitchen, jgauge):
    approved(kitchen, "alpha")
    if jgauge == "missing":
        every = os.environ["PATH"].split(os.pathsep)
        without = [part for part in every if not (Path(part) / "jgauge").exists()]
        kitchen.monkeypatch.setenv("PATH", os.pathsep.join(without))
        assert without != every
    else:
        does = "exit 1" if jgauge == "fails" else "echo maybe"
        (kitchen.stub / "jgauge").write_text(f"#!/bin/sh\n{does}\n")
        (kitchen.stub / "jgauge").chmod(0o755)
    assert "wait alpha: no room: jgauge room did not run" in kitchen.poll()
    assert kitchen.t3.launches == [] and kitchen.lines("gate") == []


def test_a_plan_limit_that_is_not_known_launches_and_is_a_note_once_a_day(kitchen):
    approved(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    limits = kitchen.machine(plan=None)
    kitchen.poll(LATER[0])
    kitchen.poll(LATER[1])
    note = (
        "note demo: the plan's five-hour and weekly limits are not known: "
        f"{limits} does not give them"
    )
    assert kitchen.lines("note") == [note]
    assert len(kitchen.t3.launches) == 2
    kitchen.poll(NOW + timedelta(days=1))
    assert kitchen.lines("note") == [note, note]


def where_the_findings_go(kitchen, slug):
    """Return the thread `jbus.reviewed` tells of the brief's review: the one its `Thread:`
    line names."""
    return thread_of((kitchen.home / f"tasks/{slug}.md").read_text())


@pytest.mark.parametrize(
    ("lost", "had", "result"),
    [
        (None, "", ""),
        ("after", "", ""),
        (None, "Thread: mcp:an-earlier-launch\n", ""),
        ("after", "", RESULT),
    ],
    ids=["a launch", "an adoption", "a line already there", "a Result written before the line"],
)
def test_a_launched_or_adopted_thread_is_the_one_thread_line_in_the_head_of_the_brief(
    kitchen, lost, had, result
):
    approved = complete("alpha", "Decisions: none\nHome: uncategorized\n").replace(
        "\n", f"\n{had}", 1
    )
    queued(kitchen, "alpha", approved)
    brief = kitchen.home / "tasks/alpha.md"
    kitchen.t3.lose = lost
    kitchen.poll()
    if lost:
        assert brief.read_text() == approved
        with brief.open("a") as file:
            file.write(result)
        kitchen.t3.lose = None
        assert "adopted alpha: mcp:thread-1" in kitchen.poll(NOW + timedelta(minutes=3))
    written = brief.read_text()
    lines = written.splitlines()
    assert [line for line in lines if line.startswith("Thread:")] == ["Thread: mcp:thread-1"]
    assert [line for line in lines if line != "Thread: mcp:thread-1"] == [
        line for line in (approved + result).splitlines() if not line.startswith("Thread:")
    ]
    place = lines.index("Thread: mcp:thread-1")
    assert place == (lines.index("## Result") - 1 if result else len(lines) - 1)
    assert where_the_findings_go(kitchen, "alpha") == "mcp:thread-1"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert brief.read_text() == written and len(kitchen.t3.launches) == 1


def test_a_launch_whose_brief_never_got_its_line_gets_it_on_the_next_pass(kitchen):
    """The test covers two cases: a pass that ended between writing the launch record and writing
    the line, and a slug that jbus launched before it wrote the line at all."""
    queued(kitchen, "alpha")
    kitchen.poll()
    brief = kitchen.home / "tasks/alpha.md"
    whole = brief.read_text()
    assert "Thread: mcp:thread-1\n" in whole
    brief.write_text(whole.replace("Thread: mcp:thread-1\n", "") + RESULT)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert brief.read_text() == whole.replace("Thread: mcp:thread-1\n", "") + (
        RESULT.replace("\n## Result", "\nThread: mcp:thread-1\n## Result")
    )
    assert where_the_findings_go(kitchen, "alpha") == "mcp:thread-1"
    brief.write_text(whole.replace("Thread: mcp:thread-1\n", "") + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.t3.threads[0]["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=4))
    assert [given["threadId"] for given in sends(kitchen)] == ["mcp:thread-1"]
    assert kitchen.lines("gate") == []
    brief.write_text(brief.read_text().replace("mcp:thread-1", "mcp:a-later-launch"))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert where_the_findings_go(kitchen, "alpha") == "mcp:a-later-launch"


@pytest.mark.parametrize("copied", [False, True], ids=["no copy", "a copy with no Home: line"])
def test_a_launch_keeps_the_home_its_queued_brief_names_in_the_brief_it_writes(kitchen, copied):
    """A scoped home's row is still its own once launched: every message about it is routed by
    the copy in `tasks/`, so the copy names the home the queued brief names."""
    flow = kitchen.home / "flow"
    flow.mkdir(parents=True)
    (flow / "plan.md").write_text("# a plan\n")
    (flow / "home-id").write_text("mcp:flow-home\n")
    stored = complete("alpha").replace("\n", "\nHome: flow\n", 1)
    queued(kitchen, "alpha", stored)
    brief = kitchen.home / "tasks/alpha.md"
    if copied:
        brief.parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(judgement.body(stored))
    kitchen.poll()
    copy = brief.read_text()
    assert [line for line in copy.splitlines() if line.startswith("Home:")] == ["Home: flow"]
    assert home_of(kitchen.home, copy) == flow
    assert judgement.brief_sha(copy) == judgement.brief_sha(stored)
    assert "Home: flow\n" in kitchen.t3.launches[0]["message"]
    assert "out alpha: row launched" in children.out(kitchen.home, flow, kitchen.state, [])
    assert kitchen.lines("gate") == []


@pytest.mark.parametrize("home", ["", "root"], ids=["no Home: line", "Home: root"])
def test_a_row_whose_brief_names_no_child_home_is_refused_at_launch_and_the_digest_says_so(
    kitchen, home
):
    """The root home owns no row: a row that would start under it waits, gated, until it names
    a child home. A brief jbus files itself skips the check of `jbus queue add`, so the launch
    is where it holds."""
    line = f"Home: {home}\n" if home else ""
    text = complete("alpha").replace("Home: uncategorized\n", line)
    queue.add(kitchen.state, "alpha", 1, [], text, ran_by=queue.PASS)
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll()
    assert kitchen.t3.launches == []
    why = f"its brief names {'root' if home else 'no home'}"
    assert any(f"alpha: {why}" in line for line in kitchen.lines())
    code, out = kitchen.main("digest", "--json")
    assert code == 0 and why in out
    assert not (kitchen.home / "tasks/alpha.md").exists()


def test_a_row_that_names_the_catch_all_launches_under_it(kitchen):
    queued(kitchen, "alpha", complete("alpha", "Home: uncategorized\n"))
    kitchen.poll()
    assert "Home: uncategorized\n" in kitchen.t3.launches[0]["message"]


@pytest.mark.parametrize(
    "written",
    [
        "{not json",
        '[{"slug": "alpha", "priority": "soon"}]',
        '[{"slug": "alpha", "priority": 1, "depends": "beta"}]',
        '["alpha"]',
    ],
)
def test_a_queue_that_does_not_parse_is_a_gate_and_nothing_is_launched(kitchen, written):
    kitchen.state.mkdir(parents=True)
    (kitchen.state / "queue.json").write_text(written)
    kitchen.poll()
    assert kitchen.lines() == ["condition demo: queue.json does not parse"]
    assert kitchen.t3.launches == []
    assert (kitchen.state / "queue.json").read_text() == written


@pytest.mark.parametrize("procfs", [True, False], ids=["proc", "no-proc"])
def test_a_settled_crew_leaves_no_worktree_in_its_claude_scratchpad_but_one_in_use_or_another_s(
    kitchen, monkeypatch, procfs
):
    """Settling a crew runs `jbus.cleanup.clear_scratch`, which removes the crew's scratch folder
    and the worktrees under its Claude scratchpad, and keeps one a process works in and one under
    another crew's. The temporary folder is reached through a link, as macOS's /tmp and /var are,
    while git lists each worktree at its resolved path; and with no /proc, as on macOS, `lsof`
    says which folder a process works in."""
    if not procfs:
        monkeypatch.setattr(cleanup, "ROOT", kitchen.root / "no-proc")
    (kitchen.root / "tmp").mkdir()
    (kitchen.root / "linked").symlink_to(kitchen.root / "tmp")
    monkeypatch.setenv("CLAUDE_CODE_TMPDIR", str(kitchen.root / "linked"))
    claude = kitchen.root / "tmp" / f"claude-{os.getuid()}"

    def scratchpad(slug):
        tree = kitchen.root / "worktrees" / kitchen.checkout.name / slug
        kitchen.t3.thread(slug, "completed", worktreePath=str(tree))
        return claude / re.sub("[^A-Za-z0-9]", "-", str(tree)) / "session" / "scratchpad"

    mine, theirs = scratchpad("alpha"), scratchpad("beta")
    for tree in (mine / "base.Xy12/base", mine / "busy", theirs / "base"):
        kitchen.git("worktree", "add", "-q", "--detach", str(tree))
    folder = kitchen.root / "scratch" / kitchen.checkout.name / "alpha"
    folder.mkdir(parents=True)
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT.replace("Status: done", "Status: paused"))
    with subprocess.Popen(["sleep", "60"], cwd=mine / "busy") as busy:
        try:
            kitchen.poll()
        finally:
            busy.kill()
    listed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=kitchen.checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert f"worktree {mine / 'base.Xy12/base'}\n" not in listed
    assert not (mine / "base.Xy12/base").exists() and not folder.exists()
    assert f"worktree {mine / 'busy'}\n" in listed and f"worktree {theirs / 'base'}\n" in listed


def t3_tree(kitchen, slug):
    """The path T3 Code gives the worktree of the branch `slug`: `<its home>/worktrees/<the
    checkout's name>/<slug>`."""
    return Path(os.environ["T3CODE_HOME"]) / "worktrees" / kitchen.checkout.name / slug


def crew_trees(kitchen, slug):
    """Each worktree git lists on the branch `slug`, and whether the branch is there."""
    listed = git_said(kitchen, "worktree", "list", "--porcelain").split("\n\n")
    trees = [one.splitlines()[0] for one in listed if f"branch refs/heads/{slug}" in one]
    return trees, git_said(kitchen, "branch", "--list", "--format=%(refname)", slug)


@pytest.mark.parametrize("lose", [None, "after", "before"], ids=["a reply", "lost", "dropped"])
def test_a_crew_launches_into_the_one_worktree_jbus_made_with_its_settings_in_it(kitchen, lose):
    """jbus makes the crew's worktree where T3 Code would, on the slug's branch off origin's
    main, writes the crew's settings file and the `.gitignore` that keeps it out of git, and
    launches into it with `existing_worktree` (`jbus.crewtree`). A second pass, a lost reply that
    is adopted, and a dropped launch that is tried once more make no second worktree or branch."""
    approved(kitchen, "alpha")
    kitchen.t3.lose = lose
    kitchen.poll()
    kitchen.t3.lose = None
    tree = t3_tree(kitchen, "alpha")
    strategy = {"type": "existing_worktree", "worktreePath": str(tree), "branch": "alpha"}
    assert kitchen.t3.launches[0]["workspaceStrategy"] == strategy
    settings = jroles.mirror.crew_settings(jroles.mirror.Main.of(Path.home()))
    assert json.loads((tree / ".claude" / "settings.json").read_text()) == settings
    assert (tree / ".claude" / ".gitignore").read_text() == "*\n"
    assert git_said(kitchen, "-C", str(tree), "status", "--porcelain") == ""
    assert git_said(kitchen, "rev-parse", "alpha") == git_said(kitchen, "rev-parse", "origin/main")
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    launches = kitchen.t3.launches
    assert len(launches) == (2 if lose == "before" else 1)
    assert [given["workspaceStrategy"] for given in launches] == [strategy] * len(launches)
    assert crew_trees(kitchen, "alpha") == ([f"worktree {tree}"], "refs/heads/alpha")
    assert where_the_findings_go(kitchen, "alpha") == "mcp:thread-1"
    assert kitchen.lines("condition") == []


def test_a_launch_t3_code_refuses_leaves_no_worktree_or_branch(kitchen):
    approved(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    kitchen.poll()
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the launch"]
    assert crew_trees(kitchen, "alpha") == ([], "")
    assert not t3_tree(kitchen, "alpha").exists()


def test_a_base_origin_lacks_is_a_gate_with_no_launch_and_no_branch(kitchen):
    """A row whose pull request goes against a branch origin does not have gets no worktree."""
    stored = complete("alpha").replace(
        "Pull request: open one when done", "Pull request: open one against release/x"
    )
    queued(kitchen, "alpha", stored)
    kitchen.poll()
    assert kitchen.lines("condition") == ["condition alpha: the crew's worktree could not be made"]
    assert kitchen.t3.launches == [] and crew_trees(kitchen, "alpha") == ([], "")
