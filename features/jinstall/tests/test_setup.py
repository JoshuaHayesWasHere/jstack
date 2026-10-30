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
from dataclasses import replace

import pytest

from jinstall.__main__ import setup as run_setup
from jinstall.harnesses import HARNESSES
from jinstall.kinds import StateRepo
from test_doctor import T3_STABLE, Doctored
from test_install import (
    REPO,
    ROOTS,
    SCRUBBED,
    SKILLS,
    T3_GET,
    UNITS_PUT,
    Machine,
    Ran,
    line_for,
    linux_only,
    machine,
    worktree,
)
from testing.paths import skills

GIT = 'case "$1" in config) echo "Sam Doe" ;; *) echo "git version 2.51.0" ;; esac'
SERVER = "http://127.0.0.1:3773"
FOLDS = [f"skills {harness.name}" for harness in HARNESSES]
"""What the line of each harness's skill links names, `<word> skills <harness>: <n> links`."""


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
        "already platform",
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
        f"missing optional jbus sign-in {user.token} -> jbus t3 login",
        f"done config {user.config}",
        f"done roles {user.roles}",
        "already lavish-axi",
        f"missing optional state repo {user.state} -> git init {user.state}"
        f" && git -C {user.state} remote add origin <url>",
    ]
    assert said[14:17] == [
        f"missing optional ci report {user.jbus_config}"
        f" -> ci_report = true in a [[project]] of {user.jbus_config}",
        f"missing optional relay {user.relay_env}"
        f" -> write the relay's keys to {user.relay_env}, as the relay's page says",
        f"missing optional limits {user.limits} -> jgauge limits",
    ]
    links = {f"hard {link}" for link in user.links()}
    parts = [part for part in [*user.parts(), f"optional units {user.units}"] if part not in links]
    done = [f"done {part.split(' ', 1)[1]}" for part in parts]
    folded = [f"done {fold}: {len(SKILLS)} links" for fold in FOLDS]
    assert said[17] == "already generated files are current"
    assert said[18:] == [*done[:3], *folded, *done[3:]]
    assert user.doctor()[1][-1] == "doctor: ok"
    assert user.run("--check") == (0, user.every("ok", f"optional units {user.units}"))


def test_it_walks_every_need_the_doctor_lists_once_and_in_order(user):
    said = user.setup()[1]
    words = ("done ", "already ", "needs you ", "missing optional ")
    assert all(line.startswith(words) for line in said)
    heads = [line.split(" -> ")[0].split(": ")[0] for line in said]
    named = [
        head.split(" ", 2 if head.startswith(("needs", "missing")) else 1)[-1] for head in heads
    ]
    links = {
        str(link): fold
        for fold, root in zip(FOLDS, ROOTS, strict=True)
        for link in user.links()
        if link.parent == user.home / root
    }
    doctored = [line.split(" -> ")[0].split(" ", 2)[2] for line in user.doctor()[1][:-1]]
    folded = [links.get(name, name) for name in doctored]
    runs = [name for at, name in enumerate(folded) if name not in FOLDS or folded[at - 1] != name]
    assert named == runs


def test_a_clean_home_is_set_up_in_at_most_40_lines_with_one_line_for_each_layouts_links(user):
    said = user.setup()[1]
    assert len(said) <= 40
    assert [line for line in said if " links" in line] == [
        f"done {fold}: {len(SKILLS)} links" for fold in FOLDS
    ]
    assert [line for line in user.setup()[1] if " links" in line] == [
        f"already {fold}: {len(SKILLS)} links" for fold in FOLDS
    ]


def test_the_last_line_names_every_need_left_to_the_user_again(user):
    said = user.setup(path=user.without("gh"))[1]
    left = [line.removeprefix("needs you ") for line in said if line.startswith("needs you ")]
    assert [step.split(" -> ")[0] for step in left[:2]] == ["gh", "gh sign-in"]
    assert left[1] == "gh sign-in -> gh auth login"
    assert said[-1] == f"setup: {len(left)} needs you: {'; '.join(left)}"
    assert [line for line in said if line.startswith("setup: ")] == [said[-1]]


def test_with_nothing_left_to_the_user_there_is_no_last_line_of_needs(user):
    assert not any(line.startswith("setup: ") for line in user.setup()[1])


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
    assert sorted(path.name for path in user.units.iterdir()) == UNITS_PUT


def test_the_jbus_server_is_the_one_the_t3_sign_in_names(user):
    user.private(user.token, '{"server": "http://127.0.0.1:4000", "token": {}}')
    user.setup()
    assert tomllib.loads(user.jbus_config.read_text())["server"] == "http://127.0.0.1:4000"


