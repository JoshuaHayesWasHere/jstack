"""The crew skill's "Do the task" asks jmerge for the changed files outside the brief's Where,
before the pull request opens and again after each push for a review's findings or a failed
check."""

import os
import subprocess

import test_room as room
from crew_helpers import PullRequest, block
from test_crew_failed_check import in_the_template
from testing.layouts import assembled

NOTHING_NEW = "nothing new: every changed file outside Where has its Wider: line"


def ask(path):
    return f"  ask: Wider: {path}: <why it had to change>, or take {path} out of the diff"


def scoping(tmp_path, result=""):
    """A crewmate's pull request whose brief's Where is `docs/` and whose task changed
    `shared.txt`, and the block that asks `jmerge --scope` of it."""
    pr = PullRequest(tmp_path, None, "other.txt")
    user = tmp_path / "user"
    brief = user / ".local" / "state" / "home" / "main" / "tasks" / "a-task.md"
    brief.parent.mkdir(parents=True)
    brief.write_text(f"# a-task: a task\nWhere: `docs/`\n{result}")
    room.uv(pr.stub)
    script = block("Do the task", "jmerge --scope").replace("<slug>", "a-task")
    env = {
        **os.environ,
        "HOME": str(user),
        "PATH": f"{pr.stub}:{room.BIN}:{os.environ['PATH']}",
        "T": str(assembled() / "templates"),
    }

    def asked():
        ran = subprocess.run(
            ["sh", "-c", script], capture_output=True, text=True, cwd=pr.work, env=env, check=True
        )
        return ran.stdout.splitlines()

    return pr, brief, asked


def test_the_files_outside_the_where_are_asked_of_jmerge_before_the_pull_request_opens(tmp_path):
    """The block runs `jmerge --scope` over the crewmate's branch. For each file that `jmerge`
    prints, the block asks the crewmate for a line, and once the crewmate writes that line, the
    file is not asked for again."""
    _, brief, asked = scoping(tmp_path)

    assert asked() == ["outside: shared.txt", ask("shared.txt")]
    line = "Wider: shared.txt: the task's test reads it"
    assert in_the_template(line)
    brief.write_text(brief.read_text() + f"\n## Result\nStatus: done\n{line}\n")
    assert asked() == [NOTHING_NEW]


def test_a_fix_pushed_after_the_wider_lines_is_asked_of_jmerge_again(tmp_path):
    """After the Result's `Wider:` lines are written, a fix commit inside Where adds nothing to
    what the block prints, and one that adds a file outside Where is named and asked for."""
    result = "\n## Result\nStatus: done\nWider: shared.txt: the task's test reads it\n"
    pr, _, asked = scoping(tmp_path, result)
    assert asked() == [NOTHING_NEW]

    (pr.work / "docs").mkdir()
    pr.commit(pr.work, "docs/fix.md", "a finding's fix\n", "the fix, inside Where")
    assert asked() == [NOTHING_NEW]

    pr.commit(pr.work, "extra.txt", "a finding's fix\n", "the fix, outside Where")
    assert asked() == ["outside: extra.txt", ask("extra.txt")]
