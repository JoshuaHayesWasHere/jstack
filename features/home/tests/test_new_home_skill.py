"""`/new-home <repo>`: the test runs the blocks of the skill on a made-up home directory and repo.

The test takes each block out of `features/home/skills/new-home/SKILL.md`, fills its placeholders as
the skill says, and runs it with `sh`, with `jbus` on PATH as the real command over a made-up
config. `features/repo-guards/tests/test_tool_calls.py` checks the steps that are tool calls against
their tools' schemas.
"""

import os
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

from skill_blocks import COPY, block, blocks, git, linked
from testing.paths import REPO

PROJECT, THREAD = "p-winnie", "mcp:the-home"
FLOW = ".github/workflows/check.yml"
TEMPLATE = REPO / "features/home/templates/check.yml"
IDENTITY = {
    "GIT_AUTHOR_NAME": "a",
    "GIT_AUTHOR_EMAIL": "a@example.com",
    "GIT_COMMITTER_NAME": "a",
    "GIT_COMMITTER_EMAIL": "a@example.com",
}
CONFIG = (
    'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "first"\n'
    'checkout = "/somewhere/first"\nprojectId = "p-first"\n'
)


class Machine:
    """A home directory with `~/repos/Winnie`, jbus's config for another project, `jbus`, and
    the new-home skill linked as a user's install links it."""

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
        jinstall = self.bin / "jinstall"
        jinstall.write_text(f'#!/bin/sh\nexec {sys.executable} -m jinstall.cli "$@"\n')
        jinstall.chmod(0o755)
        linked(self.home, "new-home")

    def run(self, marker, cwd=None, path=None, shell="sh", extra=None, **filled):
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
            **IDENTITY,
        }
        env = {k: v for k, v in {**env, **(extra or {})}.items() if v is not None}
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

    def merge(self, command="<the check command>", shell="sh", extra=None):
        filled = {"the checkout": str(self.repo), "the check command": command}
        return self.run("4 to merge", shell=shell, extra=extra, **filled)

    def origin(self):
        """A bare origin whose default branch is `wip`, with the repo's commits pushed."""
        origin = self.home / "origin.git"
        git(self.home, "init", "-q", "--bare", "-b", "wip", str(origin))
        git(self.repo, "remote", "add", "origin", str(origin))
        git(self.repo, "push", "-q", "origin", "wip")

    def commit(self, name, text):
        (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / name).write_text(text)
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", name)

    def scaffold(self):
        """What `git show jstack-check:.github/workflows/check.yml` prints, or None."""
        done = subprocess.run(
            ["git", "show", f"refs/heads/jstack-check:{FLOW}"],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        return done.stdout if done.returncode == 0 else None

    def sha(self, ref):
        done = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", ref],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        return done.stdout.strip()

    def files(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*") if p.is_file())


def hooks(repo):
    """Step 3's line for a repo that `jinstall --repo` gave both git hooks."""
    return f"3 git hooks: done, 2 ok in {repo}/.git/hooks"


NO_SIGN_IN = (
    "3 jbus sign-in: needs you: jbus t3 login, every go is your word and jbus reads it from T3 Code"
)


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
    line = 'mkdir -p "$H" && touch "$H/plan.md"'
    assert line in block("home", "first home")
    assert line in block("new-home", "THE_TEXT_ENDS_HERE")
    machine.first("Winnie")
    other = machine.home / "by-home"
    made = f"H={other}\nif {line}; then echo made; fi"
    assert subprocess.run(["sh", "-c", made], capture_output=True, text=True).stdout == "made\n"
    listed = [sorted((p.name, p.read_text()) for p in d.iterdir()) for d in (machine.state, other)]
    assert listed[0] == listed[1] == [("plan.md", "")]


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
    for name, text in (("plan.md", ""), ("merge-seen", "0\n")):
        (machine.state / name).write_text(text)
    (machine.state / "home-id").write_text(f"{THREAD}\n")
    was = sorted(p.name for p in machine.state.iterdir())
    assert machine.first("Winnie")[3:] == [
        f"1 state directory: already, {machine.state} has its plan.md",
        f"home-id: {THREAD}",
    ]
    said, signed, hooked = machine.jbus()
    assert (signed, hooked) == (NO_SIGN_IN, hooks(machine.repo))
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
    assert machine.merge("uv run pytest -k 'not slow'") == [
        f"4 to merge: needs you: git -C {machine.repo} remote add origin <the repo's address at "
        "GitHub>, it has no remote named origin, then type /new-home again for the check workflow",
        f"4 to merge: done, wrote uv run pytest -k 'not slow' to {machine.state}/fresh-check, "
        "the repo's check command, which also has jmerge prove each pull request over today's main",
        "switches, the user's alone: off is absent (/nohome repo), merge-off is absent "
        f"(/nohome merge), home-thread holds empty (a home's thread id on one line of "
        f"{machine.state}/home-thread, written by hand)",
    ]
    assert (machine.state / "fresh-check").read_text() == "uv run pytest -k 'not slow'\n"
    assert sorted(p.name for p in machine.state.iterdir()) == sorted([*was, "fresh-check"])
    assert machine.sha("refs/heads/jstack-check") == ""
    assert sorted(p.name for p in machine.state.parent.iterdir()) == ["Winnie"]

    now = machine.config.read_text()
    assert machine.jbus() == [
        "3 jbus project: already, jbus's config has its table",
        NO_SIGN_IN,
        hooks(machine.repo),
    ]
    assert machine.config.read_text() == now
    assert len(list(machine.config.parent.glob("config.toml.*.bak"))) == 1


def test_a_name_the_config_has_for_another_checkout_is_the_users_to_settle(machine):
    other = machine.home / "elsewhere" / "Winnie"
    other.mkdir(parents=True)
    machine.jbus()
    assert machine.jbus(checkout=other) == [
        '3 jbus project: needs you: jbus project add said "refused: the config already has a '
        'project of that name"',
        NO_SIGN_IN,
        f"3 git hooks: needs you: jinstall --repo {other} said:",
        f"install.sh: {other} is no git repository",
    ]


def test_with_no_config_or_no_jbus_the_line_says_what_the_user_does(machine):
    machine.config.unlink()
    assert machine.jbus() == [
        "3 jbus project: needs you: set jbus up once for the machine, as "
        'features/jbus/docs/jbus.md "Set up jbus" says, then type /new-home Winnie again',
        NO_SIGN_IN,
        hooks(machine.repo),
    ]
    assert not machine.config.exists()
    bare = machine.bin.parent / "bare"
    bare.mkdir()
    for tool in ("sh", "basename"):
        (bare / tool).symlink_to(shutil.which(tool, path="/usr/bin:/bin"))
    assert machine.run(
        "jbus project add",
        path=str(bare),
        **{"the checkout": str(machine.repo), "the T3 project id": PROJECT},
    ) == [
        "3 jbus project: needs you: sh install.sh in the checkout that holds this skill, "
        "jbus is not on PATH",
        "3 git hooks: needs you: sh install.sh in the checkout that holds this skill, "
        "jinstall is not on PATH",
    ]


def test_the_sign_in_line_says_needs_you_until_jbus_holds_a_token(machine):
    token = machine.config.with_name("t3.json")
    for stored in (None, "{}\n", '{"token": {}}\n', "not json\n"):
        if stored is not None:
            token.write_text(stored)
        assert machine.jbus()[1] == NO_SIGN_IN
    token.write_text('{"server": "http://127.0.0.1:1", "token": {"access_token": "t"}}\n')
    assert machine.jbus()[1] == "3 jbus sign-in: already, jbus holds a T3 Code token"


def switches(machine, merge_off="absent", holds="empty"):
    return (
        f"switches, the user's alone: off is absent (/nohome repo), merge-off is {merge_off} "
        f"(/nohome merge), home-thread holds {holds} (a home's thread id on one line of "
        f"{machine.state}/home-thread, written by hand)"
    )


def filled(command):
    """The workflow the template makes for `command`: the template with the command on its
    run line, as the repo's first pull request carries it."""
    text = TEMPLATE.read_text()
    assert text.count("<the check command>") == 1
    return text.replace("<the check command>", command)


ALREADY = (
    "4 to merge: already, it has origin, a default branch, a workflow with a check named check, "
    "and fresh-check"
)
BRANCH = (
    f"4 to merge: done, branch jstack-check adds {FLOW} over wip, a job named check that runs "
    "make check: push it and merge it as the repo's first pull request"
)


def test_a_fresh_repo_gets_its_check_workflow_on_a_branch_and_its_fresh_check(machine):
    machine.commit("Makefile", "check:\n\ttrue\n")
    machine.state.mkdir(parents=True)
    origin = machine.home / "origin.git"
    git(machine.home, "init", "-q", "--bare", "-b", "wip", str(origin))
    git(machine.repo, "remote", "add", "origin", str(origin))
    assert machine.merge()[0] == (
        f"4 to merge: needs you: git -C {machine.repo} push -u origin <the default branch>, "
        "origin names no default branch yet or could not be asked, then type /new-home again "
        "for the check workflow"
    )
    assert machine.sha("refs/heads/jstack-check") == ""
    git(machine.repo, "push", "-q", "origin", "wip")
    (machine.state / "fresh-check").unlink()
    (machine.repo / "notes.txt").write_text("the user's work in progress\n")
    git(machine.repo, "checkout", "-q", "-b", "mine")
    status = subprocess.run(
        ["git", "status", "--porcelain", "-b"], cwd=machine.repo, capture_output=True, text=True
    ).stdout

    assert machine.merge() == [
        BRANCH,
        f"4 to merge: done, wrote make check to {machine.state}/fresh-check, the repo's check "
        "command, which also has jmerge prove each pull request over today's main",
        switches(machine),
    ]
    assert machine.scaffold() == filled("make check")
    assert machine.sha("jstack-check^") == machine.sha("wip")
    pinned = re.compile(r"^\s*- uses: (actions/checkout@\S+)", re.M)
    ours = set(pinned.findall((REPO / ".github/workflows/check.yml").read_text()))
    assert set(pinned.findall(machine.scaffold())) == ours != set()
    assert (machine.state / "fresh-check").read_text() == "make check\n"
    assert not (machine.repo / ".github").exists()
    assert (
        subprocess.run(
            ["git", "status", "--porcelain", "-b"], cwd=machine.repo, capture_output=True, text=True
        ).stdout
        == status
    )

    made = machine.sha("refs/heads/jstack-check")
    assert machine.merge() == [
        f"4 to merge: already, branch jstack-check adds {FLOW}: push it and merge it as the "
        "repo's first pull request",
        switches(machine),
    ]
    assert machine.sha("refs/heads/jstack-check") == made

    git(machine.repo, "checkout", "-q", "wip")
    git(machine.repo, "merge", "-q", "--ff-only", "jstack-check")
    (machine.state / "merge-off").touch()
    (machine.state / "home-thread").write_text("mcp:a-home\n")
    was = machine.files()
    assert machine.merge() == [ALREADY, switches(machine, "there", "an id")]
    assert machine.files() == was


def test_a_workflow_on_origins_default_branch_counts_when_another_branch_is_checked_out(machine):
    machine.commit("Makefile", "check:\n\ttrue\n")
    machine.commit(FLOW, filled("make check"))
    machine.origin()
    git(machine.repo, "checkout", "-q", "-b", "old", "HEAD~1")
    machine.state.mkdir(parents=True)
    (machine.state / "fresh-check").write_text("make check\n")
    assert machine.merge() == [ALREADY, switches(machine)]
    assert machine.sha("refs/heads/jstack-check") == ""


def test_a_workflow_of_the_repos_own_named_check_yml_is_never_written_over(machine):
    machine.commit(FLOW, "on:\n  pull_request:\njobs:\n  lint:\n    steps: []\n")
    machine.origin()
    assert machine.merge("npm test")[0] == (
        f"4 to merge: needs you: wip's {FLOW} has no job that reports a check named check: give "
        f"it one, as the template {os.path.realpath(COPY / 'templates')}/check.yml does"
    )
    assert machine.sha("refs/heads/jstack-check") == ""


def test_a_branch_named_jstack_check_that_is_not_this_skills_is_left_as_it_is(machine):
    machine.origin()
    git(machine.repo, "branch", "jstack-check")
    was = machine.sha("refs/heads/jstack-check")
    assert machine.merge("npm test")[0] == (
        f"4 to merge: needs you: the branch jstack-check is not this skill's, it has no {FLOW}: "
        "rename it, then type /new-home again"
    )
    assert machine.sha("refs/heads/jstack-check") == was


def test_a_repo_that_names_no_check_command_gets_one_line_and_no_branch(machine):
    machine.origin()
    machine.state.mkdir(parents=True)
    assert machine.merge("none") == [
        "4 to merge: needs you: the repo names no check command: give it one, such as a check "
        "target in its Makefile, then type /new-home again",
        switches(machine),
    ]
    assert machine.sha("refs/heads/jstack-check") == ""
    assert not (machine.state / "fresh-check").exists()


def test_a_repo_with_a_fresh_check_but_no_workflow_and_no_check_command_is_not_already(machine):
    machine.origin()
    machine.state.mkdir(parents=True)
    (machine.state / "fresh-check").write_text("uv run pytest\n")
    assert machine.merge("none") == [
        "4 to merge: needs you: the repo names no check command: give it one, such as a check "
        "target in its Makefile, then type /new-home again",
        switches(machine),
    ]
    assert machine.sha("refs/heads/jstack-check") == ""


def test_with_no_makefile_check_the_command_must_be_filled_in(machine):
    machine.origin()
    assert machine.merge() == [
        "not filled in: put the repo's check command in place of the placeholder in "
        "the_command, or none where the repo names none"
    ]
    assert machine.sha("refs/heads/jstack-check") == ""


def test_a_fresh_check_with_a_line_is_never_changed(machine):
    machine.commit("Makefile", "check:\n\ttrue\n")
    machine.state.mkdir(parents=True)
    (machine.state / "fresh-check").write_text("jgauge test-slot -- make check-fast\n")
    assert [line for line in machine.merge() if "fresh-check" in line] == []
    assert (machine.state / "fresh-check").read_text() == "jgauge test-slot -- make check-fast\n"


def test_with_no_git_identity_the_line_says_what_git_said_and_no_branch_is_made(machine):
    machine.origin()
    lonely = {name: None for name in IDENTITY} | {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "user.useConfigOnly",
        "GIT_CONFIG_VALUE_0": "true",
    }
    (said, *_) = machine.merge("npm test", extra=lonely)
    lead = f"4 to merge: needs you: git could not commit {FLOW} on a branch jstack-check: "
    assert said.startswith(lead)
    assert len(said) > len(lead)
    assert machine.sha("refs/heads/jstack-check") == ""


def test_with_the_skill_not_installed_the_line_says_to_install_it(machine):
    machine.origin()
    (machine.home / ".claude/skills/new-home").unlink()
    assert machine.merge("npm test")[0] == (
        "4 to merge: needs you: sh install.sh in the checkout that holds this skill, the "
        "template check.yml of new-home is not installed"
    )
    assert machine.sha("refs/heads/jstack-check") == ""


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_under_zsh_a_repo_with_one_yml_workflow_and_no_yaml_one_is_read_as_sh_reads_it(machine):
    machine.origin()
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text("on:\n  pull_request:\njobs:\n  check:\n    steps: []\n")
    machine.state.mkdir(parents=True)
    (machine.state / "fresh-check").write_text("npm test\n")
    expected = [ALREADY, switches(machine)]
    assert machine.merge("npm test", "zsh") == machine.merge("npm test") == expected
    assert machine.sha("refs/heads/jstack-check") == ""


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_under_zsh_the_scaffold_is_the_one_sh_makes(machine, tmp_path):
    machine.commit("Makefile", "check:\n\ttrue\n")
    machine.origin()
    other = Machine(tmp_path / "other")
    other.commit("Makefile", "check:\n\ttrue\n")
    other.origin()
    assert machine.merge(shell="zsh")[0] == BRANCH == other.merge()[0]
    assert machine.scaffold() == other.scaffold() == filled("make check")


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_every_block_starts_by_asking_zsh_to_read_it_as_sh(machine):
    text = (REPO / "features/home/skills/new-home/SKILL.md").read_text()
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
    machine.origin()
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text(f"on:\n  pull_request:\njobs:\n{jobs}")
    machine.merge("npm test")
    assert (machine.scaffold() is None) == reports


def test_a_workflow_on_pull_request_target_alone_does_not_count(machine):
    machine.origin()
    flows = machine.repo / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text("on:\n  pull_request_target:\njobs:\n  check:\n    steps: []\n")
    machine.merge("npm test")
    assert machine.scaffold() == filled("npm test")
