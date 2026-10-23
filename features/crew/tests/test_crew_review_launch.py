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
    assert words[:4] == ["uv", "run", "--project", "$T/.."] and words[4] == "jroles"
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
