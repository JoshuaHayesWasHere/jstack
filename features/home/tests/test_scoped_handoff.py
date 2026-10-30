"""A handoff in a repo with a root home and a scoped one: each home's `/handoff` archives it in its
own directory and starts no home after it. A scoped home's scope is closed, and what it had out is
listed as the root home's. Each test takes every block from the handoff skill and runs it in a
temporary repo that has both homes."""

import json
import os
import re

import pytest

from test_home_thread import NAME, block
from test_scoped_home import (
    FILES_OF_ONE_HOME,
    LAST_ROOT,
    LAST_SCOPED,
    ROOT,
    SCOPE,
    SCOPED,
    UNFILLED,
    Homes,
)
from test_tool_calls import CALLS, errors

OPEN = "## sc-next: a task still to do\nStage: planned\nDone when:\n- it works\n"
NOTE = "Why: the user archived it\nOut, not on the bus: none\nUncommitted: none\n"
ARCHIVED_SCOPE = (
    f"archived: scope {SCOPE} is closed, and what it had out is the root home's. Start no home:"
    " switch off its scheduled tasks, tell the user, then rename and settle this thread"
)
ARCHIVED_ROOT = (
    f"archived: the root home is archived, and {NAME} has no home until someone types /home."
    " Start no home: switch off its scheduled tasks, tell the user, then rename and settle this"
    " thread"
)
WHERE = "printf 'write:"
CLOSE = 'jbus forget "$M/home-id"'
KEPT = re.compile(r"log/\d{4}-\d\d-\d\d-\d{4}(\d\d)?\.md")
RENAME, SETTLE = (
    call
    for call in CALLS
    if call.where.startswith("handoff:") and call.tool in ("t3_thread_update", "t3_thread_organize")
)


