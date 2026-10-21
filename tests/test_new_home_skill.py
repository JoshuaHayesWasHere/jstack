"""`/new-home <repo>`: the blocks of the skill are run, on a made-up home directory and repo.

Each block is taken out of `skills/new-home/SKILL.md`, its placeholders filled as the skill
says, and run by `sh` with `jbus` on PATH as the real command over a made-up config. The
steps that are tool calls are held to their tools' schemas by `features/repo-guards/tests/test_tool_calls.py`.
"""

import os
import shutil
import subprocess
import sys
import tomllib

import pytest

from skill_blocks import block, blocks, git
from testing.paths import REPO

PROJECT, THREAD = "p-winnie", "mcp:the-home"
CONFIG = (
    'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "first"\n'
    'checkout = "/somewhere/first"\nprojectId = "p-first"\nwebhook_url = "http://127.0.0.1:1/w"\n'
    'webhook_key = "not-a-real-key"\n'
)


class Machine:
    """A home directory with `~/repos/Winnie`, jbus's config for another project, and `jbus`."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.repo = self.home / "repos" / "Winnie"
        self.state = self.home / ".local/state/home/Winnie"
        self.config = self.home / ".config/jbus/config.toml"
        self.bin = tmp_path / "bin"
        for made in (self.repo, self.config.parent, self.bin):
            made.mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "wip")
        git(self.repo, "config", "maintenance.auto", "false")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        self.config.write_text(CONFIG)
        self.config.chmod(0o600)
        jbus = self.bin / "jbus"
        jbus.write_text(f'#!/bin/sh\nexec {sys.executable} -m jbus "$@"\n')
        jbus.chmod(0o755)

    def run(self, marker, cwd=None, path=None, shell="sh", **filled):
        body = block("new-home", marker)
        for placeholder, value in filled.items():
            assert f"<{placeholder}>" in body
            body = body.replace(f"<{placeholder}>", value)
        env = {
            "HOME": str(self.home),
            "PATH": path or f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "JBUS_CONFIG_DIR": str(self.config.parent),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "PYTHONPATH": str(REPO / "src"),
        }
        done = subprocess.run(
            [shell, "-c", body], cwd=cwd or self.home, env=env, capture_output=True, text=True
        )
        assert (done.returncode, done.stderr) == (0, "")
        return done.stdout.splitlines()

    def first(self, typed):
        return self.run("THE_TEXT_ENDS_HERE", **{"the text after /new-home": typed})

    def jbus(self, checkout=None, project=PROJECT):
        return self.run(
            "jbus project add",
            **{"the checkout": str(checkout or self.repo), "the T3 project id": project},
        )

    def merge(self, shell="sh"):
        return self.run("4 to merge", shell=shell, **{"the checkout": str(self.repo)})

    def files(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*") if p.is_file())


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


def test_typed_with_nothing_it_says_what_it_needs_and_makes_nothing(machine):
    was = machine.files()
    assert machine.first("") == [
        "needs a repo: type /new-home <repo>, a repo's path or its folder name under ~/repos. "
        "Nothing is done."
    ]
    assert machine.files() == was


@pytest.mark.parametrize("typed", ["Nowhere", "~/plain", "{home}/plain"])
def test_a_path_that_is_no_git_repository_is_said_and_nothing_is_made(machine, typed):
    plain = machine.home / "plain"
    plain.mkdir()
    (plain / ".git").write_text("not a repository\n")
    was = machine.files()
    at = machine.home / "repos/Nowhere" if typed == "Nowhere" else plain
    assert machine.first(typed.format(home=machine.home)) == [
        f"not a git repository: {at} is no checkout of one. Nothing is done."
    ]
    assert machine.files() == was


@pytest.mark.parametrize("typed", ["Winnie", "~/repos/Winnie", "{home}/repos/Winnie", "worktree"])
def test_a_repo_is_found_by_its_folder_name_its_path_or_one_of_its_worktrees(machine, typed):
    tree = machine.home / "trees" / "fix"
    git(machine.repo, "worktree", "add", "-q", str(tree), "-b", "fix")
    typed = str(tree) if typed == "worktree" else typed.format(home=machine.home)
    assert machine.first(typed) == [
        "repo: Winnie",
        f"checkout: {machine.repo}",
        f"state: {machine.state}",
        f"1 state directory: done, made {machine.state}",
        "home-id: none",
    ]
    assert machine.first(typed)[3] == f"1 state directory: already, {machine.state} has its plan.md"


def test_the_state_directory_is_the_one_the_home_skills_first_home_step_makes(machine):
    line = 'mkdir -p "$H" && touch "$H/plan.md" "$H/notes.md"'
    assert line in block("home", "first home")
    assert line in block("new-home", "THE_TEXT_ENDS_HERE")
    machine.first("Winnie")
    other = machine.home / "by-home"
    made = f"H={other}\nif {line}; then echo made; fi"
    assert subprocess.run(["sh", "-c", made], capture_output=True, text=True).stdout == "made\n"
    listed = [sorted((p.name, p.read_text()) for p in d.iterdir()) for d in (machine.state, other)]
    assert listed[0] == listed[1] == [("notes.md", ""), ("plan.md", "")]


def test_a_folder_of_a_party_is_no_repos_home(machine):
    party = machine.home / "repos" / "_jez"
    party.mkdir()
    git(party, "init", "-q")
    assert machine.first("_jez") == [
        f"not a repo's home: a folder named _jez under {machine.state.parent} is a party's, "
        "as an expert's is. Nothing is done."
    ]
    assert not (machine.state.parent / "_jez").exists()


def test_a_home_started_by_hand_gets_only_what_it_lacks(machine):
    machine.state.mkdir(parents=True)
    for name, text in (("plan.md", ""), ("notes.md", ""), ("merge-seen", "0\n")):
        (machine.state / name).write_text(text)
    (machine.state / "home-id").write_text(f"{THREAD}\n")
    was = sorted(p.name for p in machine.state.iterdir())
    assert machine.first("Winnie")[3:] == [
        f"1 state directory: already, {machine.state} has its plan.md",
        f"home-id: {THREAD}",
    ]
    (said,) = machine.jbus()
    (backup,) = machine.config.parent.glob("config.toml.*.bak")
    assert said == (
        f"3 jbus project: done, one [[project]] table, the file as it was is {backup}: "
        "the next pass works it, restart no unit"
    )
    assert backup.read_text() == CONFIG
    assert machine.config.read_text().startswith(CONFIG)
    assert tomllib.loads(machine.config.read_text())["project"][1] == {
        "name": "Winnie",
        "checkout": str(machine.repo),
        "projectId": PROJECT,
    }
    assert machine.merge() == [
        f"4 to merge: needs you: git -C {machine.repo} remote add origin <the repo's address at "
        "GitHub>, it has no remote named origin",
        f"4 to merge: needs you: a workflow in {machine.repo}/.github/workflows that runs on "
        "pull_request and has a job named check: jmerge merges on that check alone",
        f"4 to merge: needs you: echo '<the check command, on one line>' > "
        f"{machine.state}/fresh-check, the one line jmerge runs as the repo's local check",
        "switches, the user's alone: off is absent (/nohome repo), merge-off is absent "
        f"(/nohome merge), home-thread holds empty (a home's thread id on one line of "
        f"{machine.state}/home-thread, written by hand)",
    ]
    assert sorted(p.name for p in machine.state.iterdir()) == was
    assert sorted(p.name for p in machine.state.parent.iterdir()) == ["Winnie"]

    now = machine.config.read_text()
    assert machine.jbus() == ["3 jbus project: already, jbus's config has its table"]
    assert machine.config.read_text() == now
    assert len(list(machine.config.parent.glob("config.toml.*.bak"))) == 1


def test_a_name_the_config_has_for_another_checkout_is_the_users_to_settle(machine):
    other = machine.home / "elsewhere" / "Winnie"
    other.mkdir(parents=True)
    machine.jbus()
    assert machine.jbus(checkout=other) == [
        '3 jbus project: needs you: jbus project add said "refused: the config already has a '
        'project of that name"'
    ]


def test_with_no_config_or_no_jbus_the_line_says_what_the_user_does(machine):
    machine.config.unlink()
    assert machine.jbus() == [
        "3 jbus project: needs you: set jbus up once for the machine, as docs/jbus.md "
        '"Set up jbus" says, then type /new-home Winnie again'
    ]
    assert not machine.config.exists()
    bare = machine.bin.parent / "bare"
    bare.mkdir()
    for tool in ("sh", "basename"):
        (bare / tool).symlink_to(f"/usr/bin/{tool}")
    assert machine.run(
        "jbus project add",
        path=str(bare),
        **{"the checkout": str(machine.repo), "the T3 project id": PROJECT},
    ) == [
        "3 jbus project: needs you: sh install.sh in the checkout that holds this skill, "
        "jbus is not on PATH"
    ]


def test_a_repo_that_lacks_nothing_for_a_merge_says_already_and_no_switch_is_written(machine):
    origin = machine.home / "origin.git"
    git(machine.home, "init", "-q", "--bare", "-b", "wip", str(origin))
    git(machine.repo, "remote", "add", "origin", str(origin))
    assert machine.merge()[0] == (
        f"4 to merge: needs you: git -C {machine.repo} push -u origin <the default branch>, "
        "origin names no default branch yet or could not be asked"
    )
    git(machine.repo, "push", "-q", "origin", "wip")
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text("on:\n  pull_request:\njobs:\n  lint:\n    steps: []\n")
    (machine.repo / "Makefile").write_text("check:\n\ttrue\n")
    machine.state.mkdir(parents=True)
    assert machine.merge()[:2] == [
        f"4 to merge: needs you: a workflow in {flows} that runs on pull_request and has a job "
        "named check: jmerge merges on that check alone",
        f"4 to merge: needs you: echo 'make check' > {machine.state}/fresh-check, the one line "
        "jmerge runs as the repo's local check",
    ]
    (flows / "ci.yml").write_text("on:\n  pull_request:\njobs:\n  check:\n    steps: []\n")
    (machine.state / "fresh-check").write_text("make check\n")
    (machine.state / "merge-off").touch()
    (machine.state / "home-thread").write_text("mcp:a-home\n")
    was = machine.files()
    assert machine.merge() == [
        "4 to merge: already, it has origin, a default branch, a workflow with a check named "
        "check, and fresh-check",
        "switches, the user's alone: off is absent (/nohome repo), merge-off is there "
        f"(/nohome merge), home-thread holds an id (a home's thread id on one line of "
        f"{machine.state}/home-thread, written by hand)",
    ]
    assert machine.files() == was


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_under_zsh_a_repo_with_one_yml_workflow_and_no_yaml_one_is_read_as_sh_reads_it(machine):
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text("on:\n  pull_request:\njobs:\n  check:\n    steps: []\n")
    assert machine.merge("zsh") == machine.merge()
    assert [line for line in machine.merge("zsh") if "a workflow" in line] == []


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_every_block_starts_by_asking_zsh_to_read_it_as_sh(machine):
    text = (REPO / "skills/new-home/SKILL.md").read_text()
    assert len(blocks(text, "sh")) == 3
    for body in blocks(text, "sh"):
        done = subprocess.run(["zsh", "-c", body], cwd=machine.home, capture_output=True, text=True)
        assert (done.returncode, done.stderr) == (0, "")
        assert done.stdout != ""


@pytest.mark.parametrize(
    ("jobs", "reports"),
    [
        ("  check:\n    steps: []\n", True),
        ("  lint:\n    name: check\n    steps: []\n", True),
        ('  lint:\n    name: "check"  # the one jmerge waits for\n    steps: []\n', True),
        ("  check:\n    name: Lint\n    steps: []\n", False),
        ("  lint:\n    steps:\n      - name: check\n        run: make check\n", False),
        ("  lint:\n    steps: []\n    with:\n      check: true\n", False),
        ("  check:\n    strategy:\n      matrix:\n        python: [3.12]\n    steps: []\n", False),
    ],
)
def test_a_workflow_counts_only_when_a_job_reports_a_check_named_check(machine, jobs, reports):
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text(f"on:\n  pull_request:\njobs:\n{jobs}")
    lacks = [line for line in machine.merge() if "a workflow in" in line]
    assert len(lacks) == (0 if reports else 1)


def test_a_workflow_on_pull_request_target_alone_does_not_count(machine):
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text("on:\n  pull_request_target:\njobs:\n  check:\n    steps: []\n")
    assert len([line for line in machine.merge() if "a workflow in" in line]) == 1
