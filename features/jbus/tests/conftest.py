"""What jbus's tests share beyond the root `conftest.py`."""

import pytest

from testing.jstack_fixtures import ZONE


@pytest.fixture(scope="session", autouse=True)
def jstack_config_of_the_run(tmp_path_factory):
    """Point `XDG_CONFIG_HOME` at the run's own jstack config, in the zone of `jstack_config`,
    under every test's own. A test that calls `monkeypatch.undo()` takes back what
    `jstack_config` set and lands here, not on the desk's `~/.config/jstack/config.toml`."""
    home = tmp_path_factory.mktemp("run-config")
    (home / "jstack").mkdir()
    (home / "jstack" / "config.toml").write_text(ZONE)
    with pytest.MonkeyPatch.context() as run:
        run.setenv("XDG_CONFIG_HOME", str(home))
        yield
