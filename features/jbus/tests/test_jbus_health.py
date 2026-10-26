"""These tests cover `jbus health` and the health step of every `jbus poll`. They drive each
check with fake senses and the ledger, on a clock the test moves, through the real pass against
the kitchen's fakes.

The tests hold the checks to these rules. A check sends one page when an incident starts, none
while it lasts, and one when it clears. Each page names its number, what it counts and its limit.
For the quota, launches skip the capped instance, no launch starts with the whole pool capped,
and at the reset jbus starts launches again by itself, with one line that says so."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import cli, health, merge, wake
from jroles import ledger
from test_jbus_kitchen import NOW, approved

PRIME = "claudeAgent_claude_prime"
GIB = 2**30
RESET = NOW + timedelta(hours=3)
LATER = RESET + timedelta(minutes=1)
TIMED_OUT = "jbus.service: Failed with result 'timeout'."


class Senses(health.Senses):
    """`Senses` is the machine as a test sets it: the mounts, the journal of `jbus.service`, and
    each unit's properties. A journal of None is a journal that could not be read."""

    def __init__(self):
        self.disks = {"/home": (20 * GIB, 80 * GIB, 0, 0)}
        self.lines: list[str] | None = []
        self.units = {("jbus.service", "TimeoutStartUSec"): "20min"}

    def mounts(self, paths):
        return [health.Mount(point, *numbers) for point, numbers in self.disks.items()]

    def journal(self, unit, minutes):
        return None if self.lines is None else list(self.lines)

    def show(self, unit, name):
        return self.units.get((unit, name), "")


@pytest.fixture
def senses(monkeypatch):
    made = Senses()
    monkeypatch.setattr(health, "machine_senses", lambda: made)
    monkeypatch.setattr(health, "clock", lambda: NOW)
    return made


@pytest.fixture(autouse=True)
def quiet_plan(kitchen):
    """The kitchen's plan runs on the real clock, so these tests write the ledger themselves."""
    kitchen.machine(plan=None)


def pages(kitchen):
    """Every line the health check queued, oldest first: each `alert`, which pages the user, and
    each `recovered`, which only the log and the digest hold."""
    return [one["line"] for one in kitchen.events() if one["event"] in ("alert", "recovered")]


def polls(kitchen, *minutes, start=NOW):
    for one in minutes:
        kitchen.poll(start + timedelta(minutes=one))


def test_a_full_disk_is_paged_once_while_it_holds_and_logged_once_when_it_clears(kitchen, senses):
    senses.disks["/home"] = (85 * GIB, 15 * GIB, 0, 0)
    polls(kitchen, 0, 1, 5, 30)
    assert pages(kitchen) == [
        "alert: health disk /home: 85% of its space used (85.0 of 100.0 GiB), alerts at 80%"
    ]
    senses.disks["/home"] = (60 * GIB, 40 * GIB, 0, 0)
    polls(kitchen, 31, 32, 40)
    assert pages(kitchen)[1:] == [
        "recovered: health disk /home: 60% of its space used (60.0 of 100.0 GiB), alerts at 80%"
    ]
    assert [one["loud"] for one in kitchen.events("recovered")] == ["quiet"]
    assert [one["event"] for post in kitchen.webhook.posts for one in post] == ["alert"]


def test_the_page_reaches_the_webhook_once_as_an_event_of_the_machine(kitchen, senses):
    senses.disks["/home"] = (90 * GIB, 10 * GIB, 0, 0)
    polls(kitchen, 0, 10, 20)
    line = "alert: health disk /home: 90% of its space used (90.0 of 100.0 GiB), alerts at 80%"
    posted = [one for events in kitchen.webhook.posts for one in events if one["event"] == "alert"]
    assert [one["say"] for one in posted] == [line]
    assert [one for one in kitchen.log("notify") if "health" in one] == [f"jbus | {line}"]


def test_inodes_page_by_their_own_count_and_a_filesystem_with_none_has_no_inode_check(
    kitchen, senses
):
    senses.disks = {"/tmp": (1 * GIB, 30 * GIB, 900_000, 1_048_576), "/home": (GIB, GIB, 0, 0)}
    kitchen.poll()
    assert pages(kitchen) == [
        "alert: health inodes /tmp: 86% of its inodes used (900,000 of 1,048,576), alerts at 80%"
    ]
    found = [one.key for one in health.look(jbus.load(), NOW, print)]
    assert "inodes /home" not in found and "disk /home" in found


