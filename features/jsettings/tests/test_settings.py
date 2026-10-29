"""The user's name and time zone are settings. `jsettings.load` reads them from one file, and
every command runs on defaults when there is no file. The tests run as
`features/jbus/tests/test_jbus.py` runs, with the real command and the real pass against the
fakes."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from test_jbus_kitchen import NOW, RESULT, Kitchen
from test_jbus_queue import AT, add, brief, rows, sha12
from test_stall import HEAD, SAFE, URL
from testing.jstack_fixtures import NAMED


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def word(moment):
    """The abbreviation that the machine's own zone gives this time."""
    return moment.astimezone().tzname()


def test_with_no_file_every_key_has_its_default_and_no_file_is_made(jstack_config):
    jstack_config.unlink()
    user = jsettings.load()
    said = datetime(2026, 10, 12, 0, 30)
    assert (user.user, user.zone, user.label) == ("user", None, "")
    assert user.stamp(said) == f"2026-10-12 00:30 {word(said)}"
    assert user.takes(f"2026-10-12 00:30 {word(said)}")
    assert not user.takes("2026-10-12 00:30 Nowhere")
    assert not jstack_config.exists()


def test_a_good_file_gives_the_name_the_zone_and_the_label(jstack_config):
    jstack_config.write_text(NAMED)
    user = jsettings.load()
    assert (user.user, user.zone, user.label) == ("Robin", ZoneInfo("America/New_York"), "ET")
    assert (
        user.stamp(datetime(2026, 10, 12, 4, 30, tzinfo=ZoneInfo("UTC"))) == "2026-10-12 00:30 ET"
    )
    assert user.takes("2026-01-12 00:30 ET") and not user.takes("2026-01-12 00:30 EST")
    assert jsettings.load(jstack_config) == user


def test_a_zone_with_no_label_is_worded_as_the_zone_prints_it(jstack_config):
    jstack_config.write_text('timezone = "America/New_York"\n')
    user = jsettings.load()
    assert user.user == "user"
    assert user.stamp(datetime(2026, 7, 1, 16, 0, tzinfo=ZoneInfo("UTC"))) == "2026-07-01 12:00 EDT"
    assert user.takes("2026-07-01 12:00 EDT") and user.takes("2026-01-12 00:30 EST")
    assert not user.takes("2026-01-12 00:30 EDT")
    assert not user.takes("2026-13-40 00:30 EST")


def test_a_zone_is_read_on_a_machine_with_no_time_zone_database(jstack_config):
    """An empty PYTHONTZPATH imitates a machine with no /usr/share/zoneinfo. Python then has
    only the zones in the project's own packages."""
    jstack_config.write_text('timezone = "America/New_York"\n')
    ran = subprocess.run(
        [sys.executable, "-c", "import jsettings; print(jsettings.load().zone)"],
        env={**os.environ, "PYTHONTZPATH": ""},
        capture_output=True,
        text=True,
    )
    assert (ran.returncode, ran.stdout.strip(), ran.stderr) == (0, "America/New_York", "")


def test_a_python_with_no_zones_at_all_says_so_and_does_not_blame_the_name(jstack_config):
    """`install.sh` runs on a Python that has only `src`. `-S` leaves out the project's
    packages, and tzdata with them."""
    jstack_config.write_text('timezone = "America/New_York"\n')
    said = "import jsettings\ntry: jsettings.load()\nexcept jsettings.Invalid as why: print(why)"
    ran = subprocess.run(
        [sys.executable, "-S", "-c", said],
        env={
            **os.environ,
            "PYTHONTZPATH": "",
            "PYTHONPATH": str(Path(jsettings.__file__).parents[1]),
        },
        capture_output=True,
        text=True,
    )
    assert (ran.stdout, ran.stderr) == (
        f"{jstack_config} has the timezone America/New_York, and this Python has no time zone "
        "database to find it in: the system has none and tzdata is not installed\n",
        "",
    )


