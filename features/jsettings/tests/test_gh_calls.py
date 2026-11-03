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


def test_a_gh_call_logs_its_caller_endpoint_status_and_github_s_limits(gh):
    done = proc.run("gh", "api", "repos/o/r/actions/jobs/900/logs")
    assert (done.returncode, done.stdout) == (1, "out\n")
    assert done.stderr == "gh: You have exceeded a secondary rate limit (HTTP 403)\n"
    [line] = calls(gh)
    assert line.pop("at").endswith("+00:00")
    assert line == {
        "caller": f"{__name__}.test_a_gh_call_logs_its_caller_endpoint_status_and_github_s_limits",
        "endpoint": "/repos/o/r/actions/jobs/900/logs?per_page=1",
        "status": 1,
        "remaining": 4812,
        "retry_after": "60",
        "http": "HTTP/2.0 403 Forbidden",
    }


def test_a_call_gh_made_no_request_for_is_logged_by_its_command(gh, monkeypatch):
    monkeypatch.setenv("PATH", "/nowhere")
    done = proc.ask(["gh", "pr", "list", "--json", "number"])
    assert done is None
    [line] = calls(gh)
    assert (line["endpoint"], line["status"], line["remaining"]) == ("pr list", 127, None)
    assert "retry_after" not in line


def test_other_commands_are_neither_logged_nor_held(gh):
    assert proc.run("true").returncode == 0
    assert not (gh / proc.CALLS).exists()


def test_a_cut_off_debug_log_keeps_why_the_request_failed():
    said = proc.Debug.parse(
        "* Request at now\n* Request to https://api.github.com/graphql\n"
        "> POST /graphql HTTP/1.1\n\nerror connecting to api.github.com\n"
    )
    assert said.stderr == "error connecting to api.github.com\n"
    assert said.requests == ("https://api.github.com/graphql",)


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
