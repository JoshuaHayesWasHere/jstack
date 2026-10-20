"""What every test module shares.

The hourly heartbeat is an event on the first pass of each hour, so it would be one more
line in every test that pins what a pass sends. It is off everywhere but in
`test_jbus_alive.py`, which is where it is tested. So are the events of work items, one
for each line of `items.jsonl`: they are off everywhere but in `test_item.py`, and the lines
are written all the same.

Every test runs with a config of jstack's own in a directory of its own, and a jbus state
directory of its own, never the machine's:
it names no user, so the name is the default, and it fixes the zone and its label, so a time
a test pins reads the same on every machine. A test of another config writes one with `user`.

No test starts a unit of the machine's user manager: `systemd-run` on PATH is a fake that
starts the command in a session of its own, as a transient unit would outlive its caller, and
writes what it was asked to `$SYSTEMD_RUN_CALLS` where that is set.

No test leaves a daemon running: one starts it with `daemons.start`, and the autouse fixture
`no_daemons_left` stops it when the test ends, also on a failed assert or a timeout. A pytest
that is killed takes its daemons with it (`tests/daemons.py` says how).

A test that runs a pass asks for the `kitchen`: the fakes of `test_jbus_kitchen`, set up for
one project. Its repo, a checkout and its origin, is a copy of one built once for each worker
in the directory `kitchen_template` gives (`repo_template`), so a kitchen starts no git
process to make it.

A test of `jmerge` asks for the `home` and its pull request, `merged`, from `test_home_merge`;
one of a guarded path asks for `rules`, the package with a list that guards five paths, and
`proven_merged`, a pull request whose review proved the one safety fact at its head, from
`test_jmerge_guarded`. Each imports its module when it is asked for: `test_home_merge` runs
`uv cache dir` as it loads, and a run with no `uv` on PATH that asks for none of them still
loads this file.
"""

import os

import pytest

import daemons
import repo_template
from jbus import health, item, record
from test_jbus_kitchen import Kitchen

no_daemons_left = daemons.no_daemons_left
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
        monkeypatch.setattr(record, "heartbeat", lambda run, last: None)


@pytest.fixture(autouse=True)
def no_health(request, monkeypatch):
    """The health step looks at the machine the test runs on: only its own tests have it."""
    if request.module.__name__ != "test_jbus_health":
        monkeypatch.setattr(health, "watch", lambda config, now, say: [])


@pytest.fixture(autouse=True)
def no_item_events(request, monkeypatch):
    if request.module.__name__ != "test_item":
        monkeypatch.setattr(item, "told", lambda box, made: None)


@pytest.fixture(autouse=True)
def jstack_config(tmp_path_factory, monkeypatch):
    """The path of the config the test runs with. Written again, it is the config from then on."""
    home = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    path = home / "jstack" / "config.toml"
    path.parent.mkdir()
    path.write_text(ZONE)
    return path


@pytest.fixture(autouse=True)
def no_machine_state(tmp_path_factory, monkeypatch):
    """`jroles` and `jbus` read the ledger `LIMITS` names: a test never reads the machine's, and
    a test that sets the variable itself sets it again."""
    monkeypatch.setenv("LIMITS", str(tmp_path_factory.mktemp("state") / "limits"))


@pytest.fixture
def named_user(jstack_config):
    """The settings name a user, so a level and a kind of event had that name once."""
    jstack_config.write_text(NAMED)


@pytest.fixture(scope="session", autouse=True)
def kitchen_template(tmp_path_factory):
    """Where this worker builds the repos every kitchen's `repo` and every `Home` copies.

    They are built on the first copy, so a run that asks for none starts no git process.
    """
    repo_template.root = tmp_path_factory.mktemp("kitchen-template")
    yield
    repo_template.template, repo_template.root = None, None


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


@pytest.fixture
def home(tmp_path):
    import test_home_merge as merge

    return merge.Home(tmp_path)


@pytest.fixture
def merged(home, tmp_path):
    import test_home_merge as merge

    return merge.Merged(home, tmp_path)


@pytest.fixture
def rules(tmp_path):
    import test_jmerge_guarded as guarded

    return guarded.checkout(tmp_path, guarded.LISTED)


@pytest.fixture
def proven_merged(home, tmp_path):
    import test_home_merge as merge
    import test_jmerge_guarded as guarded

    made = merge.Merged(home, tmp_path)
    (made.home.tasks / "alpha.md").write_text(merge.brief(guarded.proven("clean", made.head)))
    return made
