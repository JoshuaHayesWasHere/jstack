"""Helpers that the tests of a skill's shell blocks share. They lift each block out of the skill
in the form an agent reads, and run it under a home directory and in a repository that each
test makes. They also link the skill into the place where a user's install puts it. The tests
of each skill's own feature import these by the module's bare name."""

import os
import re
import subprocess
import textwrap
import time

import pytest

from test_home_thread import as_read
from testing.layouts import assembled
from testing.paths import skills

SKILLS = skills()
COPY = assembled()
READ_SET = ("features/*/SKILL.md", "features/*/references/", "features/*/skills/")
DAY = 24 * 60 * 60
FROM_ROOT = re.compile(r"`((?:playbooks|principles|skills)/[^`<>*\s]+\.md)`")


def blocks(text, language):
    """The body of every fenced block of `language` in a skill, in order, with the indent taken
    off."""
    found = re.findall(rf"^([ \t]*)```{language}\n(.*?)^\1```$", text, re.M | re.S)
    return [textwrap.dedent(body) for _, body in found]


def block(skill, marker):
    """The one `sh` block that has `marker` in it, in the skill named `skill`. The function
    reads the skill as an agent reads it."""
    (found,) = [b for b in blocks(as_read(SKILLS[skill] / "SKILL.md"), "sh") if marker in b]
    return found


def run(body, cwd, home, before="", session=None):
    """Run a block as its reader would, in `cwd`, with `home` as the home directory."""
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": os.devnull}
    if session:
        env["CLAUDE_CODE_SESSION_ID"] = session
    done = subprocess.run(
        ["sh", "-c", before + body], cwd=cwd, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout.splitlines()


def git(cwd, *args):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "a",
        "GIT_AUTHOR_EMAIL": "a@example.com",
        "GIT_COMMITTER_NAME": "a",
        "GIT_COMMITTER_EMAIL": "a@example.com",
    }
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def aged(path, days, text="{}\n"):
    """Write `path` and set its last change `days` days back. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    then = time.time() - days * DAY
    os.utime(path, (then, then))
    return path


def transcripts(home, directory):
    return home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(directory))


def linked(home, name, to=None):
    """Link a skill from `~/.claude/skills` into the harness copy, the same link that a user's
    install makes."""
    link = home / ".claude" / "skills" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(to or COPY / "skills" / name)


def prints_the_root_and_names_only_files_under_it(name, repo, home):
    """Check a skill that names files outside its own directory, by paths from the repo's
    root. The test links the skill the way a user's install does. The skill's block then prints
    that root, and every file the skill names is under the root."""
    linked(home, name)
    (root,) = run(block(name, "no root:"), repo, home)
    assert root == str(COPY)
    named = {
        path
        for file in (COPY / "skills" / name).rglob("*.md")
        for path in FROM_ROOT.findall(file.read_text())
    }
    assert named != set()
    assert sorted(path for path in named if not (COPY / path).is_file()) == []


def says_it_is_no_link_into_the_repo(name, repo, home):
    """Check the same skill with no link, and then with a folder in the link's place. Each
    time, its block says that the skill is no link into the repo."""
    said = f"no root: ~/.claude/skills/{name} is not a link into the repo this skill lives in"
    assert run(block(name, "no root:"), repo, home) == [said]
    (home / ".claude" / "skills" / name).mkdir(parents=True)
    assert run(block(name, "no root:"), repo, home) == [said]


@pytest.fixture
def home(tmp_path):
    made = tmp_path / "home"
    made.mkdir()
    return made


@pytest.fixture
def repo(tmp_path):
    """A repository called demo, on `main`, with one commit."""
    made = tmp_path / "demo"
    made.mkdir()
    git(made, "init", "-q", "-b", "main")
    (made / "a.txt").write_text("one\n")
    git(made, "add", "a.txt")
    git(made, "commit", "-q", "-m", "one")
    return made


@pytest.fixture
def outside(tmp_path):
    """A directory that is in no repository, whatever the temporary directory is in."""
    made = tmp_path / "outside"
    made.mkdir()
    (made / ".git").write_text("not a repository\n")
    return made
