"""Every repo with a home is a jbus project. A home's start adds its repo with new-home's step 3,
the one block that adds a repo. That block never writes `home-thread`, so jbus merges for every
project. On each pass, `jbus status` and the view's machine row name a home whose repo is no jbus
project.

The tests run the skill's blocks as the home skill says, in one call with the block at the top, the
block that finds this home and the block that reads jbus. They run on a made-up home directory, with
`jbus` on PATH as the real command over a made-up config.
"""

import json
import os
import subprocess
import sys
import tomllib
from datetime import timedelta

import pytest

from skill_blocks import block, git
from test_jbus_kitchen import NOW
from testing.layouts import assembled

PROJECT, THREAD = "p-winnie", "mcp:the-home"
CONFIG = (
    'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "first"\n'
    'checkout = "/somewhere/first"\nprojectId = "p-first"\n'
)
OFF = "homes not on the bus"


class Machine:
    """A home directory with the skills, `~/repos/Winnie` and its started home, jbus's config
    for another project, and a `jbus` that notes what `home-thread` held when a block asked it to
    add a project."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.repo = self.home / "repos" / "Winnie"
        self.state = self.home / ".local/state/home/Winnie"
        self.switch = self.state / "home-thread"
        self.config = self.home / ".config/jbus/config.toml"
        self.seen = tmp_path / "switch-at-add"
        self.bin = tmp_path / "bin"
        for made in (self.repo, self.state, self.config.parent, self.bin, self.home / ".claude"):
            made.mkdir(parents=True)
        (self.home / ".claude" / "skills").symlink_to(assembled() / "skills")
        git(self.repo, "init", "-q", "-b", "wip")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        for name, text in (("plan.md", ""), ("home-id", f"{THREAD}\n")):
            (self.state / name).write_text(text)
        self.config.write_text(CONFIG)
        self.config.chmod(0o600)
        jbus = self.bin / "jbus"
        jbus.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = project ]; then cat {self.switch} > {self.seen} 2> /dev/null '
            f"|| echo none > {self.seen}; fi\n"
            f'exec {sys.executable} -m jbus "$@"\n'
        )
        jbus.chmod(0o755)
        jinstall = self.bin / "jinstall"
        jinstall.write_text(f'#!/bin/sh\nexec {sys.executable} -m jinstall.cli "$@"\n')
        jinstall.chmod(0o755)

    def sh(self, body):
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "JBUS_CONFIG_DIR": str(self.config.parent),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        done = subprocess.run(
            ["sh", "-c", body], cwd=self.repo, env=env, capture_output=True, text=True
        )
        assert (done.returncode, done.stderr) == (0, "")
        return done.stdout.splitlines()

    def start(self):
        """What "On the bus" prints at this home's start."""
        found = block("home", 'echo "no home:').replace("<threadId>", THREAD)
        reads = block("home", "SEP=$(printf")
        top = block("home", "R=$(basename")
        return self.sh("\n".join((top, found, reads, block("home", "on the bus:"))))

    def add(self):
        """New-home's step 3, as the home's start fills it in."""
        body = block("new-home", "jbus project add")
        filled = {"<the checkout>": str(self.repo), "<the T3 project id>": PROJECT}
        for placeholder, value in filled.items():
            assert placeholder in body
            body = body.replace(placeholder, value)
        return self.sh(body)

    def tables(self):
        return [one["name"] for one in tomllib.loads(self.config.read_text())["project"]]


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


def hooks(machine):
    return f"3 git hooks: done, 2 ok in {machine.repo}/.git/hooks"


NO_SIGN_IN = (
    "3 jbus sign-in: needs you: jbus t3 login, every go is your word and jbus reads it from T3 Code"
)


def added(machine):
    (backup,) = machine.config.parent.glob("config.toml.*.bak")
    return (
        f"3 jbus project: done, one [[project]] table, the file as it was is {backup}: "
        "the next pass works it, restart no unit"
    )


def test_a_home_whose_repo_jbus_lacks_adds_it_and_leaves_the_merge_to_jbus(machine):
    step3 = assembled().resolve() / "templates" / ".." / "skills" / "new-home" / "SKILL.md"
    assert step3.is_file()
    assert machine.start() == [
        "not on the bus: Winnie has no project in jbus's config: add it with the block of "
        f"step 3 of {step3}, checkout {machine.repo}"
    ]
    assert machine.add() == [added(machine), NO_SIGN_IN, hooks(machine)]
    assert machine.tables() == ["first", "Winnie"]
    assert machine.seen.read_text() == "none\n"
    assert not machine.switch.exists()
    assert machine.start() == ["on the bus: Winnie is jbus project Winnie"]


def test_a_home_whose_repo_jbus_has_is_left_as_it_is(machine):
    machine.add()
    now = machine.config.read_text()
    assert machine.start() == ["on the bus: Winnie is jbus project Winnie"]
    assert machine.add() == [
        "3 jbus project: already, jbus's config has its table",
        NO_SIGN_IN,
        hooks(machine),
    ]
    assert machine.config.read_text() == now
    assert len(list(machine.config.parent.glob("config.toml.*.bak"))) == 1


def test_registration_writes_no_switch_whatever_the_homes_rules_say(machine):
    (machine.state / "standing.md").write_text(
        "1. This repo's home merges its own pull requests, by itself.\n"
    )
    assert machine.start()[0].startswith("not on the bus: Winnie has no project")
    assert machine.add() == [added(machine), NO_SIGN_IN, hooks(machine)]
    assert machine.seen.read_text() == "none\n", "no switch was on when jbus was asked"
    assert not machine.switch.exists()


def homes(kitchen):
    """The homes' state root with two homes off the bus, a party, an expert, a folder with no
    home, one whose home handed off, and a link to the project's home under an old name."""
    root = kitchen.home.parent
    for name in ("firstmate", "LittleRamPantries", "_party", "_poteto"):
        (root / name).mkdir()
        (root / name / "home-id").write_text(f"mcp:{name}\n")
    (root / "_poteto" / "CHARTER.md").write_text("an expert\n")
    (root / "FAFU").mkdir()
    (root / "handed").mkdir()
    (root / "handed" / "home-id").write_text("\n")
    (kitchen.home / "home-id").write_text("mcp:demo\n")
    (root / "attic").symlink_to(kitchen.home)
    (root / "README.md").write_text("not a home\n")
    return root


def test_a_pass_names_each_home_with_no_project_once_and_again_when_it_changes(kitchen):
    root = homes(kitchen)
    assert f"{OFF}: firstmate, LittleRamPantries" in kitchen.poll()
    assert kitchen.status()["homes_off_bus"] == ["firstmate", "LittleRamPantries"]
    assert not [line for line in kitchen.poll(NOW + timedelta(minutes=1)) if OFF in line]
    (root / "firstmate" / "home-id").unlink()
    assert f"{OFF}: LittleRamPantries" in kitchen.poll(NOW + timedelta(minutes=2))
    (root / "LittleRamPantries" / "home-id").write_text("")
    assert f"{OFF}: none" in kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.status()["homes_off_bus"] == []


def test_jbus_status_names_the_homes_off_the_bus_as_they_are_now(kitchen):
    root = homes(kitchen)
    kitchen.poll()
    (root / "Winnifred").mkdir()
    (root / "Winnifred" / "home-id").write_text("mcp:winnifred\n")
    code, said = kitchen.main("status")
    assert (code, json.loads(said)["homes_off_bus"]) == (
        0,
        ["firstmate", "LittleRamPantries", "Winnifred"],
    )
    assert kitchen.status()["homes_off_bus"] == ["firstmate", "LittleRamPantries"]
