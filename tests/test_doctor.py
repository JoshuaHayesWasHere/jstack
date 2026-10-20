"""`install.sh --doctor`: every need of the machine as one line, the last line and the exit
code. Each test runs the script under a temporary `HOME`, with a stand-in for each program
the doctor asks, but for the three that give a kind a machine no argument of the script
reaches."""

import os
import shutil
import sys
import time

import pytest

from jinstall.kinds import Linux, Program, T3Nightly
from test_install import REPO, Machine, Ran, User, line_for, machine

NIGHTLY = "0.0.46-nightly.20261010.2935"
TOKEN = "gho_a_token_the_doctor_never_prints"
PROGRAMS = {
    "t3": f"echo 't3 v{NIGHTLY}'",
    "claude": "echo '2.1.296 (Claude Code)'",
    "git": "echo 'git version 2.51.0'",
    "jq": "echo 'jq-1.7.1'",
    "gh": f'[ "$1 $2" = "auth token" ] && echo {TOKEN}',
    "lavish-axi": "exit 0",
}
JBUS = 'server = "http://127.0.0.1:1"\n'


class Doctored(User):
    """A HOME with every program the doctor asks as a stand-in, each one line of sh."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        for name, line in PROGRAMS.items():
            self.program(name, line)
        self.limits = self.home / ".local" / "state" / "claude" / "limits"
        self.config = self.home / ".config" / "jstack" / "config.toml"
        self.token = self.jbus / "t3.json"
        self.providers = self.home / ".config" / "jstack" / "providers.json"
        self.t3_settings = self.home / ".t3" / "userdata" / "settings.json"

    def program(self, name, line):
        self.script(name, f"#!/bin/sh\n{line}\n")

    def without(self, name):
        """A PATH with every stand-in but `name`, and of the machine's own programs only what
        the script itself runs."""
        (self.stub / name).unlink()
        for own in ("dirname", "python3"):
            found = os.path.realpath(sys.executable) if own == "python3" else shutil.which(own)
            (self.stub / own).symlink_to(found)
        return str(self.stub)

    def private(self, path, value):
        self.write(path, value)
        path.chmod(0o600)

    def doctor(self, path=None):
        code, said, _ = self.run_with_stderr("--doctor", path=path)
        return code, said

    def line(self, part):
        (found,) = line_for(self.doctor()[1], part)
        return found


@pytest.fixture
def user(tmp_path):
    return Doctored(tmp_path)


def test_with_only_optional_needs_missing_the_doctor_says_ok_and_exits_0(user):
    user.run()
    code, said = user.doctor()
    assert (code, said[-1]) == (0, "doctor: ok")
    assert said[:8] == [
        "ok hard linux",
        f"ok hard t3 -> {NIGHTLY}",
        "ok hard claude",
        "ok hard uv",
        "ok hard git -> 2.51.0",
        "ok hard jq -> 1.7.1",
        "ok hard gh",
        "ok hard gh sign-in",
    ]
    assert said[8:14] == [
        f"missing optional jbus config {user.jbus / 'config.toml'} -> jbus does not run without it",
        f"missing optional jbus sign-in {user.token} -> run jbus t3 login",
        f"missing optional limits {user.limits} -> hooks/limits.sh writes it, as the status line",
        f"missing optional config {user.config}"
        " -> defaults are used: user, timezone, timezone_label",
        f"missing optional roles {user.config.with_name('roles')}"
        " -> every role inherits the model of the thread that launches it",
        "ok optional lavish-axi",
    ]
    assert said[14] == f"missing optional provider inventory -> {user.providers}"
    assert said[15:-1] == user.every("ok")


def test_with_a_hard_need_missing_and_one_old_the_doctor_counts_them_and_exits_1(user):
    user.run()
    user.program("gh", "exit 1")
    user.program("t3", "echo 't3 v0.0.45'")
    code, said = user.doctor()
    assert (code, said[-1]) == (1, "doctor: not ok, 2 hard")
    assert line_for(said, "hard t3") == [
        "old hard t3 -> 0.0.45 is the stable build,"
        " needs the nightly build (on Arch: t3code-nightly-bin)"
    ]
    assert line_for(said, "gh sign-in") == ["missing hard gh sign-in -> gh auth login"]


def test_the_doctor_writes_nothing_and_gives_checks_answer_for_each_part_both_print(user):
    code, said = user.doctor()
    hard = [part for part in user.parts() if part.startswith("hard ")]
    assert (code, said[-1]) == (1, f"doctor: not ok, {len(hard)} hard")
    assert user.listing() == []
    checked = user.run("--check")[1]
    assert checked == user.every("missing")
    assert said[15:-1] == checked


def test_the_doctor_prints_the_units_once_they_are_due_as_check_does(user):
    units = user.with_jbus()
    assert line_for(user.doctor()[1], "units") == line_for(user.run("--check")[1], "units")
    assert line_for(user.doctor()[1], "units") == [f"missing {units}"]


def test_the_token_gh_prints_is_in_no_line(user):
    code, said = user.doctor()
    assert "ok hard gh sign-in" in said
    assert TOKEN not in "\n".join(said)


def test_a_program_that_is_not_on_path_is_missing_with_how_to_get_it(user):
    code, said = user.doctor(path=user.without("lavish-axi"))
    assert line_for(said, "lavish-axi") == [
        "missing optional lavish-axi -> npm install -g lavish-axi"
    ]


def test_with_no_gh_the_program_and_its_sign_in_are_both_missing(user):
    code, said = user.doctor(path=f"{user.without('gh')}:{user.bin}")
    assert line_for(said, "gh") == ["missing hard gh", "missing hard gh sign-in -> gh auth login"]
    assert code == 1


@pytest.mark.parametrize(
    ("name", "says", "line"),
    [
        ("git", "git version 2.30.2", "old hard git -> 2.30.2, needs 2.31 or newer"),
        ("jq", "jq-1.5", "old hard jq -> 1.5, needs 1.6 or newer"),
        ("jq", "jq-1.6", "ok hard jq -> 1.6"),
        ("git", "no number here", "old hard git -> its version could not be read"),
    ],
)
def test_a_program_under_its_floor_is_old(user, name, says, line):
    user.program(name, f"echo '{says}'")
    assert user.line(f"hard {name}") == line


def test_a_t3_code_that_does_not_answer_is_old(user):
    user.program("t3", "echo 'T3 Code has moved or been removed.' >&2; exit 127")
    assert user.line("hard t3") == "old hard t3 -> t3 --version did not answer: open the app once"


def test_t3_code_is_asked_through_the_command_it_writes_into_its_own_home(user):
    path = user.without("t3")
    assert line_for(user.doctor(path=path)[1], "hard t3") == [
        "missing hard t3 -> the nightly build (on Arch: t3code-nightly-bin)"
    ]
    written = user.home / ".t3" / "bin" / "t3"
    user.write(written, f"#!/bin/sh\necho 't3 v{NIGHTLY}'\n")
    written.chmod(0o755)
    assert line_for(user.doctor(path=path)[1], "hard t3") == [f"ok hard t3 -> {NIGHTLY}"]


def test_a_nightly_before_the_floor_is_old_once_a_floor_is_written_down(tmp_path):
    said = Ran(0, "t3 v0.0.46-nightly.20261010.2935\n")
    here = machine(REPO, tmp_path, tmp_path, run=lambda args: said)
    (tmp_path / ".t3" / "bin").mkdir(parents=True)
    (tmp_path / ".t3" / "bin" / "t3").write_text("")
    (tmp_path / ".t3" / "bin" / "t3").chmod(0o755)
    after = T3Nightly("0.0.46-nightly.20261011.1").probe(here)
    assert (after.state.value, after.detail) == (
        "old",
        "0.0.46-nightly.20261010.2935, needs 0.0.46-nightly.20261011.1 or newer",
    )
    assert T3Nightly("0.0.46-nightly.20261010.2935").probe(here).state.value == "ok"
    assert T3Nightly("0.0.45-nightly.20261201.1").probe(here).state.value == "ok"


def test_a_platform_that_is_not_linux_is_missing(tmp_path):
    here = machine(REPO, tmp_path, tmp_path)
    found = Linux("darwin").probe(here)
    assert (found.state.value, found.detail) == ("missing", "this is darwin")
    assert Linux("linux").probe(here).state.value == "ok"


def test_a_program_with_no_floor_is_not_run(tmp_path):
    ran = []
    (tmp_path / "claude").write_text("")
    (tmp_path / "claude").chmod(0o755)
    env = {"PATH": str(tmp_path)}
    here = Machine(REPO, tmp_path, env, lambda args: ran.append(args) or Ran(0, ""), tmp_path)
    assert Program("claude").probe(here).state.value == "ok"
    assert ran == []


def test_a_jbus_config_the_loader_takes_is_ok_and_one_others_can_read_is_old(user):
    part = f"jbus config {user.jbus / 'config.toml'}"
    user.private(user.jbus / "config.toml", JBUS)
    assert user.line("jbus config") == f"ok optional {part}"
    (user.jbus / "config.toml").chmod(0o644)
    assert user.line("jbus config") == (
        f"old optional {part}"
        f" -> {user.jbus / 'config.toml'} is mode 644, readable by others: chmod 600 it"
    )


@pytest.mark.parametrize(
    ("written", "why"),
    [
        ("", "lacks the key 'server'"),
        ("server = ", "does not parse: Invalid value"),
        (JBUS + '[[project]]\nname = "one"\n', "lacks the key 'checkout'"),
    ],
)
def test_a_jbus_config_the_loader_refuses_is_old_in_the_loaders_words(user, written, why):
    path = user.jbus / "config.toml"
    user.private(path, written)
    said = user.line("jbus config")
    assert said.startswith(f"old optional jbus config {path} -> {path} {why}")


@pytest.mark.parametrize(
    ("written", "raised"),
    [
        ("max_running = [1]\n", "TypeError"),
        ('max_running = "many"\n', "ValueError"),
        (
            '[[project]]\nname = "one"\ncheckout = "~nobody-by-this-name/x"\nprojectId = "1"\n',
            "RuntimeError",
        ),
    ],
)
def test_a_jbus_config_the_loader_cannot_read_is_old_and_the_doctor_goes_on(user, written, raised):
    path = user.jbus / "config.toml"
    user.private(path, JBUS + written)
    code, said = user.doctor()
    assert line_for(said, "jbus config") == [
        f"old optional jbus config {path} -> jbus cannot read it: {raised}"
    ]
    assert said[-1].startswith("doctor: ")


def test_a_jbus_sign_in_with_a_time_no_clock_has_is_old_and_the_doctor_goes_on(user):
    user.private(user.token, {"token": {"access_token": TOKEN}, "obtained_at": 1e300})
    code, said = user.doctor()
    assert line_for(said, "jbus sign-in") == [
        f"old optional jbus sign-in {user.token} -> jbus cannot read it: OverflowError"
    ]
    assert said[-1].startswith("doctor: ")
    assert TOKEN not in "\n".join(said)


def test_a_jbus_sign_in_is_ok_until_its_token_runs_out(user):
    part = f"optional jbus sign-in {user.token}"
    stored = {"token": {"access_token": TOKEN, "expires_in": 3600}, "obtained_at": time.time()}
    user.private(user.token, stored)
    assert user.line("jbus sign-in") == f"ok {part}"
    user.private(user.token, stored | {"obtained_at": 1789992000 - 3600})
    user.write(user.config, 'timezone = "Pacific/Kiritimati"\n')
    assert user.line("jbus sign-in") == f"old {part} -> expired 2026-09-22, run jbus t3 login"
    user.write(user.config, 'timezone = "UTC"\n')
    assert user.line("jbus sign-in") == f"old {part} -> expired 2026-09-21, run jbus t3 login"
    user.private(user.token, {})
    assert user.line("jbus sign-in") == f"old {part} -> holds no token, run jbus t3 login"
    user.private(user.token, stored)
    user.token.chmod(0o640)
    assert user.line("jbus sign-in") == (
        f"old {part} -> {user.token} is mode 640, readable by others: chmod 600 it"
    )
    assert TOKEN not in "\n".join(user.doctor()[1])


def test_a_limits_file_is_ok_while_one_reset_is_still_to_come(user):
    part = f"optional limits {user.limits}"
    soon = int(time.time()) + 3600
    user.write(user.limits, f"five_hour 12.5 {soon}\nseven_day 40 1790000000\n")
    assert user.line("limits") == f"ok {part}"
    user.write(user.limits, "five_hour 12.5 1790000000\nseven_day 40 1790000001\n")
    assert user.line("limits") == f"old {part} -> every reset in it is past, nothing writes it now"
    user.write(user.limits, "five_hour twelve soon\n")
    assert user.line("limits") == f"old {part} -> it gives no limit"


def test_a_jstack_config_the_loader_takes_is_ok_and_one_it_refuses_is_old(user):
    part = f"optional config {user.config}"
    user.write(user.config, 'user = "ada"\ntimezone = "Europe/London"\n')
    assert user.line("optional config") == f"ok {part}"
    user.write(user.config, 'name = "ada"\n')
    assert user.line("optional config") == (
        f"old {part} -> {user.config} has the key name, not one of user, timezone, timezone_label"
    )


def test_a_jstack_config_that_is_a_link_to_nothing_is_missing(user):
    user.config.parent.mkdir(parents=True)
    user.config.symlink_to(user.home / "nowhere.toml")
    assert user.line("optional config") == (
        f"missing optional config {user.config}"
        " -> defaults are used: user, timezone, timezone_label"
    )


def test_usage_names_the_doctor(user):
    code, said, err = user.run_with_stderr("--doctor", "--check")
    assert (code, said) == (2, [])
    assert err == "usage: install.sh [--check | --uninstall | --doctor | --setup]\n"
    assert user.listing() == []


def test_the_doctor_says_when_the_private_patterns_are_missing_and_when_they_are_there(user):
    assert user.line("patterns") == f"missing optional patterns {user.patterns}"
    user.run()
    assert user.line("patterns") == f"ok optional patterns {user.patterns}"
    user.patterns.unlink()
    code, said = user.doctor()
    assert (code, said[-1]) == (0, "doctor: ok")
    assert line_for(said, "patterns") == [f"missing optional patterns {user.patterns}"]


PRIME = "claudeAgent_claude_prime"
CODEX = {"driver": "codex", "enabled": True, "config": {"setupMode": "managed"}}
CURSOR = {"driver": "cursor", "displayName": "Cursor", "enabled": True}


def prime(home="~/.claude_prime", **more):
    return {"driver": "claudeAgent", "enabled": True, "config": {"homePath": home}} | more


def declared(user, listed, inventory=None):
    """An installed HOME whose inventory declares T3's two instances of today, the built-in
    Claude one and the second Claude home, and whose T3 settings list `listed`."""
    user.run()
    (user.home / ".claude_prime").mkdir()
    (user.home / ".claude_prime" / "skills").symlink_to(user.home / ".claude" / "skills")
    inventory = inventory or {
        "claudeAgent": {"driver": "claudeAgent", "enabled": True},
        PRIME: prime(),
        "codex": CODEX,
    }
    user.write(user.providers, inventory)
    user.write(user.t3_settings, {"providerInstances": listed, "other": 1})


def test_a_declared_instance_t3_does_not_list_is_missing_and_hard(user):
    declared(user, {"codex": CODEX, "cursor": CURSOR})
    code, said = user.doctor()
    assert (code, said[-1]) == (1, "doctor: not ok, 1 hard")
    assert line_for(said, "provider") == [
        "ok optional provider inventory -> 3 declared",
        "ok hard provider claudeAgent -> T3's built-in instance",
        f"missing hard provider {PRIME} -> T3 does not list it",
        "ok hard provider codex",
    ]


def test_a_declared_instance_t3_lists_with_its_home_is_ok(user):
    listed = {"codex": CODEX, "cursor": CURSOR, PRIME: prime(str(user.home / ".claude_prime"))}
    declared(user, listed)
    code, said = user.doctor()
    assert (code, said[-1]) == (0, "doctor: ok")
    assert f"ok hard provider {PRIME}" in said
    assert line_for(said, "skills") == [
        f"ok hard skills {user.home / '.claude'}",
        f"ok hard skills {user.home / '.claude_prime'}",
    ]


@pytest.mark.parametrize(
    ("listed", "why"),
    [
        (prime(enabled=False), "T3 lists it disabled"),
        (prime("~/.claude_other"), "T3's homePath is ~/.claude_other, declared ~/.claude_prime"),
        (
            {"driver": "codex", "enabled": True},
            "T3's driver is codex, declared claudeAgent",
        ),
    ],
)
def test_a_declared_instance_t3_lists_otherwise_is_old(user, listed, why):
    declared(user, {"codex": CODEX, PRIME: listed})
    code, said = user.doctor()
    assert code == 1
    assert line_for(said, f"provider {PRIME}") == [f"old hard provider {PRIME} -> {why}"]


def test_another_instance_t3_lists_in_a_shape_the_doctor_refuses_changes_no_line(user):
    declared(user, {"cursor": {"enabled": True}, "codex": CODEX})
    assert line_for(user.doctor()[1], "provider") == [
        "ok optional provider inventory -> 3 declared",
        "ok hard provider claudeAgent -> T3's built-in instance",
        f"missing hard provider {PRIME} -> T3 does not list it",
        "ok hard provider codex",
    ]


def test_t3_settings_that_cannot_be_read_make_each_declared_instance_old(user):
    declared(user, {})
    user.write(user.t3_settings, "{not json")
    said = user.doctor()[1]
    assert line_for(said, f"provider {PRIME}") == [
        f"old hard provider {PRIME} -> T3's settings cannot be read: {user.t3_settings}"
    ]


def test_an_inventory_that_is_not_an_object_of_instances_is_old_and_declares_nothing(user):
    user.write(user.providers, ["claudeAgent"])
    code, said = user.doctor()
    assert line_for(said, "provider") == [
        "old optional provider inventory -> it is not an object of provider instances"
    ]


def test_a_claude_home_whose_skills_point_outside_the_checkout_is_old(user, tmp_path):
    declared(user, {PRIME: prime()})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    skills = user.home / ".claude_prime" / "skills"
    skills.unlink()
    skills.symlink_to(elsewhere)
    code, said = user.doctor()
    assert code == 1
    assert line_for(said, "skills") == [
        f"ok hard skills {user.home / '.claude'}",
        f"old hard skills {user.home / '.claude_prime'} -> {elsewhere}",
    ]


def test_a_claude_home_whose_own_skill_links_reach_the_checkout_is_ok(user, tmp_path):
    declared(user, {PRIME: prime()})
    skills = user.home / ".claude_prime" / "skills"
    skills.unlink()
    skills.mkdir()
    (skills / "crew").symlink_to(REPO / "skills" / "crew")
    (skills / ".system").mkdir()
    assert line_for(user.doctor()[1], "skills") == [
        f"ok hard skills {user.home / '.claude'}",
        f"ok hard skills {user.home / '.claude_prime'}",
    ]
    mine = tmp_path / "mine"
    mine.mkdir()
    (skills / "mine").symlink_to(mine)
    assert line_for(user.doctor()[1], f"skills {user.home / '.claude_prime'}") == [
        f"old hard skills {user.home / '.claude_prime'} -> {skills / 'mine'} points at {mine}"
    ]


def test_a_claude_home_with_no_skills_is_missing(user):
    declared(user, {PRIME: prime()})
    (user.home / ".claude_prime" / "skills").unlink()
    assert line_for(user.doctor()[1], f"skills {user.home / '.claude_prime'}") == [
        f"missing hard skills {user.home / '.claude_prime'}"
        f" -> link it to {user.home / '.claude' / 'skills'}"
    ]
