"""The small rules every package of jstack shares live once, in jsettings: where the config is,
how a moment is stored and read back, a thread's id, and a JSON list changed under a lock."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import pytest

import jsettings


def test_the_config_home_is_under_xdg_config_home_or_the_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert jsettings.config_home() == tmp_path / "xdg" / "jstack"
    assert jsettings.path() == tmp_path / "xdg" / "jstack" / "config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path / "me"))
    assert jsettings.config_home() == tmp_path / "me" / ".config" / "jstack"


def test_the_config_home_of_another_machine_is_read_from_its_own_env_and_home(tmp_path):
    assert jsettings.config_home({}, tmp_path) == tmp_path / ".config" / "jstack"
    named = {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    assert jsettings.config_home(named, tmp_path) == tmp_path / "xdg" / "jstack"


def test_a_stamp_is_utc_to_the_second_in_the_form_its_file_writes():
    moment = datetime(2026, 10, 27, 11, 25, 17, 999999, tzinfo=timezone(timedelta(hours=-4)))
    assert jsettings.stamp(moment) == "2026-10-27T15:25:17+00:00"
    assert jsettings.stamp(moment, z=True) == "2026-10-27T15:25:17Z"


@pytest.mark.parametrize("z", [False, True])
def test_when_reads_back_what_stamp_wrote(z):
    moment = datetime(2026, 10, 27, 15, 25, 17, tzinfo=UTC)
    assert jsettings.when(jsettings.stamp(moment, z=z)) == moment


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-27T15:25:17.123Z",
        "2026-10-27T15:25:17.5-04:00",
        "2026-10-27T15:25:17",
        "2026-10-27",
    ],
)
def test_when_reads_a_time_as_the_old_replace_of_z_read_it(text):
    assert jsettings.when(text) == datetime.fromisoformat(text.replace("Z", "+00:00"))


@pytest.mark.parametrize("text", ["", "garbage"])
def test_when_refuses_what_is_not_a_time(text):
    with pytest.raises(ValueError):
        jsettings.when(text)


def test_a_thread_id_has_the_prefix_once():
    assert jsettings.thread_id("abc") == "mcp:abc"
    assert jsettings.thread_id("mcp:abc") == "mcp:abc"
    assert jsettings.thread_id("") == ""


@dataclass(frozen=True)
class One:
    since: str
    id: str


LIST = jsettings.LockedList("ones.json", "ones.lock", lambda raw: [One(**one) for one in raw])


def test_a_locked_list_writes_a_change_and_reads_it_back_oldest_first(tmp_path):
    LIST.change(tmp_path, lambda ones: [*ones, One("2", "b"), One("1", "a")])
    assert LIST.read(tmp_path) == [One("1", "a"), One("2", "b")]
    assert json.loads((tmp_path / "ones.json").read_text()) == [
        {"since": "2", "id": "b"},
        {"since": "1", "id": "a"},
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["ones.json", "ones.lock"]


def test_a_list_that_cannot_be_read_is_no_records(tmp_path):
    assert LIST.peek(tmp_path) == [] and not LIST.there(tmp_path)
    (tmp_path / "ones.json").write_text('[{"since": "1"}]')
    assert LIST.peek(tmp_path) == []
    (tmp_path / "ones.json").write_text("[{")
    assert LIST.read(tmp_path) == []


def test_a_change_that_changes_nothing_writes_nothing(tmp_path):
    LIST.change(tmp_path, lambda ones: ones)
    assert not LIST.there(tmp_path)


def test_a_peek_makes_no_lock_file(tmp_path):
    LIST.peek(tmp_path)
    assert list(tmp_path.iterdir()) == []
