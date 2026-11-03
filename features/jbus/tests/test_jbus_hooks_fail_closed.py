"""The two hooks that judge a thread's own calls, `door-command` and `agent-sends`, refuse a call
they cannot judge, and every refusal of a jstack hook is a quiet `hook` event in the jbus log of
the repo the call ran in.

Each test runs a hook from a source tree of its own, a copy of the hook and of
`features/jbus/hooks/judge.sh` beside a judging module the test writes: one that raises, one that
runs past its time, or one that is never reached because the machine has no python. `HOME` holds
the jbus state of a repo named `Winnifred` and a checkout of it, which the call names as its
`cwd`. No test touches the machine's own files.
"""

import json
import os
import shutil
import subprocess

import pytest

from jbus import wake
from test_home_sends import git
from testing.paths import REPO

DOOR = ("door-command", "jbus", "jbus.door", "Bash", {"command": "git push --force origin main"})
SENDS = (
    "agent-sends",
    "home",
    "jbriefs.sends",
    "mcp__t3-code__t3_thread_send",
    {"threadId": "mcp:a-home", "message": "done"},
)
HOOKS = pytest.mark.parametrize("hook", [DOOR, SENDS], ids=["door-command", "agent-sends"])
RAISES = "raise RuntimeError('the judge broke')\n"
SLEEPS = "import time\ntime.sleep(30)\n"


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    checkout = home / "repos" / "Winnifred"
    checkout.mkdir(parents=True)
    git("init", "-q", cwd=checkout)
    (home / ".local" / "state" / "jbus" / "Winnifred").mkdir(parents=True)
    return home


def tree(root, hook, body):
    """A source tree whose hook `hook` judges with a module that runs `body`."""
    name, feature, module, _, _ = hook
    package, _, leaf = module.partition(".")
    for one in (f"{feature}/hooks/{name}.sh", "jbus/hooks/judge.sh"):
        (root / "features" / one).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "features" / one, root / "features" / one)
    found = root / "features" / package / "src" / package
    found.mkdir(parents=True)
    (found / "__init__.py").write_text("")
    (found / f"{leaf}.py").write_text(body)
    return root / "features" / feature / "hooks" / f"{name}.sh"


def run(home, script, hook, **env):
    _, _, _, tool, given = hook
    call = {
        "session_id": "a-session",
        "cwd": str(home / "repos" / "Winnifred"),
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": given,
    }
    gone = ("JBUS_HOME_DIR", "JBUS_STATE_DIR", "PYTHONPATH")
    environment = {k: v for k, v in os.environ.items() if k not in gone} | {"HOME": str(home)}
    done = subprocess.run(
        ["sh", str(script)],
        input=json.dumps(call),
        capture_output=True,
        text=True,
        env=environment | env,
        timeout=20,
    )
    return done.returncode, done.stderr


def logged(home):
    """The `hook` events of Winnifred's jbus log, as `jbus events` reads them."""
    found = wake.entries(home / ".local" / "state" / "jbus" / "Winnifred")
    return [one for one in found if one["event"] == "hook"]


def refused(home, hook, why):
    """The one `hook` event the refusal wrote, which names the hook, the call and `why`."""
    name, _, _, tool, given = hook
    (event,) = logged(home)
    assert event["hook"] == name and event["loud"] == "quiet"
    assert event["head"] == given.get("command", tool)
    assert why in event["reason"], event
    return event


@HOOKS
def test_a_judge_that_raises_refuses_the_call(home, tmp_path, hook):
    code, said = run(home, tree(tmp_path / "source", hook, RAISES), hook)
    assert code == 2
    assert "RuntimeError: the judge broke" in said
    assert f"{hook[0]}: refused: {hook[2]} ended 1: RuntimeError: the judge broke" in said
    refused(home, hook, "ended 1: RuntimeError: the judge broke")


@HOOKS
def test_a_judge_that_runs_out_of_time_refuses_the_call(home, tmp_path, hook):
    script = tree(tmp_path / "source", hook, SLEEPS)
    code, said = run(home, script, hook, JSTACK_HOOK_SECONDS="1")
    assert code == 2
    assert f"{hook[0]}: refused: {hook[2]} ran past 1 seconds" in said
    refused(home, hook, "ran past 1 seconds")


@HOOKS
def test_no_python_refuses_the_call(home, tmp_path, hook):
    script = tree(tmp_path / "source", hook, "")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("python3", "python"):
        (stubs / name).write_text("#!/bin/sh\nexit 127\n")
        (stubs / name).chmod(0o755)
    code, said = run(home, script, hook, PATH=f"{stubs}:{os.environ['PATH']}")
    assert code == 2
    assert said == f"{hook[0]}: refused: no python 3.12 or newer to judge the call with\n"
    refused(home, hook, "no python 3.12 or newer")


@HOOKS
def test_a_judge_that_lets_the_call_through_logs_nothing(home, tmp_path, hook):
    assert run(home, tree(tmp_path / "source", hook, ""), hook) == (0, "")
    assert logged(home) == []


def test_a_judges_own_refusal_is_logged_with_what_it_said(home, tmp_path):
    line = 'door-command: refused: "it" walks \\\\ through'
    body = f"import sys\nprint('{line}', file=sys.stderr)\nsys.exit(2)\n"
    script = tree(tmp_path / "source", DOOR, body)
    code, said = run(home, script, DOOR)
    assert (code, said) == (2, 'door-command: refused: "it" walks \\ through\n')
    assert refused(home, DOOR, "")["reason"] == 'door-command: refused: "it" walks \\ through'


def test_a_repo_jbus_keeps_no_log_for_still_refuses(home, tmp_path):
    shutil.rmtree(home / ".local" / "state" / "jbus")
    code, _ = run(home, tree(tmp_path / "source", DOOR, RAISES), DOOR)
    assert code == 2
    assert not (home / ".local" / "state" / "jbus").exists()
