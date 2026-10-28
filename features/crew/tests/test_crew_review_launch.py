"""The crew skill finds the values it needs to launch a reviewer, and says whether to launch one."""

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from crew_helpers import BRIEF, SKILL, said, sections, with_field
from test_home_thread import as_read
from testing.layouts import assembled


def test_the_skill_it_launches_by_is_found_from_any_repo(tmp_path):
    text = as_read(SKILL)
    (setting,) = [line for line in text.splitlines() if line.startswith("T=")]
    ((path, heading),) = re.findall(r'`(\$T/\S+/SKILL\.md)` "([^"]+)"', text)

    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "crew").symlink_to(assembled() / "skills" / "crew")
    elsewhere = tmp_path / "another-repo"
    elsewhere.mkdir()
    found = subprocess.run(
        ["sh", "-c", f'{setting}\nprintf %s "{path}"'],
        capture_output=True,
        env={**os.environ, "HOME": str(user)},
        cwd=elsewhere,
        check=True,
    )
    assert f"## {heading}" in Path(found.stdout.decode()).read_text().splitlines()


@pytest.mark.parametrize(
    ("brief", "mode", "launches"),
    [
        (BRIEF, "review", True),
        (with_field("Review: review"), "review", True),
        pytest.param(
            with_field("Review: review+test"),
            "review",
            True,
            id="a word from before the review ran no test step is read as a review",
        ),
        (with_field("Review: none"), "none", False),
        (with_field("Review: something else"), "review", True),
        pytest.param(
            with_field("Review: review") + "Review: none\n",
            "review",
            True,
            id="only the first Review line is the brief's",
        ),
        (with_field("Review: none") + "Review: review\n", "none", False),
        (BRIEF + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (BRIEF + "Reviewer: none, no launch tool in this session\n", "review", False),
        (BRIEF + "\n## Review\nVerdict: clean\n", "review", False),
        (with_field("Review: review+test") + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (
            with_field("Review: none") + "Reviewer: none, the brief says Review: none\n",
            "none",
            False,
        ),
    ],
)
def test_the_check_before_a_launch_prints_the_mode_and_whether_to_launch(
    brief, mode, launches, tmp_path
):
    (line,) = said(tmp_path, "The review", "launch a reviewer", brief)
    printed, what = line.split(": ", 1)
    assert printed == mode
    assert (what == "launch a reviewer") == launches
    assert launches or what.startswith("launch no reviewer, ")


def test_a_launch_on_a_capped_pool_registers_this_thread_to_be_woken(tmp_path, monkeypatch):
    """The command "The review" runs before a launch, with a review pool whose one instance is
    capped: jroles makes no selection, exits 75 and registers the thread until the cap's end,
    which `jbus poll` wakes (`test_jbus_pool_wake.py`)."""
    from datetime import UTC, datetime, timedelta

    from jroles import ledger, waits
    from jroles.cli import main

    named = r"`(uv run [^`]*jroles review --thread <thread id>)`"
    (command,) = re.findall(named, sections()["The review"])
    words = shlex.split(command.replace("<thread id>", "mcp:the-crew"))
    assert words[:4] == ["uv", "run", "--project", "$T/../source"] and words[4] == "jroles"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LIMITS", str(tmp_path / "state" / "limits"))
    (tmp_path / "config" / "jstack").mkdir(parents=True)
    pool = "claudeAgent_claude_prime"
    roles = f"review: claudeAgent claude-sonnet-5-5 {pool} effort=medium\n"
    (tmp_path / "config" / "jstack" / "roles").write_text(roles)
    now = datetime(2026, 10, 23, 3, 58, tzinfo=UTC)
    until = now + timedelta(minutes=22)
    ledger.write(ledger.Record(pool, "five_hour", ledger.FULL, int(until.timestamp())))
    assert main(words[5:], now=now) == 75
    (wait,) = waits.read(waits.where())
    assert (wait.thread, wait.role, wait.until) == ("mcp:the-crew", "review", until.isoformat())


def launched(tmp_path, roles, pass_, message="<message>"):
    """What the launch block of "The review" prints in a crew's worktree on the branch `alpha`,
    with `jroles` reading the role map `roles`: the real `jroles`, which `uv run` would start."""
    import json
    import sys

    from crew_helpers import block

    main, work = tmp_path / "main", tmp_path / "trees" / "alpha"
    subprocess.run(["git", "init", "-q", "-b", "main", main], check=True)
    git = ["git", "-C", main, "-c", "user.name=t", "-c", "user.email=t@example.test"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "start"], check=True)
    subprocess.run([*git, "worktree", "add", "-q", "-b", "alpha", work], check=True)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "uv").write_text(f'#!/bin/sh\nshift 4\nexec {sys.executable} -m jroles "$@"\n')
    (stub / "uv").chmod(0o755)
    config = tmp_path / "config" / "jstack"
    config.mkdir(parents=True)
    if roles is not None:
        (config / "roles").write_text(roles)
    script = (
        block("The review", "workspaceStrategy")
        .replace("<slug>", "alpha")
        .replace("<thread id>", "mcp:the-crew")
        .replace("<pass>", pass_)
        .replace("<message>", message)
    )
    ran = subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        cwd=work,
        env={
            **os.environ,
            "PATH": f"{stub}:{os.environ['PATH']}",
            "PYTHONPATH": os.pathsep.join(sys.path),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "LIMITS": str(tmp_path / "state" / "limits"),
            "T": str(assembled() / "templates"),
        },
        check=True,
    )
    lines = ran.stdout.splitlines()
    assert all(line.startswith("launch: ") for line in lines), ran
    return work, [json.loads(line.removeprefix("launch: ")) for line in lines]


