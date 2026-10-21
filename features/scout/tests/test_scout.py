import os
import re
import subprocess
import textwrap

import pytest

from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "scout" / "SKILL.md"
NAME = "a demo repo"
SLUG = "find-out"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)


def given(section=None):
    """The shell blocks the scout skill gives under `## section`, or above every section."""
    text = SKILL.read_text()
    if section:
        _, found, text = text.partition(f"\n## {section}\n")
        assert found, f"the scout skill has no section {section}"
    body = re.split(r"^## ", text, flags=re.M)[0]
    return [textwrap.dedent(block) for block in FENCED.findall(body)]


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


class Scene:
    """A user's home directory, a repo of theirs with a worktree, and that repo's home."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        skills = self.user / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "scout").symlink_to(assembled() / "skills" / "scout")
        self.home_dir = self.user / ".local" / "state" / "home" / NAME
        (self.home_dir / "scouts").mkdir(parents=True)
        (self.home_dir / "scouts" / f"{SLUG}.md").write_text("# the request\n")

        self.main = tmp_path / "code" / NAME
        self.main.mkdir(parents=True)
        git(self.main, "init", "-q")
        (self.main / "kept.txt").write_text("as committed\n")
        git(self.main, "add", "kept.txt")
        git(self.main, "commit", "-q", "-m", "start")
        self.worktree = tmp_path / "trees" / SLUG
        git(self.main, "worktree", "add", "-q", str(self.worktree))

    def run(self, block, checkout):
        """Run one of the skill's blocks as a scout does: in one call with the block at the top."""
        (paths,) = given()
        ran = subprocess.run(
            ["sh", "-c", f"{paths}\nS={SLUG}\n{block}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.user)},
            cwd=checkout,
        )
        assert ran.stderr == ""
        return ran.stdout

    def start(self, checkout):
        (block,) = [block for block in given("Start") if "--porcelain" in block]
        return self.run(block, checkout).splitlines()

    def end(self, checkout):
        """The end check's two lists: the lines there at the start, and the lines new since."""
        lists = []
        for line in self.run(given("End")[0], checkout).splitlines():
            if line.endswith(":"):
                lists.append([])
            else:
                lists[-1].append(line)
        there, new = lists
        return there, new

    def home_id(self, checkout):
        return self.run(f'B="$H/scouts/{SLUG}.md"\n{given("End")[1]}', checkout)


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


@pytest.mark.parametrize("checkout", ["main", "worktree"])
def test_the_paths_are_the_repos_home_and_this_repos_templates(scene, checkout):
    printed = scene.run('printf "%s\\n" "$R" "$H" "$T"', getattr(scene, checkout))
    assert printed.splitlines() == [
        NAME,
        str(scene.home_dir),
        str((assembled() / "templates").resolve()),
    ]


def test_a_clean_worktree_ends_with_only_what_the_scout_wrote_into_it(scene):
    assert scene.start(scene.worktree) == []
    assert scene.end(scene.worktree) == ([], [])

    (scene.worktree / "stray.txt").write_text("written by the scout\n")
    assert scene.end(scene.worktree) == ([], ["?? stray.txt"])


def test_a_checkout_dirty_at_the_start_keeps_the_other_threads_lines_apart(scene):
    (scene.main / "kept.txt").write_text("changed by another thread\n")
    (scene.main / "theirs.txt").write_text("written by another thread\n")
    theirs = [" M kept.txt", "?? theirs.txt"]
    assert scene.start(scene.main) == theirs
    assert scene.end(scene.main) == (theirs, [])

    (scene.main / "mine.txt").write_text("written by the scout\n")
    assert scene.end(scene.main) == (theirs, ["?? mine.txt"])

    (scene.main / "mine.txt").unlink()
    assert scene.end(scene.main) == (theirs, [])


def test_the_end_check_run_from_a_subdirectory_still_knows_the_other_threads_lines(scene):
    (scene.main / "kept.txt").write_text("changed by another thread\n")
    (scene.main / "theirs.txt").write_text("written by another thread\n")
    theirs = [" M kept.txt", "?? theirs.txt"]
    assert scene.start(scene.main) == theirs

    (scene.main / "src").mkdir()
    assert scene.end(scene.main / "src") == (theirs, [])

    (scene.main / "src" / "mine.txt").write_text("written by the scout\n")
    assert scene.end(scene.main / "src") == (theirs, ["?? src/"])


def test_a_home_id_file_gives_the_thread_to_tell(scene):
    (scene.home_dir / "home-id").write_text("mcp:thread-one\n")
    assert scene.home_id(scene.worktree).split() == ["mcp:thread-one"]


def test_no_home_id_file_gives_nobody_to_tell(scene):
    assert scene.home_id(scene.worktree) == ""
