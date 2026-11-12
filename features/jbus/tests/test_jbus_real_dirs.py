"""No test reaches the machine's own jbus config or state, or its test slots' lock files.

On 2026-10-26 a test called `monkeypatch.undo()` and then ran a pass: the undo took back the
kitchen's `JBUS_CONFIG_DIR` and `JBUS_STATE_DIR`, and the pass ran on the real ones with the
kitchen's clock, so the stale alarm said no pass had ended since 2026-10-12. In ts-slotwait-spare
the same undo took back the kitchen's `JGAUGE_LOCKS_DIR`, and the test's `slot.take` ran on the
machine's test slots and wrote its fake threads into the machine's waiters file.
"""

import os
import pwd
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from jgauge import slot

ACCOUNT = Path(pwd.getpwuid(os.getuid()).pw_dir)
REAL = {
    "JBUS_CONFIG_DIR": (jbus.config_dir, ACCOUNT / ".config" / "jbus"),
    "JBUS_STATE_DIR": (jbus.state_dir, ACCOUNT / ".local" / "state" / "jbus"),
    "JGAUGE_LOCKS_DIR": (slot.locks_dir, ACCOUNT / ".local" / "state" / "locks"),
}


def named(name):
    """The function that takes the directory `name` names, and the machine's own."""
    return REAL[name]


@pytest.mark.parametrize("name", REAL)
def test_a_test_that_reaches_a_real_dir_fails_by_its_name(monkeypatch, name):
    asked, real = named(name)
    test = os.environ["PYTEST_CURRENT_TEST"].rsplit(" ", 1)[0]
    monkeypatch.setenv("HOME", str(ACCOUNT))
    for given in ("", str(real)):
        monkeypatch.setenv(name, given)
        with pytest.raises(jbus.RealDir) as raised:
            asked()
        assert str(raised.value).startswith(f"refused: the test {test} reached the real {real}:")


@pytest.mark.parametrize("name", REAL)
def test_a_test_s_own_dir_is_the_one_taken(tmp_path, monkeypatch, name):
    asked, _ = named(name)
    monkeypatch.setenv(name, str(tmp_path))
    assert asked() == tmp_path


@pytest.mark.parametrize("name", REAL)
def test_a_test_that_undoes_its_monkeypatch_is_still_on_dirs_of_the_run(monkeypatch, name):
    asked, real = named(name)
    monkeypatch.undo()
    assert asked().resolve() != real.resolve()


@pytest.mark.parametrize("name", REAL)
def test_a_test_with_a_home_of_its_own_is_not_refused_and_the_real_dir_still_is(
    tmp_path, monkeypatch, name
):
    asked, real = named(name)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(name, "")
    assert asked() == tmp_path / real.relative_to(ACCOUNT)
    monkeypatch.setenv(name, str(real))
    with pytest.raises(jbus.RealDir):
        asked()


@pytest.mark.parametrize("name", REAL)
def test_outside_a_test_the_password_database_is_never_asked(tmp_path, monkeypatch, name):
    asked, _ = named(name)

    def no_entry(uid):
        raise KeyError(uid)

    monkeypatch.setattr(pwd, "getpwuid", no_entry)
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.setenv(name, str(tmp_path))
    assert asked() == tmp_path


def test_a_desk_config_in_another_zone_reaches_no_test_that_undoes_its_monkeypatch(
    tmp_path, monkeypatch
):
    desk = tmp_path / "desk"
    (desk / ".config" / "jstack").mkdir(parents=True)
    (desk / ".config" / "jstack" / "config.toml").write_text('timezone = "Pacific/Kiritimati"\n')
    with pytest.MonkeyPatch.context() as machine:
        machine.setenv("HOME", str(desk))
        monkeypatch.undo()
        assert jsettings.load().zone == ZoneInfo("America/New_York")
