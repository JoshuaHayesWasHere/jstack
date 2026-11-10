"""A number in a home's reply counts "today" as the view does (po-home-reply-facts).

The user read "14 PRs merged since 11:36" in a home's reply while the view said 6 merged today,
and a table cut by UTC days gave 57 where the user counted 75. The home skill's "How a turn ends"
now says a reply's "today" counts from the user's local midnight, as the view's "Merged today"
does. The test takes that rule from the skill as an agent reads it and checks its claim against
the view's own `Read.day`, in a zone where UTC's day and the user's differ.
"""

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import jsettings
from jbus.view import state
from test_home_thread import as_read
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
ZONE = ZoneInfo("America/New_York")
TODAY = re.compile(
    r'"today" starts at the user\'s local midnight, as in the view\'s "Merged today"'
)


def the_views_day(now, tmp_path):
    """The start of the day that the view's "Merged today" counts from, for a user in `ZONE`."""
    sources = SimpleNamespace(
        user=jsettings.Settings(zone=ZONE), state=lambda name: tmp_path, home=lambda name: tmp_path
    )
    read = state.Read(sources, "demo", now, runs=lambda name: {}, found=())
    return datetime.fromisoformat(read.day)


def test_a_replys_today_starts_where_the_views_merged_today_does(tmp_path):
    ends = re.search(r"^## How a turn ends\n(.*?)(?=^## )", as_read(SKILL), re.M | re.S)
    assert ends and TODAY.search(ends.group(1)), "'How a turn ends' lost its rule for a number"
    late = datetime(2026, 11, 9, 3, 30, tzinfo=UTC)
    assert the_views_day(late, tmp_path) == datetime(2026, 11, 8, tzinfo=ZONE)
    assert the_views_day(late, tmp_path) != datetime(2026, 11, 9, tzinfo=UTC)