def test_a_pass_systemd_stopped_at_its_timeout_is_paged_and_clears_after_the_window(
    kitchen, senses
):
    senses.lines = ["Started jbus.service.", TIMED_OUT, "jbus.service: Consumed 3min CPU time."]
    polls(kitchen, 0, 5)
    assert pages(kitchen) == [
        "alert: health timeout jbus: jbus.service stopped at its 20min start timeout 1 times "
        "in the last 60 min, alerts at 1"
    ]
    senses.lines = []
    polls(kitchen, 61, 62)
    assert pages(kitchen)[1:] == [
        "recovered: health timeout jbus: jbus.service stopped at its 20min start timeout 0 times "
        "in the last 60 min, alerts at 1"
    ]


def test_a_jmerge_the_pass_stopped_at_its_timeout_is_read_from_the_line_the_pass_says(
    kitchen, senses, monkeypatch
):
    """The line is the one a real pass says when `jmerge` runs past its timeout. So the check
    reads the wording that the pass writes to the journal, not a copy of it."""
    jmerge = kitchen.stub / "jmerge"
    jmerge.write_text("#!/bin/sh\nsleep 5\n")
    monkeypatch.setattr(merge, "JMERGE_TIMEOUT", 0.2)
    said = kitchen.poll()
    (stopped,) = [line for line in said if "jmerge did not run" in line]
    assert pages(kitchen) == []
    senses.lines = [stopped]
    kitchen.poll(NOW + timedelta(minutes=1))
    assert pages(kitchen) == [
        "alert: health timeout jmerge: jmerge stopped at its 17 min timeout 1 times "
        "in the last 60 min, alerts at 1"
    ]


def test_a_journal_that_cannot_be_read_leaves_an_open_incident_open(kitchen, senses):
    senses.lines = [TIMED_OUT]
    kitchen.poll()
    senses.lines = None
    polls(kitchen, 61, 62)
    assert len(pages(kitchen)) == 1
    _, out = kitchen.main("health")
    assert "?    health timeout jbus: the journal of jbus.service could not be read" in out


def test_an_incident_whose_mount_is_gone_ends_with_no_page(kitchen, senses):
    senses.disks = {"/home": (GIB, GIB, 0, 0), "/data": (95 * GIB, 5 * GIB, 0, 0)}
    kitchen.poll()
    del senses.disks["/data"]
    polls(kitchen, 1, 2)
    senses.disks["/data"] = (95 * GIB, 5 * GIB, 0, 0)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [line.split(":")[0] for line in pages(kitchen)] == ["alert", "alert"]


@pytest.fixture
def relay(kitchen, senses, monkeypatch, tmp_path):
    """The config points jbus's posts at the relay. The project's webhook is at the `RELAY_PORT`
    that the relay's env file sets for the unit. jbus's environment does not set it. The relay is
    up. Its heartbeat file records a beat at NOW and a body received at NOW, and it alerts after
    90 minutes of silence."""
    port = kitchen.webhook.url.rsplit(":", 1)[1].split("/")[0]
    for name in ("RELAY_PORT", "RELAY_STATE"):
        monkeypatch.delenv(name, raising=False)
    health.relay_env().parent.mkdir(parents=True, exist_ok=True)
    health.relay_env().write_text(
        f"RELAY_INBOUND_KEY=a-key\nRELAY_PORT={port}\nRELAY_STATE='{tmp_path / 'relay'}'\n"
    )
    (tmp_path / "relay").mkdir()
    senses.units[("jbus-relay.service", "ActiveState")] = "active"
    return Beat(tmp_path / "relay" / "heartbeat.json")


class Beat:
    def __init__(self, path):
        self.path = path
        self.write(NOW, NOW)

    def write(self, beat, heard, failing=(), started=NOW - timedelta(days=1), refused=()):
        made = {
            "beat": beat.isoformat(),
            "started": started.isoformat(),
            "heard": heard and heard.isoformat(),
            "silent_minutes": 90,
            "failing": list(failing),
            "refused": list(refused),
        }
        self.path.write_text(json.dumps(made))


def test_a_relay_that_heard_nothing_for_n_minutes_is_paged_and_clears_on_the_next_body(
    kitchen, relay
):
    now = NOW + timedelta(minutes=95)
    relay.write(now, NOW)
    kitchen.poll(now)
    kitchen.poll(now + timedelta(minutes=1))
    assert pages(kitchen) == [
        "alert: health relay silent: no body heard for 95 min, "
        "alerts after 90 min (RELAY_SILENT_MINUTES)"
    ]
    later = now + timedelta(minutes=5)
    relay.write(later, later - timedelta(minutes=2))
    kitchen.poll(later)
    assert pages(kitchen)[1:] == [
        "recovered: health relay silent: no body heard for 2 min, "
        "alerts after 90 min (RELAY_SILENT_MINUTES)"
    ]


