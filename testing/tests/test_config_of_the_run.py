"""A test that calls `monkeypatch.undo()` takes back what the autouse `jstack_config` set. It
still reads a jstack config of the run's own, in the same zone, and never the desk's
`~/.config/jstack/config.toml`, wherever its feature's tests live."""

from zoneinfo import ZoneInfo

import pytest

import jsettings


def test_a_test_that_undoes_its_monkeypatch_reads_no_desk_config(tmp_path, monkeypatch):
    desk = tmp_path / "desk"
    (desk / ".config" / "jstack").mkdir(parents=True)
    (desk / ".config" / "jstack" / "config.toml").write_text('timezone = "Pacific/Kiritimati"\n')
    with pytest.MonkeyPatch.context() as machine:
        machine.setenv("HOME", str(desk))
        monkeypatch.undo()
        assert jsettings.load().zone == ZoneInfo("America/New_York")