@pytest.mark.parametrize(
    "text, why",
    [
        ("user = ", " does not parse: "),
        ('name = "Robin"\n', " has the key name, not one of user, timezone, timezone_label"),
        ("user = 7\n", " has a user that is not one word with no comma"),
        ('user = "Robin H"\n', " has a user that is not one word with no comma"),
        ('timezone_label = ""\n', " has a timezone_label that is not one word with no comma"),
        ('timezone = "Mars/Olympus"\n', " has the timezone Mars/Olympus, not an IANA name"),
    ],
)
def test_a_bad_file_is_refused_with_the_one_line_that_says_why(kitchen, jstack_config, text, why):
    jstack_config.write_text(text)
    with pytest.raises(jsettings.Invalid) as refused:
        jsettings.load()
    said = str(refused.value)
    assert said.startswith(str(jstack_config) + why) and "\n" not in said
    assert kitchen.main("queue", "show") == (1, f"refused: {said}\n")
    assert jstack_config.read_text() == text


def test_a_file_that_cannot_be_read_is_refused(jstack_config):
    jstack_config.unlink()
    jstack_config.mkdir()
    with pytest.raises(jsettings.Invalid) as refused:
        jsettings.load()
    assert str(refused.value) == f"cannot read {jstack_config}: Is a directory"


def test_with_no_file_a_word_is_users_at_a_time_of_the_machines_zone_and_approves_a_launch(
    kitchen, jstack_config
):
    jstack_config.unlink()
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    sha = sha12(brief("alpha"))
    at = f"2026-10-11 17:58 {word(datetime(2026, 10, 11, 17, 58))}"
    out = ["queue", "remove", "beta"]
    assert kitchen.main(*out, "--by", "Robin", "--at", at)[1].startswith(
        "refused: only user removes a row, on their own words: --by user, or --message "
    )
    assert kitchen.main(*out, "--by", "user", "--at", "2026-10-11 17:58 Nowhere") == (
        1,
        f'refused: --at is "<YYYY-MM-DD HH:MM {word(datetime(2026, 10, 11, 17, 58))}>"\n',
    )
    code, said = kitchen.main("word", "--to", "demo", *kitchen.message("go"))
    assert code == 0, said
    kept = said.split()[-1]
    assert kitchen.main("queue", "approve", "alpha", "--word", kept, "--sha", sha)[0] == 0
    said_at = jsettings.DEFAULTS.stamp(NOW - timedelta(minutes=5))
    ran = jsettings.DEFAULTS.stamp(NOW)
    assert rows(kitchen)["alpha"]["approved"] == (
        f"your word, {said_at}, in chat; run {ran} by the demo home"
    )
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]
    assert not jstack_config.exists()


def test_a_config_that_names_robin_is_whom_jbus_takes_and_prints(kitchen, jstack_config):
    jstack_config.write_text(NAMED)
    why = "needs Robin, touches skills/crew/SKILL.md"
    kitchen.config(max_running=6)
    kitchen.brief("ps-agnostic", RESULT)
    accepted = f"ready 286 {HEAD} ps-agnostic ps-agnostic, accepted: {why}, {SAFE}\n"
    kitchen.set("accept.txt", accepted)
    kitchen.set("open.json", [kitchen.opened("ps-agnostic", 286)])
    kitchen.set("jmerge.txt", f"hold 286 {URL}: {why}\n")
    add(kitchen, "alpha", approve=False, depends="ps-agnostic")
    kitchen.clock_reads(AT)
    assert kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", AT)[1].startswith(
        "refused: only Robin removes a row, on their own words: --by Robin, or --message "
    )
    kept = kitchen.main("word", "--to", "demo", *kitchen.message("go"))[1].split()[-1]
    built = brief("alpha", "Builds on: ps-agnostic\n")
    go = ["queue", "approve", "alpha", "--sha", sha12(built)]
    assert kitchen.main(*go, "--word", kept)[0] == 0
    assert rows(kitchen)["alpha"]["approval"]["said_at"] == "2026-10-12 10:55 ET"
    kitchen.poll()
    hand = (
        f"hand-merge #286 {URL}: {why}; {SAFE};"
        ' jmerge --accept 286 --by Robin --at "<YYYY-MM-DD HH:MM ET>"'
    )
    line = f"waiting-on-user demo: {hand} · unblocks alpha · since 11:00 ET"
    (event,) = kitchen.events("waiting-on-user")
    assert (event["line"], event["loud"]) == (line, "quiet")
    assert kitchen.main("queue", "show")[1].startswith(f"waiting on Robin:\n{hand}\n\n| slug |")