def test_a_relay_that_is_down_is_paged_for_its_unit_and_its_beat_and_not_judged_silent(
    kitchen, senses, relay
):
    senses.units[("jbus-relay.service", "ActiveState")] = "failed"
    kitchen.poll(NOW + timedelta(minutes=200))
    assert pages(kitchen) == [
        "alert: health relay: jbus-relay.service is failed, alerts when it is not active",
        "alert: health relay heartbeat: last heartbeat 200 min ago, alerts after 3 min",
    ]


def test_a_route_whose_posts_fail_for_ten_minutes_is_paged_with_what_waits(kitchen, relay):
    since = NOW - timedelta(minutes=4)
    relay.write(
        NOW,
        NOW,
        [{"route": "blocking", "since": since.isoformat(), "why": "HTTP 503", "waiting": 2}],
    )
    kitchen.poll()
    assert pages(kitchen) == []
    later = NOW + timedelta(minutes=8)
    relay.write(
        later,
        later,
        [{"route": "blocking", "since": since.isoformat(), "why": "HTTP 503", "waiting": 3}],
    )
    kitchen.poll(later)
    assert pages(kitchen) == [
        "alert: health relay errors: POSTs on route blocking failing for 12 min (HTTP 503), "
        "3 bodies wait, alerts when a route's POSTs fail for 10 min"
    ]


def test_a_relay_the_config_does_not_post_to_is_not_watched(kitchen, senses, monkeypatch):
    for name in ("RELAY_PORT", "RELAY_STATE"):
        monkeypatch.delenv(name, raising=False)
    senses.units[("jbus-relay.service", "ActiveState")] = "failed"
    kitchen.poll()
    assert pages(kitchen) == []
    _, out = kitchen.main("health")
    assert "ok   health relay: the config posts nothing to 127.0.0.1, not watched" in out


@pytest.fixture
def pools(jstack_config):
    roles = jstack_config.parent / "roles"
    roles.write_text(f"crew: claudeAgent claude-sonnet-5-5 claudeAgent,{PRIME}\n")


def used(instance, window, share, resets=RESET):
    ledger.write(ledger.Record(instance, window, share, int(resets.timestamp())))


def test_the_weekly_window_pages_at_80_percent_and_the_five_hour_one_only_when_full(
    kitchen, senses, pools
):
    used("claudeAgent", "seven_day", 85)
    used("claudeAgent", "five_hour", 95)
    polls(kitchen, 0, 10)
    assert pages(kitchen) == [
        "alert: health quota claudeAgent seven_day: 85% of the seven_day window used, "
        "resets 2026-10-12 14:00 ET, alerts at 80%"
    ]


def launched(kitchen):
    return [given["modelSelection"]["instanceId"] for given in kitchen.t3.launches]


def test_a_capped_instance_pauses_its_launches_and_they_resume_on_their_own_at_the_reset(
    kitchen, senses, pools
):
    kitchen.config(max_running=3)
    used("claudeAgent", "five_hour", 100)
    approved(kitchen, "alpha")
    kitchen.poll()
    assert launched(kitchen) == [PRIME]
    assert pages(kitchen) == [
        "alert: health capped claudeAgent: five_hour full until 2026-10-12 14:00 ET, pauses its "
        "launches at 100% of a window; launches skip claudeAgent until then"
    ]
    used(PRIME, "seven_day", 100, RESET + timedelta(days=2))
    approved(kitchen, "beta", priority=2)
    polls(kitchen, 1, 5, 60)
    assert launched(kitchen) == [PRIME]
    assert pages(kitchen)[1:] == [
        f"alert: health quota {PRIME} seven_day: 100% of the seven_day window used, "
        "resets 2026-10-14 14:00 ET, alerts at 80%",
        f"alert: health capped {PRIME}: seven_day full until 2026-10-14 14:00 ET, pauses its "
        f"launches at 100% of a window; launches skip {PRIME} until then; every instance is "
        "capped, and no launch starts before 2026-10-12 14:00 ET",
    ]
    said = kitchen.poll(LATER)
    assert launched(kitchen) == [PRIME, "claudeAgent"]
    resumed = (
        "recovered: health capped claudeAgent: no window full, pauses its launches at 100% of a "
        "window; launches on claudeAgent resume"
    )
    assert [line for line in said if "resume" in line] == [resumed]
    polls(kitchen, 2, 30, start=LATER)
    assert pages(kitchen)[3:] == [resumed]


