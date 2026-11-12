"""A scoped home's own send to the root is refused, and the refusal names the one stop jbus takes:
`jbus stop --holds <case>`, a one-way door from the gates table. Anything else the home tells the
user directly from its own thread (settled with the user on 2026-11-08: only a one-way door goes
up to the root). The refusal named a stop with no `--holds`, which `jbus stop` refuses.

The root's own send to a scope is refused too, and its refusal names `jbus tell`, which carries the
root's own words to the scope signed as the root's (rh-root-tell): before it, only an answer to a
stop carried the root's words down."""

import pytest

from jbriefs import sends

ROOT = "mcp:the-root"
FLOW = "mcp:the-flow-home"


@pytest.fixture
def state(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "flow").mkdir()
    (tmp_path / "flow" / "plan.md").write_text("# a plan\n")
    (tmp_path / "home-id").write_text(f"{ROOT}\n")
    (tmp_path / "flow" / "home-id").write_text(f"{FLOW}\n")
    return tmp_path


def test_a_scoped_homes_send_to_the_root_names_a_stop_for_a_one_way_door_only(state):
    said = sends.refusal(state, FLOW, ROOT)
    assert "--holds <case>" in said, said
    assert "features/home/templates/gates.md" in said, said
    assert "one-way door" in said, said
    assert "tell the user directly from this home's own thread" in said, said


def test_the_roots_send_to_a_scope_names_jbus_tell_for_its_own_words(state):
    said = sends.refusal(state, ROOT, FLOW)
    assert '`jbus tell flow "<text>" --from <this home\'s id>`' in said, said
    assert "signed as the root's" in said, said
    assert "jbus word --to <project> --message <thread>/<message> --scope flow" in said, said
