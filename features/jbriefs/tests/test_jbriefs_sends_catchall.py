"""The root's send to a crew of the catch-all's, `uncategorized`, is a steer while the root stands
in for it, and goes; once the catch-all has a home of its own the crew is that home's, and the
root's send is refused as one to another home's crew. A scope's send to such a crew is refused
whether the catch-all has started or not, and names the `uncategorized` home's work."""

import pytest

from jbriefs import sends

ROOT = "mcp:the-root"
FLOW = "mcp:the-flow-home"
CATCHALL = "mcp:the-catch-all"
CREW = "mcp:a-crew"


@pytest.fixture
def state(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "flow").mkdir()
    (tmp_path / "home-id").write_text(f"{ROOT}\n")
    (tmp_path / "flow" / "plan.md").write_text("# plan\n")
    (tmp_path / "flow" / "home-id").write_text(f"{FLOW}\n")
    (tmp_path / "tasks" / "alpha.md").write_text(f"# alpha\nHome: root\nThread: {CREW}\n")
    return tmp_path


def started(state):
    (state / "uncategorized").mkdir()
    (state / "uncategorized" / "home-id").write_text(f"{CATCHALL}\n")


def test_the_root_steers_a_crew_of_the_catch_all_while_it_stands_in(state):
    assert sends.refusal(state, ROOT, CREW) == ""


def test_once_the_catch_all_has_a_home_the_root_steers_its_crews_no_more(state):
    started(state)
    said = sends.refusal(state, ROOT, CREW)
    assert "a brief of the uncategorized home's" in said, said
    assert sends.refusal(state, CATCHALL, CREW) == ""


@pytest.mark.parametrize("made", [False, True], ids=["standing in", "started"])
def test_a_scopes_send_to_a_crew_of_the_catch_all_is_a_queued_row(state, made):
    if made:
        started(state)
    said = sends.refusal(state, FLOW, CREW)
    assert "a brief of the uncategorized home's" in said, said
    assert "jbus queue add" in said, said
