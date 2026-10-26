"""The Throughput drawer in the browser: opened cold from its link, it draws a bar for each of
the last seven days with its count, and the total. `test_view_page_panels` holds that the first
screen opens it."""

from datetime import timedelta

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, walked
from view.scene import NOW, ago

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]

ROUTE = "#/demo/throughput"


def merges(scene):
    """Three merges in the last two days, and one ten days back, which no bar counts."""
    scene.merged(ago(days=10), ago(hours=26), ago(hours=2), ago(hours=1))


def test_the_drawer_opens_cold_and_draws_each_day_with_its_count_and_the_total(scene, tmp_path):
    merges(scene)
    (first,) = walked(scene, tmp_path, ROUTE, ["look"])
    assert first["open"] is True
    assert first["hash"] == ROUTE
    assert first["title"] == "Merges by day"
    assert first["notice"].lower().startswith("the last 7 days 3 merges")
    days = [(NOW - timedelta(days=back)).astimezone() for back in range(6, -1, -1)]
    for one in days:
        assert one.strftime("%m-%d") in first["said"]
    assert "today" in first["said"]