class HandingOff(Homes):
    """Both homes started, each with an open entry in its plan."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        for own in (self.home_dir, self.scope_dir):
            with (own / "plan.md").open("a") as plan:
                plan.write(f"\n{OPEN}")
        self.home_starts(ROOT)
        self.home_starts(SCOPED, SCOPE)

    def does(self, holding, thread):
        """One block of the handoff skill, run by `thread` in one call with the block at the
        top."""
        found = block("handoff", holding)
        assert "<threadId>" in found
        return self.run("handoff", found.replace("<threadId>", thread), self.main)

    def archives(self, thread, own):
        """Run a handoff's steps on disk, in order: find the home, write the note, archive. The
        test gives the archive no reply from `list_scheduled_tasks`, so the result has no lines
        about the scheduled tasks."""
        found = self.does(WHERE, thread).stdout.splitlines()
        (own / "handoff.next.md").write_text(NOTE)
        ran = self.does(CLOSE, thread)
        assert (ran.returncode, ran.stderr) == (0, ""), ran.stdout
        return found, [line for line in ran.stdout.splitlines() if not line.startswith("not read:")]


@pytest.fixture
def homes(tmp_path):
    return HandingOff(tmp_path)


def jbus_says(homes, monkeypatch, said, code=0):
    """Put a `jbus` on PATH that prints `said` and ends `code`, for what `jbus out` answers."""
    stub = homes.user / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "jbus").write_text(f"#!/bin/sh\nprintf '%s\\n' '{said}'\nexit {code}\n")
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")


def own(directory):
    return {name: (directory / name).read_bytes() for name in FILES_OF_ONE_HOME}


def test_a_scoped_home_is_archived_in_its_own_directory_and_its_scope_closed(homes, monkeypatch):
    jbus_says(homes, monkeypatch, "")
    before, root = homes.state(), own(homes.home_dir)
    last = (homes.scope_dir / "handoff.md").read_bytes()
    plan = (homes.scope_dir / "plan.md").read_bytes()

    found, said = homes.archives(SCOPED, homes.scope_dir)

    assert found == [f"scope {SCOPE}", f"write: {homes.scope_dir}/handoff.next.md"]
    (kept,) = [
        path for path in homes.changed(before) if KEPT.fullmatch(path.removeprefix(f"{SCOPE}/"))
    ]
    assert said == [
        ARCHIVED_SCOPE,
        f"note: {homes.home_dir / kept}",
        "Moved to the root: none",
        f"title: home: {NAME} {SCOPE}",
    ]
    assert own(homes.home_dir) == root
    before_note = kept.removesuffix(".md") + "-before.md"
    assert homes.changed(before) == sorted(
        [
            kept,
            before_note,
            f"{SCOPE}/handoff.md",
            f"{SCOPE}/home-id",
            f"{SCOPE}/plan.md",
            f"{SCOPE}/plan-archived.md",
        ]
    )
    assert (homes.home_dir / before_note).read_bytes() == last
    assert (homes.scope_dir / "plan-archived.md").read_bytes() == plan
    note = (homes.home_dir / kept).read_text()
    assert note.startswith(NOTE)
    assert re.search(
        r"\nArchived: \d{4}-\d\d-\d\d, and no home was started after this one\.\n", note
    )
    assert note.endswith(f"\nWas home: {SCOPED}\n")
    for gone in ("home-id", "handoff.md", "plan.md", "handoff.next.md"):
        assert not (homes.scope_dir / gone).exists()


def test_the_root_home_is_archived_and_the_repo_has_no_home(homes, monkeypatch):
    jbus_says(homes, monkeypatch, "out fix-login: row launched")
    before, scoped = homes.state(), own(homes.scope_dir)

    _, said = homes.archives(ROOT, homes.home_dir)

    assert said[0] == ARCHIVED_ROOT
    assert said[2:] == [
        "Left with no home:",
        "- out fix-login: row launched",
        f"title: home: {NAME}",
    ]
    assert own(homes.scope_dir) == scoped
    assert (homes.home_dir / "plan.md").exists()
    assert not (homes.home_dir / "home-id").exists()
    assert all(not path.startswith(f"{SCOPE}/") for path in homes.changed(before))


@pytest.mark.parametrize(
    ("said", "code", "listed"),
    [
        (
            "out sc-crew: row launched\nout question 4: tea or coffee?",
            0,
            [
                "Moved to the root:",
                "- out sc-crew: row launched",
                "- out question 4: tea or coffee?",
            ],
        ),
        (
            "unknown: the last pass is old",
            1,
            ["Moved to the root:", "- not known, jbus said: unknown: the last pass is old"],
        ),
    ],
    ids=["something out", "jbus cannot say"],
)
def test_what_a_scope_had_out_is_listed_as_moved_and_the_scope_is_archived_all_the_same(
    homes, monkeypatch, said, code, listed
):
    jbus_says(homes, monkeypatch, said, code)
    _, said_back = homes.archives(SCOPED, homes.scope_dir)
    assert said_back[0] == ARCHIVED_SCOPE
    assert said_back[2:-1] == listed
    kept = [
        path
        for path in (homes.scope_dir / "log").iterdir()
        if path.read_text().endswith(f"Was home: {SCOPED}\n")
    ]
    assert len(kept) == 1
    assert "\n".join(listed) in kept[0].read_text()
    assert not (homes.scope_dir / "plan.md").exists()


@pytest.mark.parametrize("thread", [SCOPED, ROOT])
def test_an_archive_run_again_changes_nothing_and_says_archived_before(homes, monkeypatch, thread):
    jbus_says(homes, monkeypatch, "")
    mine = homes.scope_dir if thread == SCOPED else homes.home_dir
    _, first = homes.archives(thread, mine)
    after = homes.state()
    found = homes.does(WHERE, thread)
    assert found.stdout.startswith("archived before: ")
    again = homes.does(CLOSE, thread)
    assert again.returncode == 0
    lines = [line for line in again.stdout.splitlines() if not line.startswith("not read:")]
    assert lines == [first[0].replace("archived: ", "archived before: ", 1), *first[1:]]
    assert homes.changed(after) == []


def test_a_run_cut_off_before_it_removed_home_id_keeps_one_note(homes, monkeypatch):
    """A run cut off after it kept the note and before it removed `home-id`: the next run keeps
    that note, with what was out then, and writes no second one."""
    jbus_says(homes, monkeypatch, "out sc-crew: row launched")
    homes.archives(SCOPED, homes.scope_dir)
    (homes.scope_dir / "home-id").write_text(f"{SCOPED}\n")
    (homes.scope_dir / "plan-archived.md").rename(homes.scope_dir / "plan.md")
    (homes.scope_dir / "handoff.next.md").write_text(NOTE)
    jbus_says(homes, monkeypatch, "refused: no plan.md", 1)
    ran = homes.does(CLOSE, SCOPED)
    assert ran.stdout.startswith("archived: ")
    kept = [
        path
        for path in (homes.scope_dir / "log").iterdir()
        if f"Was home: {SCOPED}" in path.read_text()
    ]
    assert len(kept) == 1
    assert "- out sc-crew: row launched" in kept[0].read_text()
    assert not (homes.scope_dir / "home-id").exists()
    assert not (homes.scope_dir / "plan.md").exists()


@pytest.mark.parametrize("thread", [UNFILLED, "mcp:a-home-that-handed-off", "<>", SCOPE])
def test_a_handoff_by_a_thread_that_is_no_home_writes_nothing_and_says_so(homes, thread):
    before = homes.state()
    ran = homes.does(WHERE, thread)
    assert ran.returncode == 1
    assert ran.stdout == (
        f"no home: thread {thread} is no home of {NAME} now, its id is in no home-id "
        f"under {homes.home_dir}. Nothing is written.\n"
    )
    ran = homes.does(CLOSE, thread)
    assert ran.returncode == 1
    unfilled = "<" in thread or ">" in thread
    assert ran.stdout.startswith("not known: " if unfilled else "not the home: ")
    assert homes.changed(before) == []


def test_a_session_with_no_id_archives_nothing(homes):
    (homes.home_dir / "handoff.next.md").write_text(NOTE)
    before = homes.state()
    for holding in (WHERE, CLOSE):
        ran = homes.does(holding, "")
        assert ran.stdout.startswith("not known: ")
    assert homes.changed(before) == []
    assert (homes.home_dir / "home-id").exists()


@pytest.mark.parametrize("thread", ["", ROOT, SCOPED, UNFILLED, "mcp:no-home", "<>", SCOPE])
def test_the_handoff_finds_a_home_where_the_home_skill_finds_it(homes, thread):
    shows = 'printf "%s" "$M"'
    asked = block("home", 'echo "no home:').replace("<threadId>", thread)
    at_home = homes.run("home", f"{asked}\n{shows}", homes.main, None)
    here = homes.run("handoff", f"this_home '{thread}'\n{shows}", homes.main)
    assert here.stdout == at_home.stdout
    found = {"": homes.home_dir, ROOT: homes.home_dir, SCOPED: homes.scope_dir}.get(thread)
    assert here.stdout == str(found) if found else here.stdout.startswith("no home: ")


def test_the_skill_launches_nothing_and_renames_the_thread_archived():
    text = block("handoff", CLOSE)
    assert "t3_thread_launch" not in text and "message: /home" not in text
    skill = "\n".join(call.written for call in CALLS if call.where.startswith("handoff:"))
    assert "/home <seed>" not in skill
    renamed = json.loads(
        RENAME.written.replace("<title>", "home: demo").replace("<date>", "2026-10-29")
    )
    assert renamed == {"action": "rename", "title": "home: demo (archived 2026-10-29)"}
    assert errors(RENAME, renamed) == []
    assert json.loads(SETTLE.written) == {"action": "settle"}


def test_an_archived_scope_starts_again_with_home_and_its_plan_back(homes, monkeypatch):
    jbus_says(homes, monkeypatch, "")
    plan = (homes.scope_dir / "plan.md").read_bytes()
    homes.archives(SCOPED, homes.scope_dir)
    assert homes.which_home(SCOPE) == [
        f"scope {SCOPE}",
        f"title: home: {NAME} {SCOPE}",
        f"reopened: {SCOPE} was archived, and its plan is back in {homes.scope_dir / 'plan.md'}",
    ]
    assert (homes.scope_dir / "plan.md").read_bytes() == plan
    assert not (homes.scope_dir / "plan-archived.md").exists()
    homes.home_starts("mcp:the-scope-again", SCOPE)
    assert (homes.scope_dir / "home-id").read_text() == "mcp:the-scope-again\n"


def test_an_archive_rewrites_no_brief_and_leaves_no_note_a_start_reads(homes, monkeypatch):
    jbus_says(homes, monkeypatch, "")
    sent = [
        homes.sent("tasks", "root-out"),
        homes.sent("tasks", "sc-out", f"Home: {SCOPE}"),
        homes.sent("tasks", "sc-before", f"Home: {SCOPED}"),
    ]
    before = [path.read_bytes() for path in sent]
    homes.archives(SCOPED, homes.scope_dir)
    homes.archives(ROOT, homes.home_dir)
    assert [path.read_bytes() for path in sent] == before
    for mine, last in ((homes.home_dir, LAST_ROOT), (homes.scope_dir, LAST_SCOPED)):
        assert not (mine / "handoff.md").exists()
        assert any(last in path.read_text() for path in (mine / "log").iterdir())


GATE = (
    "## Gate 3: tea or coffee?\nStatus: open\nDefault: tea\nAsked by: home\nUndo: pour it\n\n"
    "## Gate 4: milk?\nStatus: answered: no\nDefault: no\nAsked by: sc-crew\nUndo: none\n"
)


def jbus_takes_gates(homes, monkeypatch, gate_code=0):
    """A `jbus` on PATH that says nothing is out, and keeps each gate piped to `jbus gate` in
    `gates.log`, answering it as a question, or refusing it with `gate_code` 1."""
    stub = homes.user / "bin"
    stub.mkdir(exist_ok=True)
    log = homes.user / "gates.log"
    (stub / "jbus").write_text(
        "#!/bin/sh\n"
        "case $1 in\n"
        f'gate) {{ echo "slug: $2"; cat; }} >> "{log}"\n'
        f'    [ {gate_code} = 0 ] || {{ echo "refused: no"; exit 1; }}\n'
        '    echo "queued: question 9" ;;\n'
        "esac\n"
    )
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    return log


def test_an_open_gate_of_an_archived_scope_becomes_a_question_of_the_root_home(homes, monkeypatch):
    log = jbus_takes_gates(homes, monkeypatch)
    (homes.scope_dir / "gates.md").write_text(GATE)
    _, said = homes.archives(SCOPED, homes.scope_dir)
    assert said[0] == ARCHIVED_SCOPE
    assert "- gate 3 of gates.md is the root home's, queued: question 9" in said
    assert log.read_text() == (
        "slug: home\n## Gate 3: tea or coffee?\nStatus: open\nDefault: tea\nAsked by: home\n"
        "Undo: pour it\n\n"
    )
    assert not (homes.scope_dir / "gates.md").exists()
    assert (homes.scope_dir / "gates-moved.md").read_text() == GATE


def test_a_gate_jbus_will_not_take_leaves_the_scope_unarchived(homes, monkeypatch):
    jbus_takes_gates(homes, monkeypatch, gate_code=1)
    (homes.scope_dir / "gates.md").write_text(GATE)
    homes.does(WHERE, SCOPED)
    (homes.scope_dir / "handoff.next.md").write_text(NOTE)
    ran = homes.does(CLOSE, SCOPED)
    assert ran.returncode == 1
    assert ran.stdout.startswith("not archived: an open gate of ")
    assert "not moved: gate 3 of gates.md, jbus said: refused: no" in ran.stdout
    for kept in ("gates.md", "home-id", "plan.md", "handoff.next.md"):
        assert (homes.scope_dir / kept).exists()
