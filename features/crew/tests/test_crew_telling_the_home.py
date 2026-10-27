"""The crew skill takes its brief from the launch message. Where a review's findings go is jbus's
(`features/jbus/tests/test_jbus_reviewed.py`)."""

import hashlib

import pytest

from crew_helpers import BRIEF, said
from test_jbus_kitchen import Kitchen


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path / "kitchen", monkeypatch)
    yield made
    made.close()


def test_a_brief_that_came_in_the_launch_message_is_the_brief_the_skill_reads(kitchen, tmp_path):
    """`jbus` puts the brief under the first line of its launch, and step 1 writes it to disk."""
    brief = BRIEF.split("\n## Result")[0] + (
        "Done when:\n- it is done\nProves it: `make check`\nSize: S\nWhere: `src/alpha/`\n"
        "Design: none, a test\nReview: review+test\nPlaybook: feature\n"
    )
    assert kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=brief)[0] == 0
    sha = hashlib.sha256(brief.encode()).hexdigest()[:12]
    at = ["--word", kitchen.word(), "--sha", sha]
    assert kitchen.main("queue", "approve", "alpha", *at)[0] == 0
    kitchen.poll()
    first, _, below = kitchen.t3.launches[0]["message"].partition("\n")
    assert first == "/crew alpha"
    on_disk = (kitchen.home / "tasks" / "alpha.md").read_text()
    assert on_disk == below.strip() + "\nThread: mcp:thread-1\n"
    home = tmp_path / "a-machine-with-no-brief-on-disk"
    home.mkdir()
    assert said(home, "The review", "mode=", below) == ["review: launch a reviewer"]
