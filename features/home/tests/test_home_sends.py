"""The hook that refuses a home's or a reviewer's own `t3_thread_send` to a thread of its repo's
homes and crews, and names the jbus verb that carries what it meant to send.

Each test feeds `features/home/hooks/agent-sends.sh` what Claude Code gives a `PreToolUse` hook,
in a home of the test's own: `HOME` is a temporary folder with T3 Code's store in it, which maps
each Claude session to its thread, the homes' state of a repo named `jstack`, and a checkout of
it. The homes are as they stood on 2026-10-27, so the two sends of that day the census counted
are replayed between the homes they were made between. No test touches the machine's own files.
"""

import json
import os
import sqlite3
import subprocess

import pytest

from testing.paths import REPO

HOOK = REPO / "features" / "home" / "hooks" / "agent-sends.sh"
TOOL = "mcp__t3-code__t3_thread_send"

ROOT_WAS = "mcp:the-root-before"
ROOT = "mcp:the-root"
FLOW = "mcp:the-flow-home"
JVIEW = "mcp:the-jview-home"
ROOT_CREW = "mcp:a-root-crew"
FLOW_CREW = "mcp:a-flow-crew"
REVIEWER = "mcp:a-reviewer"
SCOUT = "mcp:a-scout"
STRANGER = "mcp:a-stranger"
INFRA = "mcp:the-infra-home"
THREADS = (ROOT_WAS, ROOT, FLOW, JVIEW, ROOT_CREW, FLOW_CREW, REVIEWER, SCOUT, STRANGER, INFRA)


def session(thread):
    """The Claude session that runs a thread, one per thread."""
    return f"session-{THREADS.index(thread)}"


def git(*args, cwd):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


def store(home):
    """T3 Code's store as the hook reads it: one provider thread per T3 thread, whose native
    id is the Claude session."""
    path = home / ".t3" / "userdata" / "statev2.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "create table orchestration_v2_projection_provider_threads"
            " (provider_thread_id text, thread_id text, payload_json text)"
        )
        for thread in THREADS:
            payload = {"appThreadId": thread, "nativeThreadRef": {"nativeId": session(thread)}}
            db.execute(
                "insert into orchestration_v2_projection_provider_threads values (?, ?, ?)",
                (f"provider-thread:{thread}", thread, json.dumps(payload)),
            )


def brief(slug, *lines):
    return f"# {slug}: a task\n" + "".join(f"{one}\n" for one in lines)


@pytest.fixture
def home(tmp_path):
    """The jstack homes at 13:55 on 2026-10-27: the root handed off from `ROOT_WAS` to `ROOT`, the
    jview home handed off with no home after it, and the flow home live. A root brief and a flow
    brief each have a crew, the flow one a reviewer too, and a scout has a request. infra is
    another repo with a home of its own."""
    home = tmp_path / "home"
    checkout = home / "repos" / "jstack"
    checkout.mkdir(parents=True)
    git("init", "-q", cwd=checkout)
    git("commit", "-q", "--allow-empty", "-m", "start", cwd=checkout)
    git("worktree", "add", "-q", "-b", "fl-task", str(home / "worktrees" / "fl-task"), cwd=checkout)
    subprocess.run(["git", "init", "-q", home / "repos" / "infra"], check=True)
    store(home)
    state = home / ".local" / "state" / "home"
    jstack = state / "jstack"
    for one in ("tasks", "scouts", "flow", "jview"):
        (jstack / one).mkdir(parents=True)
    (jstack / "home-id").write_text(f"{ROOT}\n")
    (jstack / "handoff.md").write_text(f"# handoff\nWas home: {ROOT_WAS}\n")
    (jstack / "flow" / "home-id").write_text(f"{FLOW}\n")
    (jstack / "flow" / "plan.md").write_text("# flow\n")
    (jstack / "jview" / "plan.md").write_text("# jview\n")
    (jstack / "jview" / "handoff.md").write_text(f"# jview handoff\nWas home: {JVIEW}\n")
    (jstack / "tasks" / "root-task.md").write_text(brief("root-task", f"Thread: {ROOT_CREW}"))
    (jstack / "tasks" / "fl-task.md").write_text(
        brief(
            "fl-task",
            "Home: flow",
            f"Thread: {FLOW_CREW}",
            "",
            "## Result",
            "Status: done",
            f"Reviewer: {REVIEWER} #1",
        )
    )
    (jstack / "scouts" / "a-scout.md").write_text(brief("a-scout", f"Thread: {SCOUT}"))
    (state / "infra").mkdir(parents=True)
    (state / "infra" / "home-id").write_text(f"{INFRA}\n")
    return home


