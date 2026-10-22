"""The user's name and time zone are settings. `jsettings.load` reads them from one file, and
every command runs on defaults when there is no file. Some files on disk were written under
the old names, before the name became a setting, and the commands read those names as the new
ones. The tests run as `features/jbus/tests/test_jbus.py` runs, with the real command and the
real pass against the fakes."""

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
from jbus import wake
from test_jbus_kitchen import NOW, RESULT, Kitchen
from test_jbus_queue import AT, add, brief, rows, sha12
from test_stall import ACCEPTED, HEAD, SAFE, URL, held, later, shown
from testing.jstack_fixtures import NAMED, OLD_EVENT, OLD_LEVEL, ZONE


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def word(moment):
    """The word that the machine's own zone prints after this time."""
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
    """An empty PYTHONTZPATH stands for a machine with no /usr/share/zoneinfo. Python then
    has only the zones that the project brings."""
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
    sha = sha12(brief("alpha"))
    at = f"2026-10-11 17:58 {word(datetime(2026, 10, 11, 17, 58))}"
    say = ["word", "--to", "demo"]
    assert kitchen.main(*say, "--by", "Robin", "--at", at, "go") == (
        1,
        "refused: only user gives a word, not Robin\n",
    )
    assert kitchen.main(*say, "--by", "user", "--at", "2026-10-11 17:58 Nowhere", "go") == (
        1,
        f'refused: --at is "<YYYY-MM-DD HH:MM {word(datetime(2026, 10, 11, 17, 58))}>"\n',
    )
    code, said = kitchen.main(*say, "--by", "user", "--at", at, "go")
    assert code == 0
    kept = said.split()[-1]
    assert kitchen.main("queue", "approve", "alpha", "--word", kept, "--sha", sha)[0] == 0
    ran = jsettings.DEFAULTS.stamp(NOW)
    assert rows(kitchen)["alpha"]["approved"] == (
        f"his word, {at} (time typed); run {ran} by the demo home"
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
    say = ["word", "--to", "demo"]
    assert kitchen.main(*say, "--by", "user", "--at", AT, "go") == (
        1,
        "refused: only Robin gives a word, not user\n",
    )
    kept = kitchen.main(*say, "--by", "Robin", "--at", AT, "go")[1].split()[-1]
    go = ["queue", "approve", "alpha", "--sha", sha12(brief("alpha"))]
    assert kitchen.main(*go, "--word", kept)[0] == 0
    assert rows(kitchen)["alpha"]["approval"]["said_at"] == AT
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


@pytest.mark.usefixtures("named_user")
def test_an_outbox_of_the_old_names_goes_out_in_the_next_post_under_the_new(kitchen):
    kitchen.quiet()
    waits = f"{OLD_EVENT} demo: approve alpha: do it · unblocks alpha · since 11:00 ET"
    old = [
        {
            "project": "demo",
            "slug": "approve:alpha",
            "event": OLD_EVENT,
            "line": waits,
            "text": "",
            "loud": OLD_LEVEL,
            "say": waits,
        },
        {
            "project": "demo",
            "slug": "beta",
            "event": "gate",
            "line": "gate beta: which one?",
            "text": "",
            "loud": OLD_LEVEL,
        },
    ]
    jbus.write_json(kitchen.state / "outbox.json", old)
    kitchen.poll()
    said = "waiting-on-user demo: approve alpha: do it · unblocks alpha · since 11:00 ET"
    (post,) = kitchen.webhook.posts
    assert post[:2] == [
        {**old[0], "event": "waiting-on-user", "loud": "user", "line": said, "say": said},
        {**old[1], "loud": "user"},
    ]
    assert kitchen.webhook.said[0][:2] == [said, "gate beta: which one?"]
    assert kitchen.waiting() == []


@pytest.mark.usefixtures("named_user")
def test_a_key_sent_under_the_old_event_name_keeps_the_finding_from_going_twice(kitchen):
    kitchen.quiet()
    jbus.write_json(kitchen.state / "sent.json", [f"{OLD_EVENT}|#9|a line"])
    run = wake.Pass(jbus.load(), jbus.load().projects[0], NOW)
    assert run.find("#9", "waiting-on-user", "a line") is False
    assert run.find("#9", "waiting-on-user", "another line") is True
    assert [one["line"] for one in kitchen.events()] == ["another line"]
    assert jbus.read_json(kitchen.state / "sent.json", []) == [
        "waiting-on-user|#9|a line",
        "waiting-on-user|#9|another line",
    ]


@pytest.mark.usefixtures("named_user")
def test_the_log_is_read_under_the_new_names_and_an_old_level_in_the_config_is_ignored(kitchen):
    record = {"at": "2026-10-11T15:00:00+00:00", "id": "a", "slug": "beta", "text": ""}
    record |= {"event": OLD_EVENT, "loud": OLD_LEVEL, "line": f"{OLD_EVENT} demo: do it"}
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / wake.LOG).write_text(json.dumps(record) + "\n")
    (logged,) = wake.Box(kitchen.state, jbus.load().projects[0]).log()
    assert (logged["event"], logged["loud"]) == ("waiting-on-user", "user")
    assert logged["line"] == "waiting-on-user demo: do it"
    path = kitchen.config_dir / "config.toml"
    named = 'name = "demo"\n'
    text = path.read_text().replace(named, f'{named}loud = ["{OLD_LEVEL}"]\n')
    kitchen.write(path, text)
    assert jbus.load().ignored == ("loud of project demo",)


