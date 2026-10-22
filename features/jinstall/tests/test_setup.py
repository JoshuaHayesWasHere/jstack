"""`install.sh --setup`: one pass over every need. After that pass, a HOME that never had jstack
passes the doctor with `doctor: ok`. Each test runs the script under a temporary `HOME`. It uses
the stand-ins of `test_doctor` for every program the doctor runs, and a `git` that has a user
name set."""

import os
import re
import shutil
import stat
import subprocess
import tomllib

import pytest

from jinstall.__main__ import setup as run_setup
from test_doctor import NIGHTLY, Doctored
from test_install import REPO, SCRUBBED, UNITS, line_for, machine, worktree
from testing.paths import skills

GIT = 'case "$1" in config) echo "Sam Doe" ;; *) echo "git version 2.51.0" ;; esac'
SERVER = "http://127.0.0.1:3773"


class Fresh(Doctored):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.program("git", GIT)
        self.roles = self.home / ".config" / "jstack" / "roles"
        self.jbus_config = self.jbus / "config.toml"
        self.seeded = self.home / ".local" / "state" / "jstack" / "seeded"
        self.created = self.home / ".local" / "state" / "jstack" / "created"

    def setup(self, path=None):
        code, said, _ = self.run_with_stderr("--setup", path=path)
        return code, said


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    return Fresh(tmp_path)


def test_a_fresh_home_is_set_up_in_one_pass_and_the_doctor_then_says_ok(user):
    code, said = user.setup()

    assert code == 0
    assert said[:8] == [
        "already linux",
        "already t3",
        "already claude",
        "already uv",
        "already git",
        "already jq",
        "already gh",
        "already gh sign-in",
    ]
    assert said[8:14] == [
        f"done jbus config {user.jbus_config}",
        f"needs you jbus sign-in {user.token} -> jbus t3 login",
        f"done config {user.config}",
        f"done roles {user.roles}",
        "already lavish-axi",
        f"needs you state repo {user.state} -> git init {user.state}"
        f" && git -C {user.state} remote add origin <url>",
    ]
    assert said[14:16] == [
        "needs you provider inventory -> run infra's install",
        f"needs you limits {user.limits} -> jgauge limits",
    ]
    parts = [*user.parts(), f"optional units {user.units}"]
    assert said[16] == "already generated files are current"
    assert said[17:] == [f"done {part.split(' ', 1)[1]}" for part in parts]
    assert user.doctor()[1][-1] == "doctor: ok"
    assert user.run("--check") == (0, user.every("ok", f"optional units {user.units}"))


def test_it_walks_every_need_the_doctor_lists_once_and_in_order(user):
    said = user.setup()[1]
    words = ("done ", "already ", "needs you ")
    assert all(line.startswith(words) for line in said)
    heads = [line.split(" -> ")[0] for line in said]
    named = [head.split(" ", 2 if head.startswith("needs") else 1)[-1] for head in heads]
    doctored = [line.split(" -> ")[0].split(" ", 2)[2] for line in user.doctor()[1][:-1]]
    assert named == doctored


def test_it_seeds_the_jstack_config_from_the_git_name_and_the_machines_zone(user):
    user.setup()
    assert tomllib.loads(user.config.read_text()) == {"user": "Sam", "timezone": "Europe/Berlin"}


def test_it_seeds_a_role_map_where_every_role_inherits(user):
    user.setup()
    lines = [line for line in user.roles.read_text().splitlines() if not line.startswith("#")]
    assert lines == [
        "crew: inherit",
        "scout: inherit",
        "review: inherit",
        "home: inherit",
        "expert: inherit",
    ]


def test_it_seeds_a_private_jbus_config_that_dispatches_nothing(user):
    user.setup()
    assert stat.S_IMODE(user.jbus_config.stat().st_mode) == 0o600
    assert tomllib.loads(user.jbus_config.read_text()) == {"server": SERVER, "dispatch": False}
    assert sorted(path.name for path in user.units.iterdir()) == sorted(
        [*UNITS, "timers.target.wants"]
    )


def test_the_jbus_server_is_the_one_the_t3_sign_in_names(user):
    user.private(user.token, '{"server": "http://127.0.0.1:4000", "token": {}}')
    user.setup()
    assert tomllib.loads(user.jbus_config.read_text())["server"] == "http://127.0.0.1:4000"


