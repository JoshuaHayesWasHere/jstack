"""A `jmerge` that jbus stops at its timeout takes the guards it started down with it.

jbus runs `jmerge` as a pass does (`jbus.passes.Pass.run`, which is `jsettings.proc.run` in the
main checkout), and `subprocess.run` kills `jmerge` alone at the timeout. The guards run in a
session of their own (`jmerge.treeguards.run_guards`), out of reach of that kill, so they have to
end on `jmerge`'s end themselves: else they run on in the unit's cgroup beside the next pass's
`jmerge`. The test runs the real `jmerge` command on a real origin and a fake `gh`
(`test_jmerge_fresh.Kitchen`), with guards that sleep past jbus's timeout."""

import os
import shlex
import sys
import time

import pytest

from jmerge import treeguards
from jsettings import proc
from test_home_merge import uv_cache
from test_jmerge_fresh import AFTER, LINES, SOURCE, Kitchen

TIMEOUT = 20
"""jbus's `JMERGE_TIMEOUT`, lowered: long enough for `jmerge` to start its guards on a loaded CI
machine."""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, {"a.txt": LINES})
    home = made.home
    made.pgid = tmp_path / "guards-pgid"
    guards = f"ps -o pgid= -p $$ > {shlex.quote(str(made.pgid))}; sleep 60"
    (home.state / treeguards.NAME).write_text(guards + "\n")
    jmerge = home.stub / "jmerge"
    jmerge.write_text(f'#!/bin/sh\nPYTHONPATH="{SOURCE}" exec "{sys.executable}" -m jmerge "$@"\n')
    jmerge.chmod(0o755)
    for name, value in {
        "HOME": home.user,
        "JBUS_CONFIG_DIR": home.user / ".config" / "jbus",
        "JBUS_STATE_DIR": home.user / ".local" / "state" / "jbus",
        "JBUS_HOME_DIR": home.user / ".local" / "state" / "home",
        "PATH": f"{home.stub}:{os.environ['PATH']}",
        "STUB": home.stub,
        "ORIGIN": made.origin,
        "LOG": home.state / "merge.log",
        "UV_CACHE_DIR": uv_cache(),
        "UV_OFFLINE": "1",
        "JGAUGE_LOCKS_DIR": tmp_path / "locks",
        "TEST_SLOTS": "1",
    }.items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.delenv("JGAUGE_TEST_SLOT", raising=False)
    yield made
    if made.pgid.exists():
        with_group(made, lambda group: os.killpg(group, 9))


def with_group(kitchen, act):
    """Do `act` to the guards' process group, and say whether there was one to do it to."""
    try:
        act(int(kitchen.pgid.read_text()))
    except ProcessLookupError:
        return False
    return True


def test_a_jmerge_jbus_stops_at_its_timeout_leaves_none_of_its_guards_running(kitchen):
    """Its worktree of the merged tree is left, as before, for the next run to clear."""
    kitchen.crew("two", 7, {"b.txt": "two\n"}, checks=(AFTER,))
    kitchen.on_main({"c.txt": "main\n"})
    kitchen.home.desk_checked()
    ran = proc.run("jmerge", cwd=kitchen.home.main, timeout=TIMEOUT)
    assert isinstance(ran, proc.TimedOut)
    assert kitchen.pgid.exists(), "the guards had not started when jbus stopped jmerge"
    until = time.monotonic() + 5
    while with_group(kitchen, lambda group: os.killpg(group, 0)):
        assert time.monotonic() < until, "the guards outlived the jmerge jbus stopped"
        time.sleep(0.1)
    tree = kitchen.home.state / treeguards.TREE
    (kitchen.home.state / treeguards.NAME).write_text("true\n")
    done = proc.run("jmerge", cwd=kitchen.home.main, timeout=60)
    assert done.returncode == 0, done.stderr
    listed = proc.run("git", "worktree", "list", "--porcelain", cwd=kitchen.home.main).stdout
    assert not tree.exists() and str(tree) not in listed, "the next run left the stopped tree"
