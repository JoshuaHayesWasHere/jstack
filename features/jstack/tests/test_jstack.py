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
    with pytest.raises(SystemExit) as ended:
        cli.main(["--help"])
    assert ended.value.code == 0
    shown = capsys.readouterr().out
    assert shown.startswith("usage: jstack [-h] {")
    assert "{" + ",".join(COMMANDS) + "}" in shown


@pytest.mark.parametrize("argv", [[], ["nope"], ["jleak"], ["--nope"]])
def test_no_name_or_a_name_the_table_lacks_exits_2_with_the_usage(argv, capsys):
    with pytest.raises(SystemExit) as ended:
        cli.main(argv)
    assert ended.value.code == 2
    assert capsys.readouterr().err.startswith("usage: jstack [-h] {")


def test_the_command_runs_with_its_own_argv_and_jstack_s_is_put_back(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["jstack", "leak", "--trailers"])
    seen = []
    monkeypatch.setattr("jleak.cli.main", lambda argv: seen.append((list(sys.argv), argv)) or 7)
    assert cli.main() == 7
    assert seen == [(["jleak", "--trailers"], ["--trailers"])]
    assert sys.argv == ["jstack", "leak", "--trailers"]
