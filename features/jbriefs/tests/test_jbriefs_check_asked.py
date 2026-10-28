"""`jbus queue add` warns of a brief whose `Done when:` asks for a bare `make check` while the
repo's `fresh-check` names another check command. This runs the home skill's rule for a check
line. The test runs it as `features/jbus/tests/test_jbus_kitchen.py` does, with the real command
against a faked T3 Code server."""

import pytest

from test_jbus_kitchen import Kitchen
from test_jbus_queue import brief

FAST = "jgauge test-slot -- make check-fast BASE=origin/main\n"
WARNED = (
    "warning: alpha's brief's Done when: asks for `make check`, and fresh-check names the check "
    "command `make check-fast BASE=origin/main`: a check line names the check command "
    "(`fresh-check`)"
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def added(kitchen, done, check):
    if check is not None:
        (kitchen.home / "fresh-check").write_text(check)
    text = brief("alpha").replace("- it is done\n", f"- {done}\n")
    code, said = kitchen.main(
        "--project", "demo", "queue", "add", "alpha", "--priority", "1", stdin=text
    )
    assert code == 0, said
    return [line for line in said.splitlines() if line.startswith("warning:")]


@pytest.mark.parametrize("done", ["`make check` passes", "make check passes under a test slot"])
@pytest.mark.parametrize("check", [FAST, FAST.removeprefix("jgauge test-slot -- ")])
def test_a_bare_make_check_is_warned_of_when_fresh_check_names_another_command(
    kitchen, done, check
):
    """The check command is the first line of `fresh-check`, with the slot it takes left off,
    and a `notes.md` that names nothing changes nothing."""
    (kitchen.home / "notes.md").write_text("- Nothing about a check here.\n")
    assert added(kitchen, done, check) == [WARNED]


@pytest.mark.parametrize(
    ("done", "check"),
    [
        ("`make check-fast BASE=origin/main` passes", FAST),
        ("`make check` passes", "make check\n"),
        ("`make check` passes", "jgauge test-slot -- make check\n"),
        ("`make check` passes", ""),
        ("`make check` passes", None),
    ],
)
def test_the_check_command_or_no_fresh_check_is_not_warned_of(kitchen, done, check):
    assert added(kitchen, done, check) == []
