"""features/jbus/docs/jbus/events-and-wakes.md names the routine events, the ones `jbus digest`
puts in its `routine` list and not on the pager. The page copies that list from `digest.ROUTINE`,
so the two hold the same events."""

import re

from jbus import digest
from testing.paths import REPO

PAGE = REPO / "features" / "jbus" / "docs" / "jbus" / "events-and-wakes.md"


def listed(text):
    """The events in the code spans of the page's sentence that starts "The routine events", up to
    the words "go to"."""
    (line,) = [line for line in text.splitlines() if line.startswith("The routine events")]
    return re.findall(r"`([a-z-]+)`", line.partition(" go to ")[0])


def test_the_page_names_each_routine_event_and_no_other():
    named = listed(PAGE.read_text())
    assert sorted(named) == sorted(digest.ROUTINE)


def test_the_events_are_read_from_the_sentence_up_to_the_words_go_to():
    text = (
        "Not `stall` here.\n"
        "The routine events, `merged`, `stale` and `gate`, go to the digest's `routine` list.\n"
    )
    assert listed(text) == ["merged", "stale", "gate"]
