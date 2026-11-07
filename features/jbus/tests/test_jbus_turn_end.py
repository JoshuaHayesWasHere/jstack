"""The `Stop` hook that sends a crew back when its turn ends before its task's end is on record:
with no `## Result`, or with a Result whose pull request opens after its review once that review is
written and no Result names the pull request.

Each test feeds `features/jbus/hooks/turn-end.sh`, which judges with `jbus.crewend`, what Claude
Code and Codex give a `Stop` hook, in a home of the test's own: `HOME` holds T3 Code's store, which
maps each session to its thread, the homes' state of a repo named `Winnifred` with the brief of
`a-task`, the test slots' files and a checkout of the repo on the branch `a-task`. No test touches
the machine's own files.
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime

import pytest

from jgauge import holders, waiters
from test_home_sends import git, session
from test_home_sends import store as t3_store
from testing.paths import REPO

HOOK = REPO / "features" / "jbus" / "hooks" / "turn-end.sh"
CREW = "mcp:the-crew"
STRANGER = "mcp:a-stranger"
REVIEWER = "mcp:the-reviewer"
SLUG = "a-task"
HEAD = "a" * 40
BRIEF = (
    f"# {SLUG}: a task\nDone when:\n- it holds\nPull request: open one when done\n"
    f"Review: review\nThread: {CREW}\n"
)
DESK = (
    "\n## Result\nStatus: done\nDone when: each holds\nProof:\n- the check: exit 0\n"
    f"Branch: {SLUG}   Pull request: after the review\nChanged: a doc\nSteers: none\nLeft: none\n"
)
LAUNCHED = f"Reviewer: {REVIEWER} #1\n"
REVIEW = (
    "\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\nVerdict: clean\n"
    f"Head: {HEAD}   Unchanged by the review: yes\nSent to: not sent\nFindings:\n- none\n"
)
OPENED = (
    "\n## Result, follow-up (2026-11-07, the pull request is open)\nStatus: done\n"
    "Done when: each holds\nProof:\n- the check: exit 0\n"
    f"Branch: {SLUG}   Pull request: https://github.com/o/Winnifred/pull/7\n"
    "Changed: a doc\nSteers: none\nLeft: none\n"
)
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Winnifred's checkout on `a-task`, whose brief names the crew's thread."""
    home = tmp_path / "home"
    checkout = home / "repos" / "Winnifred"
    checkout.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=checkout)
    git("commit", "-q", "--allow-empty", "-m", "start", cwd=checkout)
    git("checkout", "-q", "-b", SLUG, cwd=checkout)
    monkeypatch.setattr("test_home_sends.THREADS", (CREW, STRANGER, REVIEWER))
    t3_store(home)
    (home / ".local" / "state" / "home" / "Winnifred" / "tasks").mkdir(parents=True)
    (home / ".local" / "state" / "locks").mkdir(parents=True)
    write(home, BRIEF)
    return home


def write(home, text):
    (home / ".local" / "state" / "home" / "Winnifred" / "tasks" / f"{SLUG}.md").write_text(text)


def run(home, thread=CREW, *, harness="claude-code", known=True, active=False, hook=HOOK, raw=None):
    """What the hook prints on stdout, after checking that it ended 0 with a JSON object or
    nothing there, as both harnesses read a `Stop` hook's answer."""
    call = {
        "session_id": session(thread) if known else "a-session-of-no-thread",
        "cwd": str(home / "repos" / "Winnifred"),
        "hook_event_name": "Stop",
        "stop_hook_active": active,
    }
    if harness == "codex":
        call |= {"turn_id": "a-turn", "model": "gpt-5", "last_assistant_message": "done"}
    gone = ("JBUS_HOME_DIR", "JBUS_STATE_DIR", "JGAUGE_LOCKS_DIR", "XDG_CONFIG_HOME", "PYTHONPATH")
    env = {k: v for k, v in os.environ.items() if k not in gone} | {"HOME": str(home)}
    done = subprocess.run(
        ["sh", str(hook)],
        input=json.dumps(call) if raw is None else raw,
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else None


@pytest.mark.parametrize("harness", ["claude-code", "codex"])
def test_turn_end_of_a_crew_with_no_result_is_sent_back_to_write_it(home, harness):
    said = run(home, harness=harness)
    assert said is not None and said["decision"] == "block"
    assert "## Result" in said["reason"] and f"tasks/{SLUG}.md" in said["reason"]


def test_turn_end_owing_its_pull_request_after_a_written_review_is_sent_back_to_open_it(home):
    write(home, BRIEF + DESK + LAUNCHED + REVIEW)
    said = run(home)
    assert said is not None and said["decision"] == "block"
    assert "pull request" in said["reason"] and "follow-up Result" in said["reason"]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(BRIEF + DESK, id="no reviewer launched yet"),
        pytest.param(BRIEF + DESK + LAUNCHED, id="the reviewer has not written"),
        pytest.param(BRIEF + DESK + LAUNCHED + REVIEW + OPENED, id="the pull request is open"),
        pytest.param(
            BRIEF + OPENED + DESK + LAUNCHED + REVIEW, id="an earlier Result names the pull request"
        ),
    ],
)
def test_turn_end_of_a_crew_with_its_result_on_record_ends(home, text):
    write(home, text)
    assert run(home) is None


def test_turn_end_after_the_hook_sent_the_turn_back_once_ends(home):
    assert run(home, active=True) is None


def test_turn_end_of_a_thread_the_brief_does_not_name_ends(home):
    assert run(home, STRANGER) is None


def test_turn_end_of_a_session_t3_code_does_not_know_ends(home):
    assert run(home, known=False) is None


def test_turn_end_of_a_crew_that_waits_on_a_test_slot_ends(home):
    locks = home / ".local" / "state" / "locks"
    waiters.register(locks, CREW, "short", 2, ["pytest"], NOW)
    assert run(home) is None


def test_turn_end_of_a_crew_whose_run_holds_a_slot_ends(home):
    locks = home / ".local" / "state" / "locks"
    holders.hold(locks, CREW, "short", os.getpid(), ["pytest"], NOW)
    assert run(home) is None


def test_turn_end_ends_when_the_hook_crashes(home, tmp_path):
    root = tmp_path / "source"
    for one in ("jbus/hooks/turn-end.sh", "jbus/hooks/judge.sh"):
        (root / "features" / one).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "features" / one, root / "features" / one)
    found = root / "features" / "jbus" / "src" / "jbus"
    found.mkdir(parents=True)
    (found / "__init__.py").write_text("")
    (found / "crewend.py").write_text("print('{\"decision\": ')\nraise RuntimeError('broke')\n")
    assert run(home, hook=root / "features" / "jbus" / "hooks" / "turn-end.sh") is None


def test_turn_end_in_a_checkout_whose_branch_names_no_brief_ends(home):
    git("checkout", "-q", "main", cwd=home / "repos" / "Winnifred")
    assert run(home) is None


def test_turn_end_of_a_call_that_is_no_json_ends(home):
    assert run(home, raw="not json") is None
