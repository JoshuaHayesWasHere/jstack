"""Each small job jbus repeats across its senders is done one way, in one place (fl-sub-one-way).

jbus asks "is this thread at work?", "was this key sent?", "what does this row's brief say?" and
"which threads does T3 Code list?" in many modules. Each question has one answer: `watch.at_work`,
`wake.Box.sent`, `watch.task_brief` and `t3.listed`, and each lock of a state file is taken by
`jbus.locked`, which is the core's (`jsettings.store.locked`). The scan reads the package's code,
not its prose, so a later rule built on one of these moves every caller at once.
"""

import ast
from pathlib import Path

import pytest

from jbus import watch

PACKAGE = Path(watch.__file__).parent


def modules():
    """Each module of the package, by its path from the package, with its parsed tree."""
    return {
        str(path.relative_to(PACKAGE)): ast.parse(path.read_text())
        for path in sorted(PACKAGE.rglob("*.py"))
    }


def constants(tree, value):
    return [one for one in ast.walk(tree) if isinstance(one, ast.Constant) and one.value == value]


def test_only_the_box_reads_the_keys_that_were_sent():
    """`wake.Box.sent` renames the kinds of old keys, so a module that read `sent.json` itself
    would see a key under a name no other module uses. The bus panel of `jbus view` shows the file
    as it is kept, and is the one reader that is no part of a pass."""
    readers = [name for name, tree in modules().items() if constants(tree, "sent.json")]
    assert readers == ["view/panels/bus/panel.py", "wake.py"]


def _live_outside_at_work(name, tree):
    """The lines of `name` that test a status against `watch.LIVE` anywhere but `watch.at_work`."""
    found = []
    if name == "watch.py":
        inside = {
            id(one)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "at_work"
            for one in ast.walk(node)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and id(node) not in inside:
                names = [one.id for one in node.comparators if isinstance(one, ast.Name)]
                if "LIVE" in names:
                    found.append(node.lineno)
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "jbus.watch":
            found += [node.lineno for one in node.names if one.name == "LIVE"]
        if isinstance(node, ast.Attribute) and node.attr == "LIVE":
            if isinstance(node.value, ast.Name) and node.value.id == "watch":
                found.append(node.lineno)
    return found


def test_only_at_work_tests_a_thread_against_live():
    found = {
        name: lines
        for name, tree in modules().items()
        if (lines := _live_outside_at_work(name, tree))
    }
    assert found == {}


@pytest.mark.parametrize(
    ("name", "home"),
    [("task_brief", "watch.py"), ("locked", None), ("home_thread", "watch.py")],
)
def test_each_shared_job_has_one_definition(name, home):
    """A job of jbus's own is defined in its one module, and one the core holds in none."""
    defined = [
        where
        for where, tree in modules().items()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert defined == ([home] if home else [])


@pytest.mark.parametrize("copy", ["_brief", "_locked"])
def test_no_module_keeps_its_own_copy(copy):
    copies = [
        where
        for where, tree in modules().items()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == copy
    ]
    assert copies == []


def test_only_locked_and_the_locks_of_their_own_take_a_flock():
    """A state file's lock is `jbus.locked`, so a new one does not open and flock its own. The
    pass lock of `poll` and the queue's lock are `jbus.locked` too, and the snapshot keeps its
    lock, which waits for a time and then gives up."""
    takers = [
        name
        for name, tree in modules().items()
        if any(isinstance(node, ast.Attribute) and node.attr == "flock" for node in ast.walk(tree))
    ]
    assert takers == ["snapshot.py"]


def test_only_listed_pages_the_threads():
    """A second loop over T3 Code's `nextCursor` would page the list its own way."""
    pagers = [name for name, tree in modules().items() if constants(tree, "nextCursor")]
    assert pagers == ["t3.py"]


CREW = watch.TITLE + "alpha"


def thread(status, title=CREW, **more):
    return {"threadId": "mcp:t", "status": status, "title": title, **more}


@pytest.mark.parametrize("status", watch.LIVE)
def test_a_thread_that_is_starting_running_or_waiting_is_at_work(status):
    assert watch.at_work([thread(status)])
    assert watch.at_work([thread("completed"), thread(status)])


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted", "cancelled", None])
def test_a_thread_that_ended_or_says_no_status_is_not_at_work(status):
    assert not watch.at_work([thread(status)])
    assert not watch.at_work([])


def test_a_settled_thread_is_at_work_only_where_the_caller_counts_settled_threads():
    settled = thread("running", settled=True)
    assert not watch.at_work([settled])
    assert watch.at_work([settled], settled_too=True)


def test_a_title_picks_the_slug_s_own_thread_and_no_longer_slug():
    assert watch.at_work([thread("running", title=f"{CREW} ")], CREW)
    assert not watch.at_work([thread("running", title=f"{CREW}-two")], CREW)
    assert not watch.at_work([thread("running", title=watch.TITLE + "beta")], CREW)
