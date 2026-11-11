"""Every `gh` that `jsettings.proc.run` starts is logged in one line under jbus's state, and no
more than `proc.GH_CAP` of them run at one moment on the machine, whichever process starts them.

The `gh` here is a script first on PATH. Asked for gh's debug log (`GH_DEBUG=api`), it writes one
in gh 2.102's shape around its own words on stderr, as the real one does."""

import json
import os
import subprocess
import sys
import time

import pytest

from jsettings import paths, proc

DEBUG = """\
* Request at 2026-11-03 16:18:49.835638133 -0500 EST m=+0.032282830
* Request to https://api.github.com/repos/o/r/actions/jobs/900/logs?per_page=1
> GET /repos/o/r/actions/jobs/900/logs HTTP/1.1
> Host: api.github.com

< HTTP/2.0 403 Forbidden
< Retry-After: 60
< X-Ratelimit-Remaining: 4812
< X-Ratelimit-Reset: 1794234969
< X-Ratelimit-Resource: core

{
  "message": "You have exceeded a secondary rate limit."
}

* Request took 230.036153ms
"""

GH = f"""\
#!/bin/sh
if [ -n "$GH_STARTED" ]; then
    touch "$GH_STARTED/$$"
    while [ ! -e "$GH_GO" ]; do sleep 0.02; done
fi
[ "$GH_DEBUG" = api ] && printf '%s' '{DEBUG}' >&2
echo "gh: You have exceeded a secondary rate limit (HTTP 403)" >&2
echo out
exit 1
"""


@pytest.fixture
def gh(tmp_path, monkeypatch):
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "gh").write_text(GH)
    (bin / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin}:{os.environ['PATH']}")
    return paths.jbus_state_dir()


def calls(state):
    return [json.loads(line) for line in (state / proc.CALLS).read_text().splitlines()]


def passed_on(*command):
    """A helper that only passes a command on, as `jmerge.cli._run` does: never a caller."""
    return proc.run(*command, timeout=10)


def test_a_gh_call_logs_its_caller_endpoint_status_and_github_s_limits(gh):
    done = passed_on("gh", "api", "repos/o/r/actions/jobs/900/logs")
    assert (done.returncode, done.stdout) == (1, "out\n")
    assert done.stderr == "gh: You have exceeded a secondary rate limit (HTTP 403)\n"
    [line] = calls(gh)
    assert line.pop("at").endswith("+00:00")
    caller, _, above = line.pop("caller").partition(" < ")
    assert (
        caller == f"{__name__}.test_a_gh_call_logs_its_caller_endpoint_status_and_github_s_limits"
    )
    assert above and "passed_on" not in above
    assert line == {
        "endpoint": "/repos/o/r/actions/jobs/900/logs?per_page=1",
        "status": 1,
        "remaining": 4812,
        "resource": "core",
        "reset": 1794234969,
        "retry_after": "60",
        "http": "HTTP/2.0 403 Forbidden",
    }


def test_a_call_gh_made_no_request_for_is_logged_by_its_command(gh, monkeypatch):
    monkeypatch.setenv("PATH", "/nowhere")
    done = proc.ask(["gh", "pr", "list", "--json", "number"])
    assert done is None
    [line] = calls(gh)
    assert (line["endpoint"], line["status"], line["remaining"]) == ("pr list", 127, None)
    assert "retry_after" not in line and "reset" not in line


def test_a_state_directory_that_cannot_be_written_costs_the_call_nothing(gh, monkeypatch):
    monkeypatch.setenv("JBUS_STATE_DIR", "/proc/no-such-state")
    done = proc.run("gh", "api", "rate_limit")
    assert (done.returncode, done.stdout) == (1, "out\n")


def test_other_commands_are_neither_logged_nor_held(gh):
    assert proc.run("true").returncode == 0
    assert not (gh / proc.CALLS).exists()


def test_a_seventeenth_gh_waits_while_sixteen_run_in_other_processes(gh, tmp_path, monkeypatch):
    started, go = tmp_path / "started", tmp_path / "go"
    started.mkdir()
    monkeypatch.setenv("GH_STARTED", str(started))
    monkeypatch.setenv("GH_GO", str(go))
    script = "from jsettings import proc; proc.run('gh', 'api', 'rate_limit')"
    runs = [subprocess.Popen([sys.executable, "-c", script]) for _ in range(proc.GH_CAP + 1)]
    try:
        until = time.monotonic() + 30
        while len(list(started.iterdir())) < proc.GH_CAP and time.monotonic() < until:
            time.sleep(0.05)
        time.sleep(0.5)
        assert len(list(started.iterdir())) == proc.GH_CAP
    finally:
        go.touch()
        for one in runs:
            one.wait(30)
    assert len(list(started.iterdir())) == proc.GH_CAP + 1
    lines = calls(gh)
    assert len(lines) == proc.GH_CAP + 1
    assert [line["caller"] for line in lines] == ["__main__.<module>"] * (proc.GH_CAP + 1)
    assert sum("waited" in line for line in lines) >= 1


PAUSED = """\
import os, sys, time
from pathlib import Path
from jsettings import proc

proc.KEPT = 1000
me, at, go = sys.argv[1], Path(os.environ["AT"]), Path(os.environ["GO"])
rename = os.replace


def paused(source, target):
    if str(target).endswith(".old.jsonl"):
        (at / me).touch()
        while not (go / me).exists():
            time.sleep(0.02)
    rename(source, target)


os.replace = paused
proc.run("gh", "api", "rate_limit")
"""


def test_two_processes_that_both_find_the_log_full_keep_it_whole_in_the_old_log(gh, tmp_path):
    """Process a finds the log past KEPT and stops at its rename; process b then logs too. b may
    rename only once a's rename and line are done, and finds then a one-line log, which it keeps:
    gh-calls.old.jsonl still holds the whole log a moved."""
    at, go = tmp_path / "at", tmp_path / "go"
    at.mkdir()
    go.mkdir()
    gh.mkdir(parents=True, exist_ok=True)
    full = "".join(json.dumps({"remaining": n, "pad": "x" * 100}) + "\n" for n in range(20))
    (gh / proc.CALLS).write_text(full)
    env = {**os.environ, "AT": str(at), "GO": str(go)}

    def start(name):
        return subprocess.Popen([sys.executable, "-c", PAUSED, name], env=env)

    def reached(name, seconds):
        until = time.monotonic() + seconds
        while not (at / name).exists() and time.monotonic() < until:
            time.sleep(0.02)
        return (at / name).exists()

    a = start("a")
    b = None
    try:
        assert reached("a", 30)
        b = start("b")
        reached("b", 3)
        (go / "a").touch()
        assert a.wait(30) == 0
        (go / "b").touch()
        assert b.wait(30) == 0
    finally:
        (go / "a").touch()
        (go / "b").touch()
        for one in (a, b):
            if one:
                one.wait(30)
    assert (gh / "gh-calls.old.jsonl").read_text() == full
    assert len(calls(gh)) == 2


def test_a_log_whose_lock_cannot_be_taken_still_gets_its_line(gh):
    gh.mkdir(parents=True, exist_ok=True)
    (gh / f".{proc.CALLS}.lock").mkdir()
    proc.run("gh", "api", "rate_limit")
    assert len(calls(gh)) == 1
