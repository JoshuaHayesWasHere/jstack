"""`jstack <name> ...` runs what `j<name> ...` runs: the same function, the same help, and no other
feature's module imported. Each case runs the console scripts the project's environment has."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from jstack import cli
from jstack.table import COMMANDS
from testing.paths import REPO

BIN = Path(sys.executable).parent
SCRIPTS = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"]


def run(*argv):
    return subprocess.run([BIN / argv[0], *argv[1:]], capture_output=True, text=True)


def test_the_table_has_every_other_command_and_runs_the_function_its_script_runs():
    assert {command: target for command, target in COMMANDS.values()} == {
        name: target for name, target in SCRIPTS.items() if name != "jstack"
    }
    assert SCRIPTS["jstack"] == "jstack.cli:main"


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_jstack_name_help_is_the_command_s_own_help(name):
    command, _ = COMMANDS[name]
    own, through = run(command, "--help"), run("jstack", name, "--help")
    assert (through.returncode, through.stdout, through.stderr) == (
        own.returncode,
        own.stdout,
        own.stderr,
    )
    assert own.stdout.startswith(f"usage: {command}")


def test_a_command_s_exit_code_and_refusal_are_its_own():
    own, through = run("jleak", "--no-such-flag"), run("jstack", "leak", "--no-such-flag")
    assert own.returncode == 2
    assert (through.returncode, through.stderr) == (own.returncode, own.stderr)


def test_jstack_imports_only_the_feature_of_the_name_typed():
    names = sorted({target.split(".")[0] for _, target in COMMANDS.values()})
    code = (
        "import sys\n"
        "from jstack import cli\n"
        "try:\n"
        "    cli.main(['leak', '--help'])\n"
        "except SystemExit:\n"
        "    pass\n"
        f"print(sorted({{m.split('.')[0] for m in sys.modules}} & set({names!r})))\n"
    )
    ran = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert ran.stdout.splitlines()[-1] == "['jleak']"


def test_help_names_every_command(capsys):
    assert cli.main(["--help"]) == 0
    shown = capsys.readouterr().out
    assert shown.startswith("usage: jstack <name>")
    for name, (command, _) in COMMANDS.items():
        assert f"  {name} " in shown and f"runs {command}\n" in shown


@pytest.mark.parametrize("argv", [[], ["nope"], ["jleak"]])
def test_no_name_or_a_name_the_table_lacks_exits_2_with_the_usage(argv, capsys):
    assert cli.main(argv) == 2
    said = capsys.readouterr().err
    assert "usage: jstack <name>" in said
    assert ("no command" in said) == bool(argv)
    assert all(f"no command {name!r}" in said for name in argv)
