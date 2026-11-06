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