def test_a_row_approved_before_the_name_was_a_setting_still_launches(kitchen):
    add(kitchen, "alpha")
    table = json.loads((kitchen.state / "queue.json").read_text())
    table[0]["approved"] = "2026-10-11 20:28 ET by Robin"
    jbus.write_json(kitchen.state / "queue.json", table)
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]
    assert rows(kitchen)["alpha"]["approved"] == "2026-10-11 20:28 ET by Robin"


def test_across_a_clock_change_the_refusal_names_the_word_the_time_typed_has(jstack_config):
    jstack_config.write_text('timezone = "America/New_York"\n')
    user = jsettings.load()
    assert user.takes("2026-10-31 23:50 EDT") and not user.takes("2026-10-31 23:50 EST")
    assert user.form("2026-10-31 23:50 EST") == "<YYYY-MM-DD HH:MM EDT>"
    assert user.form("2026-12-01 10:00 EDT") == "<YYYY-MM-DD HH:MM EST>"
    assert user.takes("2026-11-01 01:30 EDT") and user.takes("2026-11-01 01:30 EST")
    assert not user.takes("2026-11-01 02:30 EDT")


def test_a_refused_time_asks_for_the_word_of_the_time_it_was_given(kitchen, jstack_config):
    jstack_config.write_text('timezone = "America/New_York"\n')
    kitchen.clock_reads("2026-12-01 10:00 EST")
    add(kitchen, "alpha", approve=False)
    out = ["queue", "remove", "alpha", "--by", "user"]
    assert kitchen.main(*out, "--at", "2026-12-01 10:00 EDT") == (
        1,
        'refused: --at is "<YYYY-MM-DD HH:MM EST>"\n',
    )
    assert kitchen.main(*out, "--at", "2026-12-01 10:00 EST")[0] == 0


@pytest.mark.parametrize("given", ["0", "100.5", '"90"', "true", "-1"])
def test_a_headroom_that_is_not_a_percent_is_refused(jstack_config, given):
    jstack_config.write_text(f"headroom = {given}\n")
    with pytest.raises(jsettings.Invalid, match="has a headroom that is not a percent"):
        jsettings.load()


def test_the_headroom_is_90_with_none_and_the_number_given_with_one(jstack_config):
    assert jsettings.load().headroom == 90
    jstack_config.write_text("headroom = 82.5\n")
    assert jsettings.load().headroom == 82.5


@pytest.mark.parametrize("given", ["0", "1.5", '"2"', "true", "-1"])
def test_a_retry_cap_that_is_not_a_whole_number_of_one_or_more_is_refused(jstack_config, given):
    jstack_config.write_text(f"retry_cap = {given}\n")
    with pytest.raises(jsettings.Invalid, match="has a retry_cap that is not a whole number"):
        jsettings.load()


def test_the_retry_cap_is_2_with_none_and_the_number_given_with_one(jstack_config):
    assert jsettings.load().retry_cap == 2
    jstack_config.write_text("retry_cap = 5\n")
    assert jsettings.load().retry_cap == 5


def test_the_go_is_given_per_entry_after_30_quiet_minutes_with_none(jstack_config):
    user = jsettings.load()
    assert (user.go, user.go_quiet_minutes) == ("entry", 30)
    jstack_config.write_text('go = "silence"\ngo_quiet_minutes = 5\n')
    user = jsettings.load()
    assert (user.go, user.go_quiet_minutes) == ("silence", 5)


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ('go = "maybe"', 'has a go that is not "entry" or "silence"'),
        ("go = true", 'has a go that is not "entry" or "silence"'),
        ("go_quiet_minutes = 0", "has a go_quiet_minutes that is not a whole number of 1 or more"),
        ("go_quiet_minutes = 2.5", "has a go_quiet_minutes that is not a whole number of 1"),
        ('go_quiet_minutes = "30"', "has a go_quiet_minutes that is not a whole number of 1"),
        ("go_quiet_minutes = true", "has a go_quiet_minutes that is not a whole number of 1"),
    ],
)
def test_a_go_or_a_window_that_is_not_one_of_its_values_is_refused_in_one_line(
    jstack_config, line, why
):
    jstack_config.write_text(f"{line}\n")
    with pytest.raises(jsettings.Invalid) as refused:
        jsettings.load()
    assert why in str(refused.value) and "\n" not in str(refused.value)
