"""What every test module shares. The root `conftest.py` loads it as a pytest plugin, so a test
in a feature's own `tests/` has it too.

jbus sends the hourly heartbeat on the first pass of each hour, so every test that pins what a pass
sends would need one more line. It is off everywhere but in `test_jbus_alive.py`, which tests it.
The events of work items, one for each line of `items.jsonl`, are off in the same way everywhere but
in `test_item.py`. jbus still writes the lines.

Every test runs with its own jstack config in a directory of its own, and its own jbus state
directory, never the machine's. The config names no user, so the name is the default. It fixes the
time zone and its label, so a time that a test pins reads the same on every machine. A test
that needs another config writes one with `user`.

No test starts a unit of the machine's user manager. `systemd-run` on PATH is a fake: it starts
the command in a session of its own, so that the command outlives its caller as a transient
unit would. Where `$SYSTEMD_RUN_CALLS` is set, the fake writes each call it gets into that file.

No test leaves a daemon running: a test starts a daemon with `daemons.start`, and the autouse
fixture `no_daemons_left` stops it when the test ends, also on a failed assert or a timeout. When
pytest is killed, the kernel kills its daemons too (`testing/tests/daemons.py` says how).

A test that runs a pass asks for the `kitchen`: the fakes of `test_jbus_kitchen`, set up for
one project. The kitchen's repo is a checkout and its origin. It is a copy of a repo that
`repo_template` has built once for each worker, in the directory that `kitchen_template` gives,
so a kitchen starts no git process to make its repo.

A test of `jmerge` asks for the `home` and its pull request, `merged`, from `test_home_merge`.
A test of a guarded path asks for two fixtures from `test_jmerge_guarded`: `rules`, the package
with a list that guards five paths, and `proven_merged`, a pull request whose review proved the
one safety fact at its head. Both modules are plugins of the root `conftest.py` too, so every
run loads them. `test_home_merge` runs `uv cache dir` only when a test needs the cache.
"""

import os
import sys

import pytest

import daemons
import repo_template
from jbus import health, item, record
from test_jbus_kitchen import Kitchen
from testing.paths import REPO

no_daemons_left = daemons.no_daemons_left
ZONE = 'timezone = "America/New_York"\ntimezone_label = "ET"\n'
NAMED = f'user = "Robin"\n{ZONE}'
OLD_LEVEL, OLD_EVENT = "robin", "waiting-on-robin"


SYSTEMD_RUN = f"""\
#!/bin/sh
if [ -n "$SYSTEMD_RUN_CALLS" ]; then echo "$*" >> "$SYSTEMD_RUN_CALLS"; fi
while [ $# -gt 0 ]; do
    case $1 in
    --) shift; break ;;
    -*) shift ;;
    *) break ;;
    esac
done
exec "{sys.executable}" -c '
import subprocess, sys
subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, start_new_session=True)
' "$@"
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
    """The health step checks the machine the test runs on, so only `test_jbus_health` runs it."""
    if request.module.__name__ != "test_jbus_health":
        monkeypatch.setattr(health, "watch", lambda config, now, say: [])


@pytest.fixture(autouse=True)
def no_item_events(request, monkeypatch):
    if request.module.__name__ != "test_item":
        monkeypatch.setattr(item, "told", lambda box, made: None)


@pytest.fixture(autouse=True)
def jstack_config(tmp_path_factory, monkeypatch):
    """The path of the config the test runs with. A test that writes the file again changes
    the config from then on."""
    home = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    path = home / "jstack" / "config.toml"
    path.parent.mkdir()
    path.write_text(ZONE)
    return path


@pytest.fixture(autouse=True)
def no_machine_state(tmp_path_factory, monkeypatch):
    """Point `LIMITS` at a ledger of the test's own. `jroles` and `jbus` read the ledger that
    `LIMITS` names, so a test never reads the machine's ledger. A test that needs its own `LIMITS`
    sets the variable again itself."""
    monkeypatch.setenv("LIMITS", str(tmp_path_factory.mktemp("state") / "limits"))


@pytest.fixture(autouse=True)
def homes_state(tmp_path_factory, monkeypatch):
    """Point `JBUS_HOME_DIR` at the run's temporary root, so that `jbus forget`, which deletes
    only inside the homes' state or a repo's git dir, takes a file of a test's `tmp_path` as a
    file of the homes' state. A test that needs another state sets the variable again itself."""
    monkeypatch.setenv("JBUS_HOME_DIR", str(tmp_path_factory.getbasetemp()))


JBUS_DIRS = ("JBUS_CONFIG_DIR", "JBUS_STATE_DIR")


@pytest.fixture(scope="session", autouse=True)
def jbus_dirs_of_the_run(tmp_path_factory):
    """Point `JBUS_CONFIG_DIR` and `JBUS_STATE_DIR` at the run's own directories, under every
    test's own (`jbus_dirs`). A test that calls `monkeypatch.undo()` takes back what it, the
    kitchen and `jbus_dirs` set, and lands here, not on the machine's jbus. On 2026-10-26 such
    an undo, then a pass, ran a pass on the real state with the kitchen's clock."""
    with pytest.MonkeyPatch.context() as run:
        for name in JBUS_DIRS:
            run.setenv(name, str(tmp_path_factory.mktemp(f"run-{name.lower()}")))
        yield


@pytest.fixture(autouse=True)
def jbus_dirs(tmp_path_factory, monkeypatch):
    """Point `JBUS_CONFIG_DIR` and `JBUS_STATE_DIR` at directories of the test's own, so a test
    that sets neither never reaches the machine's jbus (`jbus.config_dir`, `jbus.state_dir`).
    A test, or the kitchen, that needs its own sets the variables again itself."""
    for name in JBUS_DIRS:
        monkeypatch.setenv(name, str(tmp_path_factory.mktemp(name.lower())))


@pytest.fixture(autouse=True)
def no_step_files(monkeypatch):
    """Keep the step's own output and summary files, which GitHub Actions sets for the job that
    runs the suite, out of each test. A script a test runs, `select_tests.py` above all, writes to
    them, and a line it wrote there would be the step's: the check job reads `selection` from the
    output. A test that needs the files sets the variables again itself."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture(scope="session")
def harness_root(tmp_path_factory):
    """A harness's layout as far as a skill's block runs a tool from it: `templates/`, and `source`,
    a link to this checkout. `uv run --project "$T/../source"` runs this checkout's tools."""
    root = tmp_path_factory.mktemp("harness") / "claude-code"
    (root / "templates").mkdir(parents=True)
    (root / "source").symlink_to(REPO)
    return root


@pytest.fixture(autouse=True)
def harness_templates(harness_root, monkeypatch):
    """Set `T` as a skill's block sets it, to the templates of a layout whose `source` is this
    checkout, so a block that a test runs reaches this checkout's tools. A test that needs the
    real templates sets `T` again itself."""
    monkeypatch.setenv("T", str(harness_root / "templates"))


@pytest.fixture
def named_user(jstack_config):
    """Settings that name the user Robin. `OLD_LEVEL` and `OLD_EVENT` are a level and a kind of
    event that once used that name."""
    jstack_config.write_text(NAMED)


@pytest.fixture(scope="session", autouse=True)
def kitchen_template(tmp_path_factory):
    """Where this worker builds the repos that each kitchen's `repo` copies. Each `Home` copies them
    too.

    The first test that asks for a copy builds them, so a run that asks for none starts no git
    process.

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
