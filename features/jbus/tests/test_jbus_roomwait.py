"""A row's reason to wait for room keeps what `jgauge room` waits on and its limit, so two
readings of one wait give one reason, and a no whose shape jbus does not know gives the bare
`waiting for room on the machine`, since its text may carry a reading."""

import pytest

from jbus import roomwait

SAME = (
    (
        "load 30.00 is at or over 200% of 12 cores; the busiest: uv in /a (40%)",
        "load 31.00 is at or over 200% of 12 cores",
        "load is at or over 200% of 12 cores",
    ),
    ("CPU pressure 40.1 is at or over 30", "CPU pressure 52.0 is at or over 30", None),
    (
        "1.2 GB of memory available, under 2",
        "0.9 GB of memory available, under 2",
        "memory available under 2 GB",
    ),
    ("memory pressure 12.3 is at or over 10", "memory pressure 15.0 is at or over 10", None),
    (
        "the five-hour limit is 95% used, at or over 90%, and resets in 2h 3m",
        "the five-hour limit is 97% used, at or over 90%, and resets in 1h 50m",
        "the five-hour limit is at or over 90%",
    ),
    (
        "a, b are both at or over 90%: a's weekly limit is 95% used and resets in 1h",
        "a, b are both at or over 90%: b's weekly limit is 99% used and resets in 3h",
        "a, b are both at or over 90%",
    ),
)


@pytest.mark.parametrize(("one", "other", "head"), SAME)
def test_two_readings_of_one_wait_give_one_reason_with_no_reading(one, other, head):
    said = roomwait.reason(one)
    assert said == roomwait.reason(other)
    if head is not None:
        assert said == f"{roomwait.ROOM}: {head}"
    assert said.startswith(f"{roomwait.ROOM}: ")


@pytest.mark.parametrize(
    "why", ("the load or the core count could not be read", "jgauge room did not run")
)
def test_a_no_with_no_reading_is_kept_whole(why):
    assert roomwait.reason(why) == f"{roomwait.ROOM}: {why}"


def test_a_no_of_a_shape_jbus_does_not_know_is_the_bare_wait_for_room():
    assert roomwait.reason("swap 7.5 GB in use, over 4") == roomwait.ROOM