TWO = (
    "review: claudeAgent claude-sonnet-5-5 claudeAgent effort=medium\nreview: codex gpt-5.5 codex\n"
)


def test_each_reviewer_is_launched_in_the_crews_own_worktree_and_branch(tmp_path):
    """Reviewers launched with no `workspaceStrategy` opened in the main checkout and refused to
    run (cleanup-ux-inbox-pr, 2026-10-26): every call the block prints carries it."""
    work, calls = launched(tmp_path, TWO, "first")
    assert [call["title"] for call in calls] == ["review: alpha, 1", "review: alpha, 2"]
    assert [call["message"] for call in calls] == [
        "/pr-review run alpha 1",
        "/pr-review run alpha 2",
    ]
    for call in calls:
        assert call["workspaceStrategy"] == {
            "type": "existing_worktree",
            "worktreePath": str(work),
            "branch": "alpha",
        }
    assert [call["modelSelection"]["model"] for call in calls] == ["claude-sonnet-5-5", "gpt-5.5"]


def test_a_map_with_no_review_line_gives_one_call_that_inherits_the_model(tmp_path):
    work, (call,) = launched(tmp_path, None, "first")
    assert call == {
        "title": "review: alpha, 1",
        "workspaceStrategy": {
            "type": "existing_worktree",
            "worktreePath": str(work),
            "branch": "alpha",
        },
        "message": "/pr-review run alpha 1",
    }


@pytest.mark.parametrize(
    ("pass_", "title", "message"),
    [
        ("second", "review: alpha, second pass", "/pr-review run alpha again"),
        ("scoped", "review: alpha, scoped", "/pr-review run alpha scoped a..b c..d"),
    ],
)
def test_a_second_or_scoped_pass_is_one_reviewer_in_the_same_worktree(
    tmp_path, pass_, title, message
):
    work, (call,) = launched(tmp_path, TWO, pass_, "/pr-review run alpha scoped a..b c..d")
    assert (call["title"], call["message"]) == (title, message)
    assert call["workspaceStrategy"]["worktreePath"] == str(work)
    assert call["modelSelection"]["model"] == "claude-sonnet-5-5"