def test_the_list_under_the_old_name_is_read_once_and_written_under_the_new(kitchen, jstack_config):
    held(kitchen, ACCEPTED)
    kitchen.poll()
    jstack_config.write_text(NAMED)
    new, old = kitchen.state / "waiting-on-user.json", kitchen.state / f"{OLD_EVENT}.json"
    assert [one["key"] for one in shown(kitchen)] == ["#286"]
    said = (
        f"{OLD_EVENT} demo: hand-merge #286 {URL}: it is yours · unblocks jbus-a · since 11:00 ET"
    )
    was = {"root": "#286", "line": said, "since": NOW.isoformat(), "unblocks": ["jbus-a"]}
    jbus.write_json(old, [was])
    new.unlink()
    stall = (kitchen.state / "stall.json").read_text()
    line = said.replace(OLD_EVENT, "waiting-on-user")
    assert kitchen.main("queue", "show")[1].startswith(f"waiting on Robin:\n{line}\n\n|")
    assert old.exists() and not new.exists()
    kitchen.config(max_running=6, dispatch=False)
    kitchen.poll(later(1))
    assert not old.exists()
    (kept,) = shown(kitchen)
    assert (kept["key"], kept["kind"], kept["line"]) == ("#286", "hold", line)
    assert (kept["since"], kept["unblocks"]) == (NOW.isoformat(), ["jbus-a"])
    assert (kitchen.state / "stall.json").read_text() == stall
    kitchen.config(max_running=6)
    kitchen.poll(later(2) + timedelta(seconds=1))
    assert [one["key"] for one in shown(kitchen)] == ["#286"] and not old.exists()
    assert OLD_EVENT not in new.read_text()


def test_the_old_names_are_those_of_the_user_the_settings_name_and_of_nobody_else(
    kitchen, jstack_config
):
    went = {"chef": "quiet"}
    assert jbus.old_names() == went
    held(kitchen, ACCEPTED)
    kitchen.poll()
    assert (kitchen.state / "waiting-on-user.json").exists()
    jstack_config.write_text(NAMED)
    assert jbus.old_names() == {OLD_LEVEL: "user", OLD_EVENT: "waiting-on-user", **went}
    assert jbus.current_level("wren", jbus.old_names()) == "wren"
    for live in ("Chef", "Quiet", "User"):
        jstack_config.write_text(f'user = "{live}"\n')
        level = jbus.current_level(live.lower(), jbus.old_names())
        assert level == went.get(live.lower(), live.lower())
    jstack_config.write_text("user = 7\n")
    assert jbus.old_names() == went


@pytest.mark.parametrize("name", ["Remark", "Word", "Settled", "Gate", "Result"])
def test_a_user_named_as_a_kind_or_a_key_begins_leaves_that_kind_and_that_key_as_written(
    kitchen, jstack_config, name
):
    jstack_config.write_text(f'user = "{name}"\n{ZONE}')
    word = name.lower()
    keys = [f"{word}|alpha|#1|a line", f"waiting-on-{word}|#9|a line"]
    jbus.write_json(kitchen.state / "sent.json", keys)
    box = wake.Box(kitchen.state, jbus.load().projects[0])
    assert box.sent() == [keys[0], "waiting-on-user|#9|a line"]
    one = {"event": word, "loud": word, "line": f"{word} demo: a line"}
    assert wake.current(one, jbus.old_names()) == {**one, "loud": "user"}


def test_across_a_clock_change_the_refusal_names_the_word_the_time_typed_has(jstack_config):
    jstack_config.write_text('timezone = "America/New_York"\n')
    user = jsettings.load()
    assert user.takes("2026-10-31 23:50 EDT") and not user.takes("2026-10-31 23:50 EST")
    assert user.form("2026-10-31 23:50 EST") == "<YYYY-MM-DD HH:MM EDT>"
    assert user.form("2026-12-01 10:00 EDT") == "<YYYY-MM-DD HH:MM EST>"
    assert user.takes("2026-11-01 01:30 EDT") and user.takes("2026-11-01 01:30 EST")
    assert not user.takes("2026-11-01 02:30 EDT")


def test_a_refused_word_asks_for_the_word_of_the_time_it_was_given(kitchen, jstack_config):
    jstack_config.write_text('timezone = "America/New_York"\n')
    go = ["word", "--to", "demo", "--by", "user"]
    assert kitchen.main(*go, "--at", "2026-12-01 10:00 EDT", "go") == (
        1,
        'refused: --at is "<YYYY-MM-DD HH:MM EST>"\n',
    )
    assert kitchen.main(*go, "--at", "2026-12-01 10:00 EST", "go")[0] == 0


@pytest.mark.parametrize("given", ["0", "100.5", '"90"', "true", "-1"])
def test_a_headroom_that_is_not_a_percent_is_refused(jstack_config, given):
    jstack_config.write_text(f"headroom = {given}\n")
    with pytest.raises(jsettings.Invalid, match="has a headroom that is not a percent"):
        jsettings.load()


def test_the_headroom_is_90_with_none_and_the_number_given_with_one(jstack_config):
    assert jsettings.load().headroom == 90
    jstack_config.write_text("headroom = 82.5\n")
    assert jsettings.load().headroom == 82.5
