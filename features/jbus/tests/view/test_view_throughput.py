"""The Throughput panel: the merges GitHub has for each of the last seven days of the user's
zone, and their total."""

from datetime import UTC, datetime, timedelta

import pytest

from view.scene import NOW, Served

ASKED = (
    "pr list --repo acme/demo --state merged --search merged:>=2026-10-05"
    " --json number,mergedAt --limit 1000"
)


@pytest.fixture
def zoned(scene, monkeypatch):
    """The server, for a user in New York: 20:00 UTC on 2026-10-12 is 16:00 there."""
    config = scene.root / "xdg"
    (config / "jstack").mkdir(parents=True)
    (config / "jstack" / "config.toml").write_text('timezone = "America/New_York"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    made = Served(scene)
    yield made
    made.close()


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def merges(scene):
    scene.merged(
        at("2026-09-30T12:00"),
        at("2026-10-06T03:00"),
        at("2026-10-06T05:00"),
        at("2026-10-10T12:00"),
        at("2026-10-12T03:30"),
        at("2026-10-12T15:00"),
        at("2026-10-12T19:00"),
    )


def test_each_of_the_seven_days_counts_the_merges_of_that_day_in_the_users_zone(scene, zoned):
    merges(scene)
    said = zoned.json("/panel/throughput.json?project=demo")["data"]["throughput"]
    assert [(one["day"], one["merged"]) for one in said["days"]] == [
        ("2026-10-06", 1),
        ("2026-10-07", 0),
        ("2026-10-08", 0),
        ("2026-10-09", 0),
        ("2026-10-10", 1),
        ("2026-10-11", 1),
        ("2026-10-12", 2),
    ]
    assert said["total"] == 4 + 1
    assert said["read"] is True
    assert said["error"] == ""


def test_github_is_asked_when_the_drawer_opens_and_its_answer_is_kept_five_minutes(
    scene, zoned
):
    merges(scene)
    for _ in range(3):
        zoned.json("/state.json?project=demo")
    assert not [one for one in scene.asked() if one.startswith("pr list")]
    for _ in range(3):
        zoned.json("/panel/throughput.json?project=demo")
    assert [one for one in scene.asked() if one.startswith("pr list")] == [ASKED]
    scene.now = NOW + timedelta(seconds=301)
    zoned.json("/panel/throughput.json?project=demo")
    assert [one for one in scene.asked() if one.startswith("pr list")] == [ASKED] * 2


def test_a_github_that_does_not_answer_is_said_and_counts_nothing(scene, zoned):
    said = zoned.json("/panel/throughput.json?project=demo")["data"]["throughput"]
    assert said["read"] is False
    assert said["error"] == "GitHub did not answer"
    assert said["total"] == 0
    assert [one["merged"] for one in said["days"]] == [0] * 7


def test_the_page_opens_the_drawer_from_the_merges_of_today(scene, zoned):
    _, _, page = zoned.ask("/")
    assert 'openBtn("throughput", ' in page
