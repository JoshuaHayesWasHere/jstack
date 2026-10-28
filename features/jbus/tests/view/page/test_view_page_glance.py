"""The glance band at the top of `#/`, in the browser: what is wrong, then what waits on the user,
each tier cut to `GLANCE_MAX` rows with the rest in Triage, one calm line where nothing is wrong
and nothing waits, and a line that says what changed since the user last looked.

The page keeps when the user last looked in the browser's store, and only while the user can see
the page: a tab nobody sees that polls does not count as a look."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from view.days import DAYS
from view.page.browser import BROWSES, LAUNCH, PATIENCE, look
from view.page.test_view_page_budgets import SCENES
from view.scene import NOW, Served, iso

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


PROBE = (Path(__file__).parent / "glance.js").read_text()


def ms(moment):
    return int(moment.timestamp() * 1000)


def glanced(scene, tmp_path, build="calm", route="#/", alter=None, at=600, budget=6000, **how):
    """What the probe of the band found on `route` of the scene that `build` makes. `how` sets
    the probe's own globals: `looked`, `hidden` and `flip`."""
    (DAYS | SCENES)[build](scene)
    said = "".join(f"window.__{key} = {json.dumps(value)};" for key, value in how.items())
    served = Served(scene)
    try:
        seen = look(
            scene,
            tmp_path,
            route=route,
            script=said + PROBE,
            port=served.port,
            alter=alter,
            at=at,
            budget=budget,
        )
    finally:
        served.close()
    assert seen["errors"] == []
    return seen


def wrongs(n):
    """A band with `n` things wrong and nothing that waits on the user."""

    def alter(nth, body):
        made = [
            {
                "tier": "wrong",
                "kind": "ci",
                "subj": f"rye-{one}",
                "cause": "check failed",
                "since": iso(NOW - timedelta(minutes=10 + one)),
                "where": "demo",
                "open": "#/demo/checks",
                "verb": "Open checks",
                "count": 1,
            }
            for one in range(n)
        ]
        moving = [one for one in body["glance"]["items"] if one["tier"] == "moving"]
        body["glance"] |= {"calm": False, "items": made + moving}
        return body

    return alter


def test_a_tier_shows_four_rows_and_says_how_many_more_wait_in_triage(scene, tmp_path):
    seen = glanced(scene, tmp_path, alter=wrongs(6))
    (tier,) = seen["band"]["tiers"]
    assert tier["head"] == "WRONG"
    assert tier["rows"] == [f"ci:rye-{one}" for one in range(4)]
    assert (tier["more"], tier["href"]) == ("2 more in Triage ›", "#/triage")
    assert seen["band"]["calm"] is None
    assert seen["band"]["head"].endswith("6 wrong")


def test_four_wrong_are_all_shown_and_send_nobody_to_triage(scene, tmp_path):
    (tier,) = glanced(scene, tmp_path, alter=wrongs(4))["band"]["tiers"]
    assert len(tier["rows"]) == 4
    assert tier["more"] is None


def test_nothing_wrong_and_nothing_waiting_is_one_calm_line(scene, tmp_path):
    """The calm scene has rows that wait on the user, so the test takes those out of the band:
    with nothing in either tier the band is its one line."""

    def calm(nth, body):
        moving = [one for one in body["glance"]["items"] if one["tier"] == "moving"]
        body["glance"] |= {"calm": True, "items": moving}
        return body

    band = glanced(scene, tmp_path, alter=calm)["band"]
    assert band["calm"].startswith("All clear: nothing wrong, nothing waits on you.")
    assert (band["tiers"], band["since"], band["moving"]) == ([], None, None)
    assert band["word"] == "MOVING" and band["head"].startswith("MOVING Slowed by ")


@pytest.mark.parametrize("route", ["#/homes", "#/demo", "#/triage", "#/nosuch"])
def test_the_band_is_only_on_the_overview(scene, tmp_path, route):
    seen = glanced(scene, tmp_path, route=route)
    assert seen["cards"] == ""


def test_since_you_looked_says_what_changed_since_the_last_look(scene, tmp_path):
    seen = glanced(scene, tmp_path, alter=wrongs(2), looked=ms(NOW - timedelta(hours=2)))
    assert seen["band"]["since"] == "Since you looked 2h00 ago: 6 merged, 2 newly wrong."
    assert seen["stamp"] == str(ms(NOW))


def test_the_band_keeps_the_since_lines_one_clock_and_drops_its_old_one(scene, tmp_path):
    """The band and the since line share one time of the last look: the band keeps no clock of
    its own, and a time the band kept in its old key before is dropped, not read."""
    looked, old = ms(NOW - timedelta(hours=2)), ms(NOW - timedelta(minutes=5))
    seen = glanced(scene, tmp_path, alter=wrongs(2), looked=looked, old=old)
    assert seen["band"]["since"] == "Since you looked 2h00 ago: 6 merged, 2 newly wrong."
    assert seen["kept"] == ["jbus.since.looked"]
    assert seen["stamp"] == str(ms(NOW))


def test_a_tab_nobody_sees_does_not_count_as_a_look(scene, tmp_path):
    """A background tab polls and draws, but the time of the last look stays where it was, so
    the tab the user opens next still says what changed."""
    looked = ms(NOW - timedelta(hours=2))
    how = {"looked": looked, "hidden": True, "at": 7000, "budget": 9000}
    seen = glanced(scene, tmp_path, alter=wrongs(2), **how)
    assert seen["stamp"] == str(looked)


def test_after_the_user_looks_away_and_back_the_line_is_about_the_new_look(scene, tmp_path):
    """The page was seen until the tab was hidden, so on its return nothing changed since: the
    line from the first look goes."""
    looked = ms(NOW - timedelta(hours=2))
    how = {"looked": looked, "flip": [1000, 2000], "at": 8000, "budget": 10000}
    seen = glanced(scene, tmp_path, alter=wrongs(2), **how)
    assert seen["band"]["since"] is None
    assert seen["stamp"] == str(ms(NOW))


@pytest.mark.parametrize("day", sorted(DAYS))
def test_the_band_draws_the_verdict_word_and_how_many_need_you(scene, tmp_path, day):
    """On each day the overview is shot over, the band draws the server's word large, its cause,
    and in the line under it the count of `needs`, the same as Needs you."""
    band = glanced(scene, tmp_path, build=day)["band"]
    served = Served(scene)
    try:
        given = served.json("/stack.json")
    finally:
        served.close()
    verdict = given["glance"]["verdict"]
    assert band["word"] == verdict["word"]
    assert band["cause"].lower() == f"{verdict['cause']}.".lower()
    assert band["needs"] == f"{len(given['needs'])} need you"
