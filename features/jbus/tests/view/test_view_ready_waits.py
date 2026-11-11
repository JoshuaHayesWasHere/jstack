"""A ready row that dispatch passed over says the reason dispatch gave it, and what it waits on."""

import pytest

from view.scene import row, tasks


@pytest.mark.parametrize(
    ("why", "waits"),
    [
        ("max_running is 1 across all projects", "a slot"),
        ("max_per_home is 1 in the polish home", "a slot"),
        ("max_per_project is 3 in demo", "a slot"),
        ("a gate held back while every slot is taken: branch x is there", "a slot"),
        ("no slot", "a slot"),
        ("waiting for room on the machine", "room on the machine"),
        (
            "waiting for room on the machine: load 30.00 is at or over 85% of 12 cores",
            "room on the machine",
        ),
        ("waiting: /tmp at 91% of its quota", "room on the machine"),
        ("no launch: every instance is capped", "room on the machine"),
    ],
)
def test_a_ready_row_held_by_a_cap_or_by_room_says_why_and_what_it_waits_on(
    scene, served, why, waits
):
    scene.queue([row("fig-jam", why=why)])
    said = tasks(served.json("/state.json?project=demo"))["fig-jam"]["state"]
    assert (said["kind"], said["say"], said["waits"]) == ("ready", why, waits)