def test_a_second_run_says_only_already_and_needs_you_and_writes_nothing(user):
    user.setup()
    before, created, seeded = user.snapshot(), user.created.read_bytes(), user.seeded.read_bytes()
    code, said = user.setup()
    assert code == 0
    assert {line.split(" ")[0] for line in said} == {"already", "needs"}
    assert line_for(said, "limits") == [f"needs you limits {user.limits} -> jgauge limits"]
    assert user.snapshot() == before
    assert (user.created.read_bytes(), user.seeded.read_bytes()) == (created, seeded)


def test_a_file_that_is_there_is_never_written_over(user):
    user.write(user.config, 'user = "ada"\n')
    user.write(user.roles, "crew: nonsense\n")
    code, said = user.setup()
    assert f"already config {user.config}" in said
    bad = f"needs you roles {user.roles} -> bad line 1: crew: nonsense"
    assert line_for(said, "roles") == [bad]
    assert user.config.read_text() == 'user = "ada"\n'
    assert user.roles.read_text() == "crew: nonsense\n"


def test_a_missing_program_names_the_one_command_to_get_it(user):
    path = user.without("gh")
    assert line_for(user.setup(path=path)[1], "gh") == [
        "needs you gh -> gh",
        "needs you gh sign-in -> gh auth login",
    ]
    user.program("pacman", "exit 0")
    said = user.setup(path=path)[1]
    assert line_for(said, "gh") == [
        "needs you gh -> yay -S github-cli",
        "needs you gh sign-in -> gh auth login",
    ]


def test_a_hard_need_left_to_the_user_exits_1(user):
    user.program("t3", "echo 't3 v0.0.45'")
    user.program("pacman", "exit 0")
    code, said = user.setup()
    assert code == 1
    assert "needs you t3 -> yay -S t3code-nightly-bin" in said
    user.program("t3", f"echo 't3 v{NIGHTLY}'")
    assert user.setup()[0] == 0


def test_uninstall_removes_what_setup_seeded_and_keeps_what_was_changed(user):
    user.setup()
    user.config.write_text(user.config.read_text() + 'timezone_label = "CET"\n')
    code, said = user.run("--uninstall")
    assert code == 0
    assert f"removed roles {user.roles}" in said
    assert f"removed jbus config {user.jbus_config}" in said
    assert f"kept config {user.config} -> yours, it is not as setup wrote it" in said
    assert not user.roles.exists()
    assert not user.jbus_config.exists()
    assert user.config.exists()


def test_uninstall_leaves_a_new_home_as_it_was_after_setup(user):
    user.setup()
    user.run("--uninstall")
    assert user.listing() == []
    assert user.run("--uninstall") == (0, [])


def test_uninstall_keeps_a_config_setup_never_wrote(user):
    user.private(user.jbus_config, f'server = "{SERVER}"\n')
    user.setup()
    said = user.run("--uninstall")[1]
    assert not [line for line in said if "jbus config" in line]
    assert user.jbus_config.exists()


def test_a_plain_install_still_seeds_nothing(user):
    user.run()
    assert not user.config.exists()
    assert not user.roles.exists()
    assert not user.jbus_config.exists()


def test_setup_from_a_linked_worktree_under_the_accounts_own_home_is_refused(tmp_path):
    main, linked = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    refused = run_setup(machine(linked, home, account=home))
    assert (refused.lines, refused.code) == ((), 1)
    assert refused.note == (
        f"install.sh: {linked} is a linked worktree, and HOME is your own: "
        "set up from the main checkout"
    )
    assert list(home.iterdir()) == []


def test_usage_names_setup(user):
    code, said, err = user.run_with_stderr("--setup", "--check")
    assert (code, said) == (2, [])
    assert (
        err == "usage: install.sh [--check | --uninstall | --doctor | --setup | --repo [<path>]]\n"
    )
    assert os.listdir(user.home) == []


def skill_block():
    text = (skills()["setup-pstack"] / "SKILL.md").read_text()
    (found,) = re.findall(r"^```sh\n(.*?)^```$", text, re.M | re.S)
    return found


