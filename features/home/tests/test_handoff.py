"""A scoped home's handoff hands each open gate of its `gates.md` to jbus, and asks no gate twice:
a gate the home asked itself, which jbus already holds as a question, stays that one question.
The test runs the handoff's archive block against the real `jbus` of `test_gates`'s kitchen."""

import pytest

from test_gates import SCOPE, SCOPED, Home, old_file, whole
from test_home_thread import block, paths
from test_jbus_kitchen import complete

AT = "2026-10-12 11:30 ET"
NOTE = "Why: the user archived it\nOut, not on the bus: none\nUncommitted: none\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    made = Home(tmp_path, monkeypatch)
    yield made
    made.kitchen.close()


def hands_off(home, thread):
    """Step 3 of the handoff, archive, run by `thread` with the block at the top."""
    found = block("handoff", 'jbus tidy files "$M/home-id"').replace("<threadId>", thread)
    return home.sh(f"{paths('handoff')}\n{found}", home.main)


def test_a_gate_the_home_asked_is_one_question_after_its_handoff(home):
    """An older home's `gates.md` kept a gate jbus refused, so the start moved the home's own gate
    to jbus and left the file: the handoff pipes the file's gates again, and the home's own is
    the question jbus already holds, not a second one under another home's name."""
    scope = home.dir / SCOPE
    old_file(home, scope, whole)
    home.kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=complete("alpha"))
    assert home.kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", AT)[0] == 0
    moved = home.moves(SCOPED)
    assert "moved: gate 3 of " in moved and "kept: " in moved
    (scope / "handoff.next.md").write_text(NOTE)

    said = hands_off(home, SCOPED)

    assert said.startswith(f"archived: scope {SCOPE} is closed"), said
    asked = [one for one in home.records() if one["question"] == "the home's own?"]
    assert [one["slug"] for one in asked] == [f"home-{SCOPE}"]
