"""A usage endpoint that answers 429 changes nothing in the ledger, keeps a retry time, and never
marks an account free or capped. The test `test_the_31st` replays 2026-10-31, as the journal has it:
prime's weekly window read 100% with its reset on 11-02 at 20:00 UTC, three 429s at 08:55, more
reads at 100%, and from 15:00 a reading of 0% with the same reset."""

import email.message
import json
import os
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from jgauge import limits
from jroles import ledger

PRIME = "claudeAgent_claude_prime"
RESETS = datetime(2026, 11, 2, 20, 0, tzinfo=UTC)
AT = datetime(2026, 10, 31, 12, 55, tzinfo=UTC)
FULL = {
    "five_hour": {"utilization": 0, "resets_at": None},
    "seven_day": {"utilization": 100, "resets_at": RESETS.isoformat()},
}


def refused(retry_after=None):
    def get(url, token):
        headers = email.message.Message()
        if retry_after:
            headers["Retry-After"] = retry_after
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", headers, None)

    return get


def reading(week, resets=RESETS):
    usage = {
        "five_hour": {"utilization": 0, "resets_at": None},
        "seven_day": {"utilization": week, "resets_at": resets.isoformat()},
    }
    return lambda url, token: usage


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITS", str(tmp_path / "limits"))
    where = tmp_path / "prime"
    where.mkdir()
    expires = (AT + timedelta(days=30)).timestamp() * 1000
    token = {"claudeAiOauth": {"accessToken": "t", "expiresAt": expires}}
    (where / ".credentials.json").write_text(json.dumps(token))
    (where / ".claude.json").write_text("{}")
    return limits.Home(PRIME, where)


def read(home, at, get):
    """Read the home as `jgauge limits` does, and keep what it read."""
    source, found = limits.read(home, at, get)
    return limits.keep(home, found, at, source)


def capped(at):
    return ledger.capped_until(ledger.read([PRIME]), PRIME, at)


def test_a_429_leaves_the_last_good_value_and_a_retry_time(home):
    read(home, AT, reading(100))
    before = ledger.file_of(PRIME).read_text()
    with pytest.raises(limits.Stale, match="answered 429, asked again at"):
        limits.read(home, AT, refused())
    assert ledger.file_of(PRIME).read_text() == before
    assert capped(AT) == RESETS
    assert limits.retry_at(PRIME) == AT + limits.RETRY


def test_a_429_on_a_free_account_does_not_cap_it(home):
    read(home, AT, reading(40))
    with pytest.raises(limits.Stale):
        limits.read(home, AT, refused())
    assert capped(AT) is None


def test_a_429_with_no_reading_writes_no_ledger_line(home):
    with pytest.raises(limits.Stale):
        limits.read(home, AT, refused())
    assert ledger.read([PRIME]) == {}


def test_the_retry_time_is_the_answer_s_retry_after(home):
    with pytest.raises(limits.Stale):
        limits.read(home, AT, refused("120"))
    assert limits.retry_at(PRIME) == AT + timedelta(seconds=120)


def test_the_endpoint_is_not_asked_before_the_retry_time_and_is_asked_after(home):
    with pytest.raises(limits.Stale):
        limits.read(home, AT, refused("120"))
    asked = []

    def counts(url, token):
        asked.append(url)
        return FULL

    with pytest.raises(limits.Stale):
        limits.read(home, AT + timedelta(seconds=119), counts)
    assert asked == []
    read(home, AT + timedelta(seconds=120), counts)
    assert len(asked) == 1
    assert limits.retry_at(PRIME) is None


def test_the_ledger_is_out_of_date_only_after_a_failed_read_and_fresh_minutes(home):
    file = read(home, AT, reading(100))
    assert limits.unread(PRIME, AT + ledger.FRESH * 2) == ""
    with pytest.raises(limits.Stale):
        limits.read(home, AT + timedelta(minutes=1), refused())
    os.utime(file, (AT.timestamp(), AT.timestamp()))
    assert limits.unread(PRIME, AT + ledger.FRESH - timedelta(seconds=1)) == ""
    assert limits.unread(PRIME, AT + ledger.FRESH)
    assert capped(AT + ledger.FRESH) == RESETS


def test_a_turn_that_just_hit_the_limit_is_not_undone_by_a_reading_of_98(home):
    ledger.write(ledger.Record(PRIME, "seven_day", 100.0, int(RESETS.timestamp())))
    read(home, AT, reading(98))
    assert capped(AT) == RESETS


def test_the_cache_never_lowers_a_cap(home):
    ledger.write(ledger.Record(PRIME, "seven_day", 100.0, int(RESETS.timestamp())))
    account = {"accountUuid": "a"}
    cached = {
        **account,
        "fetchedAtMs": AT.timestamp() * 1000,
        "utilization": {
            "five_hour": {"utilization": 0, "resets_at": None},
            "seven_day": {"utilization": 0, "resets_at": RESETS.isoformat()},
        },
    }
    home.config().write_text(
        json.dumps({"oauthAccount": account, "cachedUsageUtilization": cached})
    )
    source, found = limits.read(home, AT, refused())
    assert source == "cache"
    limits.keep(home, found, AT, source)
    assert capped(AT) == RESETS


def test_the_31st(home):
    """Each step of the day as `jgauge limits` read it. The 429s touch nothing, a reading of 100
    holds, and the endpoint's 0% with the same reset ends the cap at once, at 15:00 ET."""
    morning = datetime(2026, 10, 31, 12, 43, tzinfo=UTC)
    read(home, morning, reading(100))
    assert capped(morning) == RESETS
    for minute in (55, 57, 59):
        at = morning.replace(minute=minute)
        with pytest.raises(limits.Stale):
            limits.read(home, at, refused())
        assert capped(at) == RESETS
    drifted = RESETS - timedelta(seconds=1)
    held = datetime(2026, 10, 31, 18, 58, tzinfo=UTC)
    read(home, held, reading(100, drifted))
    assert capped(held) == RESETS
    freed = datetime(2026, 10, 31, 19, 0, 22, tzinfo=UTC)
    read(home, freed, reading(0, drifted))
    assert capped(freed) is None
