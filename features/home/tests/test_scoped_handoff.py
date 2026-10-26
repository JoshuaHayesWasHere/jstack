"""A handoff in a repo with a root home and a scoped one: each home's `/handoff` archives, writes
and closes in its own directory, and launches its own successor. Each test takes every block from
the handoff skill and runs it in a temporary repo that has both homes."""

import json
import os
import re

import pytest

from test_home_thread import NAME, NOTE, block
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
DONE = "## sc-last: a task with a line typed before\nStatus: done (pull request 7)\n"
SECTION_WITH_NO_SLUG = "## Order\nStatus: read this first\n"
PAGE = NOTE
SEED = 'This message was written by the previous home.\n1. The user: "keep the queue going"'
THE_HOME = "the home: start the next home, then rename and settle this thread"
CLOSED = "the home of a closed scope: start no home, then rename and settle this thread"
NOT_THE_HOME = "not the home: start nothing, tell the user"
WHERE = "printf 'write:"
ARCHIVED = re.compile(r"log/\d{4}-\d\d-\d\d-\d{4}\.md")
LAUNCH, LOOKUP, RENAME, SETTLE = (
    call
    for call in CALLS
    if call.where.startswith("handoff:")
    and "<model selection>" not in call.written
    and call.tool not in ("t3_thread_send", "update_scheduled_task")
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

    def closes(self, thread):
        """Run step 6, the block that says who starts the next home, and return the lines it
        prints."""
        ran = self.does('rm -f "$M/home-id"', thread)
        assert ran.returncode == 0
        return ran.stdout.splitlines()

    def hands_off(self, thread, own):
        """Run a handoff's steps on disk, in order: find the home, write the note, close. The test
        gives the close no reply from `list_scheduled_tasks`, so the result has no lines about the
        scheduled tasks.
        """
        found = self.does(WHERE, thread).stdout.splitlines()
        (own / "handoff.next.md").write_text(PAGE)
        said = self.closes(thread)
        return found, [line for line in said if not line.startswith("not read:")]


@pytest.fixture
def homes(tmp_path):
    return HandingOff(tmp_path)


def own(directory):
    return {name: (directory / name).read_bytes() for name in FILES_OF_ONE_HOME}


def directories(homes):
    return {ROOT: (homes.home_dir, homes.scope_dir), SCOPED: (homes.scope_dir, homes.home_dir)}


@pytest.mark.parametrize("thread", [SCOPED, ROOT])
def test_a_handoff_archives_writes_and_closes_in_its_own_homes_directory(homes, thread):
    mine, theirs = directories(homes)[thread]
    before, others, last = homes.state(), own(theirs), (mine / "handoff.md").read_bytes()
    name = "" if mine == homes.home_dir else f"{SCOPE}/"

    found, said = homes.hands_off(thread, mine)

    assert found == [
        "root" if mine == homes.home_dir else f"scope {SCOPE}",
        f"write: {mine}/handoff.next.md",
    ]
    assert said[0] == THE_HOME
    assert own(theirs) == others
    changed = homes.changed(before)
    (archived,) = [path for path in changed if ARCHIVED.fullmatch(path.removeprefix(name))]
    assert sorted(changed) == sorted([archived, f"{name}handoff.md", f"{name}home-id"])
    assert (homes.home_dir / archived).read_bytes() == last
    assert (mine / "handoff.md").read_text() == f"{PAGE}\nWas home: {thread}\n"
    assert not (mine / "home-id").exists()


@pytest.mark.parametrize("thread", [UNFILLED, "mcp:a-home-that-handed-off", "<>", SCOPE])
def test_a_handoff_by_a_thread_that_is_no_home_writes_nothing_and_says_so(homes, thread):
    before = homes.state()
    ran = homes.does(WHERE, thread)
    assert ran.returncode == 1
    assert ran.stdout == (
        f"no home: thread {thread} is no home of {NAME} now, its id is in no home-id "
        f"under {homes.home_dir}. Nothing is written.\n"
    )
    ran = homes.does('rm -f "$M/home-id"', thread)
    unfilled = "<" in thread or ">" in thread
    assert ran.returncode == (1 if unfilled else 0)
    assert ran.stdout.startswith("not known: " if unfilled else NOT_THE_HOME)
    assert homes.changed(before) == []


def test_a_session_with_no_id_writes_the_roots_handoff_and_starts_no_home(homes):
    before, others = homes.state(), own(homes.scope_dir)
    found, said = homes.hands_off("", homes.home_dir)
    assert found[0] == "root"
    assert said == [NOT_THE_HOME]
    assert own(homes.scope_dir) == others
    (archived,) = [path for path in homes.changed(before) if ARCHIVED.fullmatch(path)]
    assert homes.changed(before) == sorted(["handoff.md", archived])
    assert (homes.home_dir / "handoff.md").read_text() == PAGE


@pytest.mark.parametrize("thread", ["", ROOT, SCOPED, UNFILLED, "mcp:no-home", "<>", SCOPE])
def test_the_handoff_finds_a_home_where_the_home_skill_finds_it(homes, thread):
    shows = 'printf "%s" "$M"'
    asked = block("home", 'echo "no home:').replace("<threadId>", thread)
    at_home = homes.run("home", f"{asked}\n{shows}", homes.main, None)
    here = homes.run("handoff", f"this_home '{thread}'\n{shows}", homes.main)
    assert here.stdout == at_home.stdout
    found = {"": homes.home_dir, ROOT: homes.home_dir, SCOPED: homes.scope_dir}.get(thread)
    assert here.stdout == str(found) if found else here.stdout.startswith("no home: ")


@pytest.mark.parametrize(
    ("thread", "typed", "title"),
    [
        (ROOT, "", f"home: {NAME}"),
        (SCOPED, f"{SCOPE} ", f"home: {NAME} {SCOPE}"),
    ],
)
def test_each_home_launches_its_own_successor(homes, thread, typed, title):
    mine, _ = directories(homes)[thread]
    _, (_, *printed) = homes.hands_off(thread, mine)
    assert printed == [f"title: {title}", f"message: /home {typed}<seed>"]
    message = printed[1].removeprefix("message: ")

    written = LAUNCH.written.replace("<title>", title)
    assert '"/home <seed>"' in written
    written = written.replace("/home <seed>", message).replace("<seed>", json.dumps(SEED)[1:-1])
    given = json.loads(written)
    assert errors(LAUNCH, given) == []
    assert given == {
        "title": title,
        "workspaceStrategy": {"type": "root"},
        "message": f"/home {typed}{SEED}",
    }
    which = "root" if mine == homes.home_dir else f"scope {SCOPE}"
    assert homes.which_home(given["message"].removeprefix("/home ")) == [which, f"title: {title}"]
    before = homes.state()
    homes.home_starts("mcp:the-next-home", given["message"].removeprefix("/home "))
    assert (mine / "home-id").read_text() == "mcp:the-next-home\n"
    assert len(homes.changed(before)) == 1

    assert json.loads(LOOKUP.written.replace("<title>", title)) == {"titleContains": title}
    renamed = json.loads(RENAME.written.replace("<title>", title).replace("<date>", "2026-10-11"))
    assert renamed == {"action": "rename", "title": f"{title} (handed off 2026-10-11)"}
    assert errors(RENAME, renamed) == []


def jbus_says(homes, monkeypatch, said, code=0):
    """Put a `jbus` on PATH that prints `said` and ends `code`, for what `jbus out` answers."""
    stub = homes.user / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "jbus").write_text(f"#!/bin/sh\nprintf '%s' '{said}'\nexit {code}\n")
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.parametrize("plan", ["", SECTION_WITH_NO_SLUG])
def test_a_scoped_home_whose_plan_has_no_open_entry_launches_no_successor(homes, plan, monkeypatch):
    jbus_says(homes, monkeypatch, "")
    (homes.scope_dir / "plan.md").write_text(f"# the second home: plan\n\n{plan}")
    before, root = homes.state(), own(homes.home_dir)
    _, said = homes.hands_off(SCOPED, homes.scope_dir)
    assert said == [CLOSED, f"title: home: {NAME} {SCOPE}"]
    page = (homes.scope_dir / "handoff.md").read_text()
    assert page.startswith(PAGE)
    closed, was = page.removeprefix(PAGE).strip().split("\n\n")
    assert re.fullmatch(r"Scope closed: \d{4}-\d\d-\d\d, .+", closed)
    assert was == f"Was home: {SCOPED}"
    assert not (homes.scope_dir / "home-id").exists()
    assert own(homes.home_dir) == root
    assert all(path.startswith(f"{SCOPE}/") for path in homes.changed(before))


