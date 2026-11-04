"""The refusing hooks the install writes into `~/.codex/hooks.json`, run as Codex runs them.

Each test runs `install.sh` under a temporary `HOME`, as `test_install.py` does, then runs one
hook's command from the file the install wrote, given what Codex gives a `PreToolUse` hook.
"""

import json
import os
import sqlite3
import subprocess

import pytest

from test_install import User, group, pre_tool_use


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


INFRA_FILE = ".config/jbus/config.toml"


def codex_call(tool, given, cwd, session):
    """What Codex gives a `PreToolUse` hook: its own fields beside the ones Claude Code gives."""
    return {
        "session_id": session,
        "turn_id": "a-turn",
        "transcript_path": None,
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.5",
        "permission_mode": "default",
        "tool_name": tool,
        "tool_use_id": "call-1",
        "tool_input": given,
    }


def a_home_codex_runs(home):
    """A jstack checkout under `home` whose root home is the T3 thread `mcp:root`, run by the
    Codex session `codex-root` in T3 Code's store."""
    checkout = home / "repos" / "jstack"
    subprocess.run(["git", "init", "-q", checkout], check=True)
    state = home / ".local" / "state" / "home" / "jstack"
    state.mkdir(parents=True)
    (state / "home-id").write_text("mcp:root\n")
    store = home / ".t3" / "userdata" / "statev2.sqlite"
    store.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store) as db:
        db.execute(
            "create table orchestration_v2_projection_provider_threads"
            " (provider_thread_id text, thread_id text, payload_json text)"
        )
        payload = {"appThreadId": "mcp:root", "nativeThreadRef": {"nativeId": "codex-root"}}
        db.execute(
            "insert into orchestration_v2_projection_provider_threads values (?, ?, ?)",
            ("provider-thread:mcp:root", "mcp:root", json.dumps(payload)),
        )
    return checkout


@pytest.mark.parametrize(
    ("script", "matcher", "tool", "given", "said"),
    [
        (
            "outbound-command.sh",
            "Bash",
            "Bash",
            {"command": "git push --no-verify"},
            "command:1: push-no-verify",
        ),
        (
            "infra-files.sh",
            "Bash|apply_patch|Write|Edit|MultiEdit|NotebookEdit",
            "apply_patch",
            {"command": "\n".join(["*** Begin Patch", "*** Add File: " + INFRA_FILE, "+x"])},
            "jleak: ~/.config/jbus/config.toml is infra's",
        ),
        (
            "agent-sends.sh",
            "mcp__t3[-_]code__t3_thread_send",
            "mcp__t3-code__t3_thread_send",
            {"threadId": "mcp:root", "message": "a line"},
            "agent-sends: refused, a send to mcp:root",
        ),
    ],
)
def test_each_refusing_hook_the_install_writes_for_codex_refuses_a_codex_call(
    user, script, matcher, tool, given, said
):
    """Each hook runs from `~/.codex/hooks.json` as the install wrote it, given what Codex gives
    it, in a session T3 Code's store runs as the root home."""
    user.run()
    written = pre_tool_use(user.codex, script)
    assert written == group(script, user.home, matcher=matcher, refuses=True, harness="codex")
    checkout = a_home_codex_runs(user.home)
    cwd = user.home if script == "infra-files.sh" else checkout
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "JBUS_HOME_DIR")}
    env |= {"HOME": str(user.home), "XDG_CONFIG_HOME": str(user.home / ".config")}
    done = subprocess.run(
        written["hooks"][0]["command"],
        shell=True,
        input=json.dumps(codex_call(tool, given, cwd, "codex-root")),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )
    assert done.returncode == 2, done.stderr
    assert any(line.startswith(said) for line in done.stderr.splitlines()), done.stderr