def test_the_skill_runs_the_setup_of_the_checkout_it_is_linked_from_and_reports(user):
    user.setup()
    env = {k: v for k, v in os.environ.items() if not k.startswith(SCRUBBED)}
    env |= {
        "HOME": str(user.home),
        "PATH": f"{user.stub}:{user.bin}:{os.environ['PATH']}",
        "UV_TOOL_DIR": str(user.tools),
        "UV_LOG": str(user.uv_log),
        "FAKE_SYSTEMCTL_LOG": str(user.systemctl_log),
        "JBUS_CONFIG_DIR": str(user.jbus),
    }
    before = user.snapshot()
    done = subprocess.run(
        ["sh", "-c", skill_block()], env=env, cwd=user.home, capture_output=True, text=True
    )
    said = done.stdout.splitlines()
    assert (done.returncode, done.stderr) == (0, "")
    assert said[0] == f"checkout: {REPO}"
    probed, harness, units, left = 16, 1, 1, 4
    count = probed + harness + len(user.parts()) + units - left
    assert said[-2:] == [f"setup: 0 done, {count} already, 4 needs you, exit 0", "doctor: ok"]
    assert user.snapshot() == before


@pytest.mark.parametrize("zone", ["Nowhere/Fake", "UTC0", "/etc/passwd"])
def test_a_zone_the_loader_would_not_take_is_left_out_and_the_pass_goes_on(user, monkeypatch, zone):
    monkeypatch.setenv("TZ", zone)
    code, said = user.setup()
    assert code == 0
    assert tomllib.loads(user.config.read_text()) == {"user": "Sam"}
    assert said[-1] == f"done units {user.units}"


def no_checkout_behind(home, tmp_path):
    """A HOME whose setup-pstack link leads to a layout whose source has no install.sh, as a
    release's does."""
    source = tmp_path / "share" / "jstack"
    layout = tmp_path / "layout"
    source.mkdir(parents=True)
    (layout / "skills" / "setup-pstack").mkdir(parents=True)
    (layout / "source").symlink_to(source)
    (home / ".claude" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills" / "setup-pstack").symlink_to(layout / "skills" / "setup-pstack")


def narrow_path(tmp_path, **stubs):
    """A PATH of the programs the skill's block runs, and a stand-in for each of `stubs`."""
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    for program in ("realpath", "awk", "tail", "cat"):
        (narrow / program).symlink_to(shutil.which(program))
    for name, text in stubs.items():
        (narrow / name).write_text(text)
        (narrow / name).chmod(0o755)
    return narrow


JINSTALL = """#!/bin/sh
echo "$*" >> "$JINSTALL_LOG"
case "$1" in
--setup) printf 'already linux\ndone patterns x\nneeds you gh sign-in -> gh auth login\n'; exit 1 ;;
--doctor) printf 'ok hard linux\ndoctor: not ok, 1 hard\n'; exit 1 ;;
esac
exit 2
"""


def test_the_skill_on_a_release_runs_jinstall_setup_then_the_doctor(tmp_path):
    home = tmp_path / "home"
    no_checkout_behind(home, tmp_path)
    narrow = narrow_path(tmp_path, jinstall=JINSTALL)
    log = tmp_path / "jinstall.log"
    env = {"HOME": str(home), "PATH": str(narrow), "JINSTALL_LOG": str(log)}

    done = subprocess.run(
        ["/bin/sh", "-c", skill_block()], env=env, cwd=home, capture_output=True, text=True
    )

    assert (done.returncode, done.stderr) == (0, "")
    assert done.stdout.splitlines() == [
        f"release: {narrow / 'jinstall'}",
        "already linux",
        "done patterns x",
        "needs you gh sign-in -> gh auth login",
        "setup: 1 done, 1 already, 1 needs you, exit 1",
        "doctor: not ok, 1 hard",
    ]
    assert log.read_text() == "--setup\n--doctor\n"


def test_the_skill_with_no_checkout_and_no_jinstall_names_the_release_install(tmp_path):
    home = tmp_path / "home"
    no_checkout_behind(home, tmp_path)
    env = {"HOME": str(home), "PATH": str(narrow_path(tmp_path))}

    done = subprocess.run(
        ["/bin/sh", "-c", skill_block()], env=env, cwd=home, capture_output=True, text=True
    )

    said = done.stdout.splitlines()
    assert said[0].startswith("not set up: ")
    assert said[1] == (
        "needs you: curl -fsSL https://github.com/JoshuaHayesWasHere/jstack/releases/latest/"
        "download/install.sh | sh"
    )
