"""A home's status, a wake and `/ketchup` open with jbus's list of what waits on the user. The tests
run the home skill's block and the ketchup skill's block as an agent reads them, against the real
`jbus needs` and a kitchen whose jbus holds a gate that holds, and the start's `## waiting on you`
part, which is the same list."""

import pytest

from test_home_start import parts
from test_home_thread import STATUS, block
from test_jbus_questions import held

NEEDS = "jbus needs"
LISTED = [
    "waiting on user: 1, in demo",
    "demo question 1: drop the old branch, it holds (deletes data) for your answer",
    "  fail-safe: the dry-run in /tmp/gone.txt",
    "  answer: reply in your own words to keep the default (the first one) or say what to do "
    "instead",
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


def test_the_ketchup_block_prints_the_same_list(bus):
    holding(bus)
    assert bus.sh(block("ketchup", NEEDS), bus.main).splitlines() == LISTED


def test_a_start_opens_its_status_with_the_same_list(bus):
    holding(bus)
    said = parts(bus.home(STATUS))
    assert said["waiting on you"] == LISTED
    assert not any(line.startswith("waiting on") for line in said["queue"])
