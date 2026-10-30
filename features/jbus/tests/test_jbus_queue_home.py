"""`jbus queue add` refuses a brief that does not say which home it is for.

A brief with no `Home:` line once landed in the root home without a word, so work meant for a
scope ran in the wrong place. The line is required: it names `root` or a scope of the project's
homes, and `--for`, where it is given, names the same home. A row already queued is not checked
again.

The tests run the real command against the kitchen.
"""

import json

import pytest

from jbus.view.homes import Homes
from test_jbus_kitchen import Kitchen, complete
from test_jbus_scout import request
from test_jbus_word import thread

ROOT, FLOW = thread("a"), thread("f")
SCOPE = "flow"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "home-id").write_text(f"{ROOT}\n")
    (made.home / SCOPE).mkdir()
    (made.home / SCOPE / "home-id").write_text(f"{FLOW}\n")
    yield made
    made.close()


def bare(slug):
    """A complete brief with its `Home:` line taken out."""
    return "".join(
        line for line in complete(slug).splitlines(keepends=True) if not line.startswith("Home:")
    )


def adds(kitchen, slug, text, *more):
    return kitchen.main("queue", "add", slug, "--priority", "1", *more, stdin=text)


def queued(kitchen):
    return [row["slug"] for row in json.loads((kitchen.state / "queue.json").read_text())]


def test_a_brief_with_no_home_line_is_refused_as_a_brief_fault(kitchen):
    code, out = adds(kitchen, "no-home", bare("no-home"))
    assert (code, out.splitlines()[:2]) == (
        1,
        [
            "refused: no-home's brief has 1 fault, and nothing is queued",
            "- no Home: line: it names root, or the scope of the home the row is for (flow)",
        ],
    )
    assert not (kitchen.state / "queue.json").exists() or "no-home" not in queued(kitchen)


def test_a_scouts_request_with_no_home_line_is_refused_too(kitchen):
    code, out = adds(kitchen, "sc-ask", request("sc-ask"))
    assert (code, out.splitlines()[0]) == (
        1,
        "refused: sc-ask's request has 1 fault, and nothing is queued",
    )


def test_a_home_line_that_names_no_scope_is_refused(kitchen):
    code, out = adds(kitchen, "to-docs", complete("to-docs", "Home: docs\n"))
    assert (code, out.splitlines()[:2]) == (
        1,
        [
            "refused: to-docs's brief has 1 fault, and nothing is queued",
            "- Home: line names docs, which is no home of demo: it names root, or the scope of "
            "the home the row is for (flow)",
        ],
    )


def test_a_home_line_that_gives_a_thread_id_is_refused(kitchen):
    code, out = adds(kitchen, "by-id", complete("by-id", f"Home: {FLOW}\n"))
    assert (code, out.splitlines()[0]) == (
        1,
        "refused: by-id's brief has 1 fault, and nothing is queued",
    )


def test_home_root_and_home_of_a_scope_are_queued(kitchen):
    assert adds(kitchen, "at-root", complete("at-root", "Home: root\n"))[0] == 0
    assert adds(kitchen, "at-flow", complete("at-flow", f"Home: {SCOPE}\n"))[0] == 0
    assert adds(kitchen, "fl-own", complete("fl-own", f"Home: {SCOPE}\n"), "--from", FLOW)[0] == 0
    assert adds(kitchen, "rt-own", complete("rt-own", "Home: root\n"), "--from", ROOT)[0] == 0
    assert queued(kitchen) == ["at-root", "at-flow", "fl-own", "rt-own"]


def test_a_home_line_and_a_for_that_differ_are_refused(kitchen):
    code, out = adds(kitchen, "to-root", complete("to-root", "Home: root\n"), "--for", SCOPE)
    assert (code, out.splitlines()[0]) == (
        1,
        "refused: --for flow, and to-root's brief is the root home's: nothing is queued",
    )
    code, out = adds(kitchen, "to-flow", complete("to-flow", f"Home: {SCOPE}\n"), "--for", "root")
    assert (code, out.splitlines()[0]) == (
        1,
        "refused: --for root, and to-flow's brief is the flow home's: nothing is queued",
    )
    assert adds(kitchen, "given", complete("given", f"Home: {SCOPE}\n"), "--for", SCOPE)[0] == 0
    assert queued(kitchen) == ["given"]


def test_a_row_queued_before_the_rule_is_not_checked_again(kitchen):
    assert adds(kitchen, "old-row", complete("old-row", "Home: root\n"))[0] == 0
    (kitchen.state / "briefs" / "old-row.md").write_text(bare("old-row"))
    assert kitchen.main("queue", "show")[0] == 0
    assert queued(kitchen) == ["old-row"]


def test_home_root_is_the_roots_and_names_no_retired_scope(kitchen):
    owner = Homes(kitchen.home, kitchen.state).owner(complete("x", "Home: root\n"))
    assert (owner.name, owner.retired) == ("", "")
