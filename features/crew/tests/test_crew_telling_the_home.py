"""The crew skill's brief from the launch message, and where the findings go."""

import hashlib
import os
import subprocess
import textwrap
from datetime import timedelta

import pytest

from crew_helpers import BRIEF, said
from test_home_thread import as_read
from test_jbus_kitchen import NOW, Kitchen
from testing.paths import REPO


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path / "kitchen", monkeypatch)
    yield made
    made.close()


def test_a_brief_that_came_in_the_launch_message_is_the_brief_the_skill_reads(kitchen, tmp_path):
    """`jbus` puts the brief under the first line of its launch, and step 1 writes that down."""
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


def where_the_findings_go(home):
    """What step 4 of the pr-review skill's "After the review" prints, then whom its
    "Telling the home" finds, for the brief `alpha` in a home's state directory."""
    skill = as_read(REPO / "features" / "pr-review" / "SKILL.md")
    printed = []
    for heading, about in (
        ("### After the review", "crewmate $thread"),
        ("### Telling the home", ""),
    ):
        under = skill.split(f"{heading}\n", 1)[1].split("```sh\n")[1:]
        found = next(text for text in under if about in text).split("```", 1)[0]
        script = 'B="$H/tasks/alpha.md"\n' + textwrap.dedent(found).replace("<slug>", "alpha")
        script = script.replace("<clean, findings or not run>", "findings")
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "H": str(home)},
            check=True,
        )
        printed.append(ran.stdout.strip())
    return printed[0].split(":")[0], printed[1]


def test_with_no_home_the_findings_go_to_the_thread_line_as_they_do_with_one(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    for home in ("", "mcp:a-home\n"):
        (kitchen.home / "home-id").write_text(home)
        assert where_the_findings_go(kitchen.home)[0] == "crewmate mcp"


def test_findings_with_no_thread_line_and_no_home_are_written_not_sent_and_jbus_parks_them(
    kitchen,
):
    """The reviewer writes the `Sent to:` line the pr-review skill gives for no home, and
    the next pass of jbus reads it."""
    from jbus import threads

    review = (
        "\n## Review\nVerdict: findings\nFindings:\n- warning a.py:1 wrong\n"
        "Sent to: not sent, no home\n"
    )
    brief = kitchen.brief("alpha", review)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    (kitchen.home / "home-id").write_text("")
    assert where_the_findings_go(kitchen.home) == ("home", "")
    kitchen.poll()
    assert kitchen.lines("condition") == [
        "condition alpha: review findings with no thread to send them to"
    ]
    (kitchen.home / "home-id").write_text("mcp:a-home\n")
    assert where_the_findings_go(kitchen.home) == ("home", "mcp:a-home")
    (kitchen.home / "home-id").write_text("")
    brief.write_text(brief.read_text().replace("\n## Review", "Thread: mcp:crew\n\n## Review"))
    assert where_the_findings_go(kitchen.home)[0] == "crewmate mcp"
    kitchen.poll(NOW + timedelta(minutes=3))
    ((tool, given),) = [call for call in kitchen.t3.calls if call[0] == "t3_thread_send"]
    assert given["message"].startswith(threads.RELAY + "\n\n## Review\n")
    assert (given["threadId"], kitchen.lines("relayed")) == ("mcp:crew", ["relayed alpha"])
