"""The crew skill's "Do the task": the changed files outside the brief's Where, asked of jmerge."""

import os
import subprocess

import test_room as room
from crew_helpers import PullRequest, block
from test_crew_failed_check import in_the_template
from testing.paths import REPO


def test_the_files_outside_the_where_are_asked_of_jmerge_before_the_pull_request_opens(tmp_path):
    """The block runs `jmerge --scope` over the crewmate's branch, and the line it tells the
    crewmate to write for each file it prints is the line that makes it print `wider:`."""
    pr = PullRequest(tmp_path, None, "other.txt")
    user = tmp_path / "user"
    brief = user / ".local" / "state" / "home" / "main" / "tasks" / "a-task.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# a-task: a task\nWhere: `docs/`\n")
    room.uv(pr.stub)
    script = block("Do the task", "jmerge --scope").replace("<slug>", "a-task")
    env = {
        **os.environ,
        "HOME": str(user),
        "PATH": f"{pr.stub}:{room.BIN}:{os.environ['PATH']}",
        "T": str(REPO / "templates"),
    }

    def asked():
        ran = subprocess.run(
            ["sh", "-c", script], capture_output=True, text=True, cwd=pr.work, env=env, check=True
        )
        return ran.stdout.splitlines()

    assert asked() == ["outside: shared.txt"]
    line = "Wider: shared.txt: the task's test reads it"
    assert in_the_template(line)
    brief.write_text(brief.read_text() + f"\n## Result\nStatus: done\n{line}\n")
    assert asked() == ["wider: shared.txt: the task's test reads it"]
