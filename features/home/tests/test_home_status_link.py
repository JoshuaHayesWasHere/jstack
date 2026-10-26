"""A home's status reply ends with the address of the same facts in jbus view. The tests run the
status step's block as a home reads it, in one call with the block at the top, in a made-up home
directory whose repo is a project of a made-up jbus config, with the real `jbus` the skill names."""

import os
import subprocess

import pytest

from skill_blocks import git
from test_home_merge import uv_cache
from test_home_thread import block, paths
from testing.layouts import assembled

LINK = "jbus link"


class Machine:
    """A home directory with the skills, `~/repos/demo`, and jbus's config, which names `demo`
    when `kept` and only another repo when not."""

    def __init__(self, tmp_path, kept=True):
        self.home = tmp_path / "home"
        self.repo = self.home / "repos" / "demo"
        self.config = tmp_path / "config"
        for made in (self.repo, self.config, self.home / ".claude"):
            made.mkdir(parents=True)
        (self.home / ".claude" / "skills").symlink_to(assembled() / "skills")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        name = "demo" if kept else "other"
        toml = self.config / "config.toml"
        toml.write_text(
            f'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "{name}"\n'
            f'checkout = "{self.home / "repos" / name}"\nprojectId = "p-{name}"\n'
            '\n[[project]]\nname = "third"\ncheckout = "/somewhere/third"\nprojectId = "p-3"\n'
        )
        toml.chmod(0o600)

    def status(self, **view):
        env = {
            "HOME": str(self.home),
            "PATH": os.environ["PATH"],
            "GIT_CONFIG_GLOBAL": os.devnull,
            "JBUS_CONFIG_DIR": str(self.config),
            "UV_CACHE_DIR": uv_cache(),
            "UV_OFFLINE": "1",
            **view,
        }
        done = subprocess.run(
            ["sh", "-c", f"{paths('home')}\n{block('home', LINK)}"],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
        )
        assert (done.returncode, done.stderr) == (0, "")
        return done.stdout.splitlines()


@pytest.mark.parametrize(
    ("view", "link"),
    [
        ({}, "http://127.0.0.1:4388/#/demo"),
        ({"JBUS_VIEW_ORIGINS": "https://view.example.test"}, "https://view.example.test/#/demo"),
    ],
)
def test_the_status_step_ends_with_the_projects_page_in_jbus_view(tmp_path, view, link):
    assert Machine(tmp_path).status(**view) == [link]


def test_a_repo_jbus_keeps_no_project_for_gets_no_link(tmp_path):
    assert Machine(tmp_path, kept=False).status() == ["no jview link: jbus has no page for demo"]