def jview_live(home):
    """The jview home as it was at 12:57 on 2026-10-27, before its handoff: live on `JVIEW`."""
    jview = home / ".local" / "state" / "home" / "jstack" / "jview"
    (jview / "handoff.md").unlink()
    (jview / "home-id").write_text(f"{JVIEW}\n")


def send(home, sender, to, *, cwd=None, tool=TOOL):
    """What the hook exits with and what it says on stderr, for a `t3_thread_send` to `to` made
    by the thread `sender`, which runs in jstack's checkout unless `cwd` names another place."""
    cwd = cwd or home / "repos" / "jstack"
    call = {
        "session_id": session(sender),
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"threadId": to, "message": "a line"},
    }
    env = {k: v for k, v in os.environ.items() if k not in ("JBUS_HOME_DIR", "CLAUDE_PROJECT_DIR")}
    env["HOME"] = str(home)
    done = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(call), capture_output=True, text=True, env=env
    )
    return done.returncode, done.stderr


def refused(home, sender, to, **given):
    code, said = send(home, sender, to, **given)
    assert code == 2, said
    assert said.endswith("\n") and said.count("\n") == 1, said
    assert said.startswith(f"agent-sends: refused, a send to {to}"), said
    return said


@pytest.mark.parametrize(
    ("sender", "to", "names"),
    [
        (ROOT, ROOT, ["this home's own thread", "send nothing"]),
        (FLOW, ROOT, ["jbus stop"]),
        (ROOT, FLOW, ["jbus word --to <project> --message <thread>/<message> --scope flow"]),
        (ROOT, FLOW, ["jbus stop answer flow"]),
        (FLOW, FLOW, ["send nothing"]),
        (ROOT, FLOW_CREW, ["fl-task", "jbus noticed add --for flow"]),
        (REVIEWER, FLOW_CREW, ["fl-task", "send nothing", "review notice"]),
        (REVIEWER, FLOW, ["jbus noticed add --for flow"]),
        (REVIEWER, ROOT, ["jbus noticed add --for root"]),
        (REVIEWER, ROOT_CREW, ["root-task", "jbus noticed add --for root"]),
    ],
)
def test_a_send_between_homes_and_crews_is_refused_with_its_channel(home, sender, to, names):
    said = refused(home, sender, to)
    for one in names:
        assert one in said, said


def test_a_scope_to_another_scope_is_a_finding(home):
    jview_live(home)
    assert "jbus noticed add --for jview" in refused(home, FLOW, JVIEW)


def test_the_jview_send_to_the_handed_off_root_at_12_57_names_the_root_now_and_jbus_stop(home):
    jview_live(home)
    said = refused(home, JVIEW, ROOT_WAS)
    assert "the root home that handed off" in said, said
    assert f"the root home is {ROOT} now" in said, said
    assert "jbus stop" in said, said


def test_the_roots_send_to_the_handed_off_jview_home_at_13_55_says_none_is_there(home):
    said = refused(home, ROOT, JVIEW)
    assert "the jview home that handed off" in said, said
    assert "no thread is the jview home now" in said, said
    assert "--scope jview" in said, said


def test_the_handed_off_root_relaying_to_the_root_now_is_refused(home):
    said = refused(home, ROOT_WAS, ROOT)
    assert "send nothing" in said, said


def test_a_reviewer_in_its_crews_worktree_is_refused_as_from_the_checkout(home):
    worktree = home / "worktrees" / "fl-task"
    assert "review notice" in refused(home, REVIEWER, FLOW_CREW, cwd=worktree)


@pytest.mark.parametrize(
    ("sender", "to"),
    [
        (ROOT, ROOT_CREW),
        (FLOW, FLOW_CREW),
        (ROOT, SCOUT),
        (FLOW, SCOUT),
        (ROOT, INFRA),
        (ROOT, STRANGER),
        (ROOT_CREW, ROOT),
        (FLOW_CREW, FLOW),
        (FLOW_CREW, ROOT),
        (SCOUT, ROOT),
        (STRANGER, FLOW),
    ],
)
def test_a_steer_to_its_own_crew_and_any_send_of_no_home_or_reviewer_passes(home, sender, to):
    assert send(home, sender, to) == (0, "")


def test_another_repos_home_sending_to_a_jstack_home_passes(home):
    assert send(home, INFRA, ROOT, cwd=home / "repos" / "infra") == (0, "")


def test_a_session_t3_does_not_know_passes(home):
    (home / ".t3" / "userdata" / "statev2.sqlite").unlink()
    assert send(home, ROOT, FLOW) == (0, "")


def test_another_tool_passes(home):
    assert send(home, ROOT, FLOW, tool="mcp__t3-code__t3_thread_launch") == (0, "")
