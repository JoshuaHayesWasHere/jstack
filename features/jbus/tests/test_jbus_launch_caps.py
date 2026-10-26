"""A pass launches at most `max_per_home` crews out for each home and `max_per_project` for each
project, beside `max_running` for the machine. A crew out counts toward the home its queued brief
names (`jbriefs.home.home_of`), and a scout or a reviewer counts toward neither. Like
`test_jbus_queue.py`, the tests run the real pass against a faked T3 Code server, `gh` and
`jmerge`."""

import pytest

import jbus
import test_jbus_scout as scout
from test_jbus_kitchen import Kitchen
from test_jbus_queue import SINCE, add, brief, rows

SCOPES = ("flow", "jview", "macos", "infra")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def scoped(kitchen, *names):
    """Make a scoped home for each name: a directory beside the root home's files with a
    `home-id`."""
    for name in names:
        (kitchen.home / name).mkdir()
        (kitchen.home / name / "home-id").write_text(f"mcp:{name}-home\n")


def queue(kitchen, slug, home="", priority=1, approve=True):
    """Queue a row whose brief belongs to `home`, a scope's name, or to the root home."""
    text = brief(slug)
    if home:
        text = text.replace("Home: mcp:a-home", f"Home: {home}")
    add(kitchen, slug, priority=priority, approve=approve, text=text)


def out(kitchen, slug, home=""):
    """Put a crew out for a row of `home`: its brief is queued, and its thread is running."""
    queue(kitchen, slug, home, approve=False)
    kitchen.t3.thread(slug, "running")


def launched(kitchen):
    crews = (one["title"] for one in kitchen.t3.launches if one["title"].startswith("crew: "))
    return [title.removeprefix("crew: ") for title in crews]


def capped(said, key):
    return [line for line in said if line.startswith(f"{key} is ")]


def test_one_home_launches_six_and_the_rest_wait_naming_the_home(kitchen):
    kitchen.config(max_running=40)
    slugs = [f"r{place}" for place in range(1, 9)]
    for place, slug in enumerate(slugs, start=1):
        queue(kitchen, slug, priority=place)

    said = kitchen.poll()

    assert launched(kitchen) == slugs[:6]
    assert capped(said, "max_per_home") == [
        f"max_per_home is 6 in the root home: r7 waits, {SINCE}",
        f"max_per_home is 6 in the root home: r8 waits, {SINCE}",
    ]
    assert capped(said, "max_running") == [] and capped(said, "max_per_project") == []
    assert [rows(kitchen)[slug]["status"] for slug in slugs[6:]] == ["queued", "queued"]


def test_five_homes_of_one_project_launch_24_and_the_rest_wait_naming_the_project(kitchen):
    kitchen.config(max_running=40)
    scoped(kitchen, *SCOPES)
    homes = ("", *SCOPES)
    for place in range(1, 7):
        for home in homes:
            queue(kitchen, f"{home or 'root'}{place}", home, priority=place)

    said = kitchen.poll()

    assert len(launched(kitchen)) == 24
    for home in homes:
        mine = [slug for slug in launched(kitchen) if slug.startswith(home or "root")]
        assert len(mine) <= 6
    waits = capped(said, "max_per_project")
    assert len(waits) == 6
    assert all(line.startswith("max_per_project is 24 in demo: ") for line in waits)
    assert {line.split(": ")[1].split()[0] for line in waits} == {
        f"{home or 'root'}{place}" for place in range(1, 7) for home in homes
    } - set(launched(kitchen))
    assert capped(said, "max_per_home") == []


def test_the_root_and_each_scope_count_their_own_crews_out(kitchen):
    kitchen.config(max_running=8)
    scoped(kitchen, "flow")
    for place in range(6):
        out(kitchen, f"flow-out{place}", "flow")
    queue(kitchen, "flow1", "flow", priority=1)
    queue(kitchen, "root1", priority=2)

    said = kitchen.poll()

    assert launched(kitchen) == ["root1"]
    assert capped(said, "max_per_home") == [
        f"max_per_home is 6 in the flow home: flow1 waits, {SINCE}"
    ]


def test_the_machine_cap_still_holds_over_every_home(kitchen):
    kitchen.config(max_running=3)
    scoped(kitchen, "flow")
    for place in range(1, 4):
        queue(kitchen, f"flow{place}", "flow", priority=place)
        queue(kitchen, f"root{place}", priority=place)

    said = kitchen.poll()

    assert len(launched(kitchen)) == 3
    assert len(capped(said, "max_running")) == 3
    assert capped(said, "max_per_home") == [] and capped(said, "max_per_project") == []


def test_at_both_caps_a_scout_launches_a_reviewer_is_not_counted_and_a_crew_row_waits(kitchen):
    kitchen.config(max_running=40, max_per_home=2, max_per_project=3)
    scoped(kitchen, "flow")
    out(kitchen, "flow-out1", "flow")
    out(kitchen, "flow-out2", "flow")
    kitchen.t3.thread("ignored", "running", title="review: flow-out1, 1")
    queue(kitchen, "flow1", "flow", priority=1)
    queue(kitchen, "root1", priority=2)
    queue(kitchen, "root2", priority=3)
    assert scout.add(kitchen, "look")[0] == 0
    assert scout.approve(kitchen, "look")[0] == 0

    said = kitchen.poll()

    assert launched(kitchen) == ["root1"]
    assert [one["title"] for one in scout.launches(kitchen)] == ["scout: look"]
    assert capped(said, "max_per_home") == [
        f"max_per_home is 2 in the flow home: flow1 waits, {SINCE}"
    ]
    assert capped(said, "max_per_project") == [
        f"max_per_project is 3 in demo: root2 waits, {SINCE}"
    ]


def test_the_caps_default_to_6_and_24(kitchen):
    config = jbus.load(kitchen.config_dir)
    assert (config.max_per_home, config.max_per_project) == (6, 24)
    kitchen.config(max_per_home=2, max_per_project=5)
    config = jbus.load(kitchen.config_dir)
    assert (config.max_per_home, config.max_per_project) == (2, 5)


@pytest.mark.parametrize("key", ["max_per_home", "max_per_project"])
@pytest.mark.parametrize("written", [0, -1, "six"])
def test_a_cap_that_is_not_a_count_of_1_or_more_is_refused(kitchen, key, written):
    kitchen.config(**{key: written})
    with pytest.raises(jbus.Refused) as refused:
        jbus.load(kitchen.config_dir)
    path = kitchen.config_dir / "config.toml"
    assert str(refused.value) == f"refused: {key} in {path} is {written!r}, and it is 1 or more"
