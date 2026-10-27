"""No test reaches the machine's own jbus config or state.

On 2026-10-26 a test called `monkeypatch.undo()` and then ran a pass: the undo took back the
kitchen's `JBUS_CONFIG_DIR` and `JBUS_STATE_DIR`, and the pass ran on the real ones with the
kitchen's clock, so the stale alarm said no pass had ended since 2026-10-12.
"""

import os
from pathlib import Path

import pytest

import jbus

REAL = {
    "JBUS_CONFIG_DIR": ("config_dir", Path.home() / ".config" / "jbus"),
    "JBUS_STATE_DIR": ("state_dir", Path.home() / ".local" / "state" / "jbus"),
}


def named(name):
    """The directory jbus takes for `name`, and the machine's own."""
    function, real = REAL[name]
    return getattr(jbus, function), real


@pytest.mark.parametrize("name", REAL)
def test_a_test_that_reaches_a_real_jbus_dir_fails_by_its_name(monkeypatch, name):
    asked, real = named(name)
    test = os.environ["PYTEST_CURRENT_TEST"].rsplit(" ", 1)[0]
    for given in ("", str(real)):
        monkeypatch.setenv(name, given)
        with pytest.raises(jbus.RealDir) as raised:
            asked()
        assert str(raised.value).startswith(f"refused: the test {test} reached the real {real}:")


@pytest.mark.parametrize("name", REAL)
def test_a_test_s_own_dir_is_the_one_jbus_takes(tmp_path, monkeypatch, name):
    asked, _ = named(name)
    monkeypatch.setenv(name, str(tmp_path))
    assert asked() == tmp_path


@pytest.mark.parametrize("name", REAL)
def test_a_test_that_undoes_its_monkeypatch_is_still_on_dirs_of_the_run(monkeypatch, name):
    asked, real = named(name)
    monkeypatch.undo()
    assert asked().resolve() != real.resolve()