def test_a_second_run_says_only_already_and_needs_you_and_writes_nothing(user):
    user.setup()
    before, created, seeded = user.snapshot(), user.created.read_bytes(), user.seeded.read_bytes()
    code, said = user.setup()
    assert code == 0
    assert {line.split(" ")[0] for line in said} == {"already", "missing"}
    assert line_for(said, "limits") == [f"missing optional limits {user.limits} -> jgauge limits"]
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


@linux_only(
    "test_setup.py::test_each_missing_program_is_named_with_the_command_that_gets_it_on_the_platform"
)
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


WSL2 = "install jstack inside WSL2"
T3_PAGE = "https://github.com/pingdotgg/t3code"
CLAUDE_PAGE = "https://code.claude.com/docs/en/setup"


@pytest.mark.parametrize(
    ("platform", "lines"),
    [
        (
            "linux",
            [
                "already platform",
                f"needs you t3 -> {T3_PAGE}",
                f"needs you claude -> {CLAUDE_PAGE}",
                "needs you uv -> uv",
                "needs you git -> git",
                "needs you jq -> jq",
                "needs you gh -> gh",
            ],
        ),
        (
            "darwin",
            [
                "already platform",
                "needs you t3 -> brew install --cask t3-code",
                "needs you claude -> brew install --cask claude-code",
                "needs you uv -> brew install uv",
                "needs you git -> brew install git",
                "needs you jq -> brew install jq",
                "needs you gh -> brew install gh",
            ],
        ),
        (
            "win32",
            [
                f"needs you platform -> this is win32: {WSL2}",
                f"needs you t3 -> {WSL2}",
                f"needs you claude -> {WSL2}",
                f"needs you uv -> {WSL2}",
                f"needs you git -> {WSL2}",
                f"needs you jq -> {WSL2}",
                f"needs you gh -> {WSL2}",
            ],
        ),
    ],
)
def test_each_missing_program_is_named_with_the_command_that_gets_it_on_the_platform(
    tmp_path, platform, lines
):
    bare = machine(REPO, tmp_path / "home", tmp_path / "account")
    done = run_setup(replace(bare, platform=platform))
    assert list(done.lines[:7]) == lines
    assert done.lines[-1].startswith("setup: ")
    assert done.code == 1


@linux_only(
    "test_setup.py::test_each_missing_program_is_named_with_the_command_that_gets_it_on_the_platform"
)
def test_off_arch_t3_and_claude_are_named_by_their_install_pages(user):
    (user.stub / "claude").unlink()
    said = user.setup(path=user.without("t3"))[1]
    assert f"needs you t3 -> {T3_PAGE}" in said
    assert f"needs you claude -> {CLAUDE_PAGE}" in said
    assert f"t3 -> {T3_PAGE}; claude -> {CLAUDE_PAGE}" in said[-1]


@pytest.mark.parametrize(
    ("platform", "pacman", "ask"),
    [
        ("linux", False, "gitleaks"),
        ("linux", True, "yay -S gitleaks"),
        ("darwin", False, "brew install gitleaks"),
        ("win32", False, WSL2),
    ],
)
def test_a_backup_with_no_gitleaks_names_the_command_that_gets_it_on_the_platform(
    tmp_path, platform, pacman, ask
):
    programs = tmp_path / "bin"
    programs.mkdir()
    if pacman:
        (programs / "pacman").write_text("#!/bin/sh\n")
        (programs / "pacman").chmod(0o755)
    state = tmp_path / "state"
    answers = {"rev-parse": Ran(0, f"{state}\n"), "remote": Ran(0, "git@example.com:me/s\n")}
    here = Machine(
        REPO,
        tmp_path,
        {"PATH": str(programs)},
        lambda args: answers[args[3]],
        tmp_path,
        platform=platform,
    )
    assert StateRepo(state).ask(here) == ask


def test_a_hard_need_left_to_the_user_exits_1(user):
    user.program("t3", "echo 't3 v0.1.1'")
    user.program("pacman", "exit 0")
    code, said = user.setup()
    assert code == 1
    assert f"needs you t3 -> {T3_GET}" in said
    user.program("t3", f"echo 't3 v{T3_STABLE}'")
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
    probed, harness, units, left = 17, 1, 1, 5
    parts = len(user.parts()) - len(user.links()) + len(FOLDS)
    count = probed + harness + parts + units - left
    assert said[-2:] == [
        f"setup: 0 done, {count} already, 0 needs you, {left} optional left, exit 0",
        "doctor: ok",
    ]
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
--setup)
    printf 'already platform\ndone patterns x\nneeds you gh sign-in -> gh auth login\n'
    exit 1
    ;;
--doctor) printf 'ok hard platform -> linux\ndoctor: not ok, 1 hard\n'; exit 1 ;;
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
        "already platform",
        "done patterns x",
        "needs you gh sign-in -> gh auth login",
        "setup: 1 done, 1 already, 1 needs you, 0 optional left, exit 1",
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