@pytest.mark.parametrize(
    ("said", "code", "kept"),
    [
        ("out sc-crew: row launched", 0, ["kept open: out sc-crew: row launched"]),
        ("unknown: the last pass is old", 1, ["kept open: unknown: the last pass is old"]),
        ("", 127, ["kept open: jbus could not say what second has out"]),
    ],
    ids=["something out", "jbus cannot say", "no jbus"],
)
def test_a_scoped_home_with_no_open_entry_and_something_out_stays_open(
    homes, monkeypatch, said, code, kept
):
    """The scope's plan has no open entry, and jbus says it still has something out, or cannot
    say: the scope is not closed, a next home starts, and the block says why."""
    jbus_says(homes, monkeypatch, said, code)
    (homes.scope_dir / "plan.md").write_text("# the second home: plan\n")
    _, said_back = homes.hands_off(SCOPED, homes.scope_dir)
    assert said_back[:2] == [THE_HOME, *kept]
    assert "Scope closed:" not in (homes.scope_dir / "handoff.md").read_text()


@pytest.mark.parametrize(
    "plan", [OPEN, DONE, DONE + "\n" + SECTION_WITH_NO_SLUG, "## sc-bare: no stage yet\n"]
)
def test_a_scoped_home_with_an_open_entry_starts_the_next_one(homes, plan):
    (homes.scope_dir / "plan.md").write_text(f"# the second home: plan\n\n{plan}")
    _, said = homes.hands_off(SCOPED, homes.scope_dir)
    assert said[0] == THE_HOME
    assert "Scope closed" not in (homes.scope_dir / "handoff.md").read_text()


def test_the_root_home_is_never_closed(homes):
    (homes.home_dir / "plan.md").write_text("# the root home: plan\n")
    _, said = homes.hands_off(ROOT, homes.home_dir)
    assert said[0] == THE_HOME
    assert "Scope closed" not in (homes.home_dir / "handoff.md").read_text()


def test_the_next_home_of_each_starts_from_its_own_handoff_and_rewrites_no_brief(homes):
    sent = [
        homes.sent("tasks", "root-out"),
        homes.sent("tasks", "sc-out", f"Home: {SCOPE}"),
        homes.sent("tasks", "sc-before", f"Home: {SCOPED}"),
    ]
    before = [path.read_bytes() for path in sent]
    homes.hands_off(SCOPED, homes.scope_dir)
    homes.hands_off(ROOT, homes.home_dir)
    assert homes.home_starts("mcp:next-root") == ""
    assert homes.home_starts("mcp:next-scoped", SCOPE) == ""
    assert [path.read_bytes() for path in sent] == before
    assert LAST_ROOT not in (homes.home_dir / "handoff.md").read_text()
    assert LAST_SCOPED not in (homes.scope_dir / "handoff.md").read_text()