def test_jbus_health_prints_each_check_with_its_number_and_limit_and_pages_nothing(
    kitchen, senses, pools
):
    senses.disks = {"/home": (85 * GIB, 15 * GIB, 0, 0), "/tmp": (GIB, 9 * GIB, 10, 100)}
    used("claudeAgent", "seven_day", 40)
    code, out = kitchen.main("health")
    assert code == 1
    assert out.splitlines() == [
        "over health disk /home: 85% of its space used (85.0 of 100.0 GiB), alerts at 80%",
        "ok   health disk /tmp: 10% of its space used (1.0 of 10.0 GiB), alerts at 80%",
        "ok   health inodes /tmp: 10% of its inodes used (10 of 100), alerts at 80%",
        "ok   health timeout jbus: jbus.service stopped at its 20min start timeout 0 times in "
        "the last 60 min, alerts at 1",
        "ok   health timeout jmerge: jmerge stopped at its 17 min timeout 0 times in the last "
        "60 min, alerts at 1",
        "ok   health relay: the config posts nothing to 127.0.0.1, not watched",
        "ok   health quota claudeAgent seven_day: 40% of the seven_day window used, resets "
        "2026-10-12 14:00 ET, alerts at 80%",
        "ok   health capped claudeAgent: no window full, pauses its launches at 100% of a window",
    ]
    assert pages(kitchen) == [] and kitchen.waiting() == []


def test_a_pass_in_which_a_project_raises_still_looks_at_the_machine_and_pages(
    kitchen, senses, monkeypatch
):
    def broken(run):
        raise RuntimeError("jmerge broke")

    monkeypatch.setattr(merge, "merge", broken)
    senses.disks["/home"] = (85 * GIB, 15 * GIB, 0, 0)
    kitchen.t3.write(NOW)
    said = []
    assert cli.poll(jbus.load(), NOW, said.append) == 1
    line = "alert: health disk /home: 85% of its space used (85.0 of 100.0 GiB), alerts at 80%"
    assert line in said and pages(kitchen) == [line]
    assert [one for one in kitchen.log("notify") if "health" in one] == [f"jbus | {line}"]


def test_a_relay_restarted_often_still_goes_silent_from_the_last_body_it_heard(kitchen, relay):
    now = NOW + timedelta(minutes=95)
    relay.write(now, NOW, started=now - timedelta(minutes=5))
    kitchen.poll(now)
    assert pages(kitchen) == [
        "alert: health relay silent: no body heard for 95 min, "
        "alerts after 90 min (RELAY_SILENT_MINUTES)"
    ]


def test_a_body_refused_for_good_is_paged_with_where_it_is_kept_and_clears_after_an_hour(
    kitchen, relay, tmp_path
):
    at = NOW - timedelta(minutes=5)
    refused = {"route": "blocking", "at": at.isoformat(), "why": "HTTP 400", "file": "1-abc.json"}
    for minutes in (0, 10):
        relay.write(NOW + timedelta(minutes=minutes), NOW, refused=[refused])
        kitchen.poll(NOW + timedelta(minutes=minutes))
    kept = tmp_path / "relay" / "dead" / "blocking" / "1-abc.json"
    assert pages(kitchen) == [
        "alert: health relay refused: 1 bodies refused for good in the last 60 min, the last "
        f"5 min ago on route blocking (HTTP 400), kept in {kept}, alerts at 1 in the last 60 min"
    ]
    later = NOW + timedelta(minutes=56)
    relay.write(later, later, refused=[refused])
    kitchen.poll(later)
    assert pages(kitchen)[1:] == [
        "recovered: health relay refused: 0 bodies refused for good in the last 60 min, "
        "alerts at 1 in the last 60 min"
    ]


def test_an_incident_whose_page_did_not_go_and_that_cleared_is_paged_once_with_both(
    kitchen, senses, monkeypatch
):
    sent = wake.Box.send
    failed = []

    def flaky(self, slug, kind, line, *more, **named):
        if kind == "alert" and not failed:
            failed.append(line)
            raise OSError("No space left on device")
        return sent(self, slug, kind, line, *more, **named)

    monkeypatch.setattr(wake.Box, "send", flaky)
    senses.disks["/home"] = (85 * GIB, 15 * GIB, 0, 0)
    said = kitchen.poll()
    assert failed and pages(kitchen) == []
    assert any(line.startswith("health failed: OSError") for line in said)
    senses.disks["/home"] = (60 * GIB, 40 * GIB, 0, 0)
    polls(kitchen, 1, 2, 10)
    assert pages(kitchen) == [
        "recovered: health disk /home: 60% of its space used (60.0 of 100.0 GiB), alerts at 80% "
        "(it began 11:00 ET, and that page did not go)"
    ]


def test_a_heartbeat_that_cannot_be_read_leaves_an_open_refusal_open(kitchen, relay):
    refused = {"route": "blocking", "at": NOW.isoformat(), "why": "HTTP 400", "file": "1-a.json"}
    relay.write(NOW, NOW, refused=[refused])
    kitchen.poll()
    relay.path.write_text("{not json")
    polls(kitchen, 61, 62)
    assert [line.split(":", 2)[1] for line in pages(kitchen)] == [
        " health relay refused",
        " health relay heartbeat",
    ]
