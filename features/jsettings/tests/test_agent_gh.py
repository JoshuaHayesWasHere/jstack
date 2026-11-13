"""A `gh` an agent runs in its own shell is logged in `gh-calls.jsonl` with the caller `agent`
(`jsettings.agent_gh`), as a `gh` that `jsettings.proc.run` starts is logged with the function
that asked for it.

The shell is the one Claude Code gives its Bash tool: it sources the file the crew's
SessionStart hook wrote to `CLAUDE_ENV_FILE`. The real `gh` is a script later on PATH that
writes gh's debug log on stderr when asked for it (`GH_DEBUG=api`), as the real one does."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jsettings import paths, proc

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "features" / "crew" / "hooks" / "gh-logged.sh"

DEBUG = """\
* Request at 2026-11-13 01:18:49.835638133 -0500 EST m=+0.032282830
* Request to https://api.github.com/repos/o/r/pulls?state=open
> GET /repos/o/r/pulls?state=open HTTP/1.1
> Host: api.github.com

< HTTP/2.0 200 OK
< X-Ratelimit-Remaining: 4321
< X-Ratelimit-Reset: 1794553522
< X-Ratelimit-Resource: core

[]

* Request took 230.036153ms
"""

GH = f"""\
#!/bin/sh
[ "$GH_DEBUG" = api ] && echo "[git remote -v]" >&2 && printf '%s' '{DEBUG}' >&2
echo "gh's own words" >&2
cat > "$GH_STDIN"
echo "out:$*"
exit 3
"""


@pytest.fixture
def shell(tmp_path, monkeypatch):
    """Run a command in an agent's Bash shell, after the hook ran at its session's start."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "gh").write_text(GH)
    (real / "gh").chmod(0o755)
    (real / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    (real / "python3").chmod(0o755)
    monkeypatch.setenv("PATH", f"{real}:{os.environ['PATH']}")
    monkeypatch.setenv("GH_STDIN", str(tmp_path / "stdin"))
    monkeypatch.delenv("GH_DEBUG", raising=False)
    env_file = tmp_path / "env"
    env_file.touch()
    started = subprocess.run(
        ["sh", str(HOOK)],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)},
        capture_output=True,
        text=True,
    )
    assert started.returncode == 0, started.stderr

    def run(command: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f'. "{env_file}"; {command}'],
            input=stdin,
            capture_output=True,
            text=True,
        )

    return run


def calls():
    log = paths.jbus_state_dir() / proc.CALLS
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_an_agents_gh_is_logged_as_the_agents(shell):
    done = shell("gh api 'repos/o/r/pulls?state=open' --paginate", stdin="given")

    assert (done.returncode, done.stdout, done.stderr) == (
        3,
        "out:api repos/o/r/pulls?state=open --paginate\n",
        "gh's own words\n",
    )
    assert Path(os.environ["GH_STDIN"]).read_text() == "given"
    [line] = calls()
    assert line["caller"].split(" < ")[0] == "agent"
    assert {key: line[key] for key in ("endpoint", "status", "remaining", "resource", "reset")} == {
        "endpoint": "/repos/o/r/pulls?state=open",
        "status": 3,
        "remaining": 4321,
        "resource": "core",
        "reset": 1794553522,
    }


def test_a_gh_jsettings_runs_from_an_agents_shell_is_logged_once(shell, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))

    done = shell(f"'{sys.executable}' -c 'from jsettings import proc; proc.ask([\"gh\", \"pr\"])'")

    assert done.returncode == 0, done.stderr
    assert [line["caller"] for line in calls()] == ["__main__.<module>"]


def test_a_gh_that_asks_github_nothing_writes_no_line(shell, tmp_path):
    (tmp_path / "real" / "gh").write_text('#!/bin/sh\necho "gh version 2.102.0"\n')

    done = shell("gh --version")

    assert (done.returncode, done.stdout) == (0, "gh version 2.102.0\n")
    assert calls() == []
