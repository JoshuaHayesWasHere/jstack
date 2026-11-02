"""A home's status, a wake and `/ketchup` open with jbus's list of what waits on the user. The tests
run the home skill's block and the ketchup skill's block as an agent reads them, against the real
`jbus needs` and a kitchen whose jbus holds a gate that holds, and the start's `## waiting on you`
part, which is the same list."""

import pytest

from test_home_start import parts
from test_home_thread import STATUS, as_read, block
from test_jbus_questions import held
from testing.layouts import assembled

NEEDS = "jbus needs"
LISTED = [
    "waiting on user: 1, in demo",
    "demo question 1: drop the old branch, it holds (deletes data) for your answer",
    "  fail-safe: the dry-run in /tmp/gone.txt",
    '  answer: say "demo question 1: default", or say what to do instead',
]


@pytest.fixture
def bus(tmp_path, monkeypatch):
    from test_gates import Home

    made = Home(tmp_path, monkeypatch)
    yield made
    made.kitchen.close()


def holding(bus):
    assert bus.kitchen.main("gate", "alpha", stdin=held())[0] == 0
    bus.kitchen.poll()


def test_the_home_skills_block_prints_the_gate_that_holds_and_its_reply(bus):
    holding(bus)
    assert bus.home(NEEDS).splitlines() == LISTED


def test_the_ketchup_block_prints_the_same_list(bus):
    holding(bus)
    assert bus.sh(block("ketchup", NEEDS), bus.main).splitlines() == LISTED


def test_with_nothing_open_the_block_says_nothing_waits(bus):
    bus.kitchen.poll()
    assert bus.home(NEEDS) == "nothing waits on user in any project"


def test_a_start_opens_its_status_with_the_same_list(bus):
    holding(bus)
    said = parts(bus.home(STATUS))
    assert said["waiting on you"] == LISTED
    assert not any(line.startswith("waiting on") for line in said["queue"])


def test_the_skills_say_status_a_wake_and_ketchup_open_with_the_list():
    skills = assembled() / "skills"
    home = as_read(skills / "home" / "SKILL.md")
    assert "A status reply, a `/ketchup` in a home, and any turn a wake started" in home
    told = as_read(skills / "home" / "when-a-thread-sends-a-message.md")
    assert 'First run the block of "What waits on the user"' in told
    assert 'open the reply with what the block of "What waits on the user" prints' in told
    ketchup = as_read(skills / "ketchup" / "SKILL.md")
    assert "In a home, the reply opens with what it printed" in ketchup
