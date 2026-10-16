"""What every test module shares.

The hourly heartbeat is an event on the first pass of each hour, so it would be one more
line in every test that pins what a pass sends. It is off everywhere but in
`test_jbus_alive.py`, which is where it is tested.

Every test runs with a config of jstack's own in a directory of its own, never the machine's:
it names no user, so the name is the default, and it fixes the zone and its label, so a time
a test pins reads the same on every machine. A test of another config writes one with `user`.

No test starts a unit of the machine's user manager: `systemd-run` on PATH is a fake that
starts the command in a session of its own, as a transient unit would outlive its caller, and
writes what it was asked to `$SYSTEMD_RUN_CALLS` where that is set.

A test that runs a pass asks for the `kitchen`: the fakes of `test_jbus_kitchen`, set up for
one project.
"""

import os

import pytest

from jbus import cli
from test_jbus_kitchen import Kitchen

ZONE = 'timezone = "America/New_York"\ntimezone_label = "ET"\n'
NAMED = f'user = "Robin"\n{ZONE}'
OLD_LEVEL, OLD_EVENT = "robin", "waiting-on-robin"


SYSTEMD_RUN = """\
#!/bin/sh
if [ -n "$SYSTEMD_RUN_CALLS" ]; then echo "$*" >> "$SYSTEMD_RUN_CALLS"; fi
while [ $# -gt 0 ]; do
    case $1 in
    --) shift; break ;;
    -*) shift ;;
    *) break ;;
    esac
done
setsid "$@" < /dev/null > /dev/null 2>&1 &
"""


@pytest.fixture(autouse=True)
def no_user_units(tmp_path_factory, monkeypatch):
    """The directory of the fake `systemd-run`, first on PATH."""
    bin = tmp_path_factory.mktemp("units")
    (bin / "systemd-run").write_text(SYSTEMD_RUN)
    (bin / "systemd-run").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin}:{os.environ['PATH']}")
    return bin


@pytest.fixture(autouse=True)
def no_heartbeat(request, monkeypatch):
    if request.module.__name__ != "test_jbus_alive":
        monkeypatch.setattr(cli, "heartbeat", lambda run, last: None)


@pytest.fixture(autouse=True)
def jstack_config(tmp_path_factory, monkeypatch):
    """The path of the config the test runs with. Written again, it is the config from then on."""
    home = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    path = home / "jstack" / "config.toml"
    path.parent.mkdir()
    path.write_text(ZONE)
    return path


@pytest.fixture
def named_user(jstack_config):
    """The settings name a user, so a level and a kind of event had that name once."""
    jstack_config.write_text(NAMED)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()
