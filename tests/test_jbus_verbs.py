"""Each verb of `jbus` is declared beside its feature, and the command is built from them.

`fixtures/jbus-help/` holds what `jbus --help` and each `jbus <verb> --help` printed before
a verb was declared anywhere but in `jbus.cli`, at 80 columns and with no colour: `jbus.txt`
is `jbus --help` with the verbs there were then, `verbs.FIRST`, so a verb added since does not
change it and `jbus-queue-add.txt` is `jbus queue add --help`. The tests run the real
command and hold it to those files, byte for byte.
"""

import argparse
import contextlib
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

import jbus
from jbus import cli, t3, verbs
from test_jbus_kitchen import GATE

HELP = Path(__file__).parent / "fixtures" / "jbus-help"
PAGES = sorted(path.stem for path in HELP.glob("*.txt"))


def helped(page, monkeypatch):
    """What `--help` prints for a page, `jbus-queue-add` being `jbus queue add --help`, with
    the verbs of `verbs.FIRST` alone."""
    monkeypatch.setattr(cli, "DECLARED", {name: cli.DECLARED[name] for name in verbs.FIRST})
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as stopped:
        cli.main([*page.split("-")[1:], "--help"])
    assert stopped.value.code == 0
    return out.getvalue()


@pytest.mark.parametrize("page", PAGES)
def test_help_prints_what_it_printed_before_the_verbs_moved(page, monkeypatch):
    assert helped(page, monkeypatch) == (HELP / f"{page}.txt").read_text()


def listed(page):
    """The verbs a help page lists, in its order."""
    return re.search(r"\{([a-z0-9,]+)\}", page).group(1).split(",")


def test_the_verbs_there_were_are_listed_first_and_each_has_its_help_kept(monkeypatch):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        cli.main(["--help"])
    assert listed(out.getvalue())[: len(verbs.FIRST)] == list(verbs.FIRST)
    named = [f"jbus-{verb}" for verb in verbs.FIRST]
    under = [
        f"jbus-{verb}-{each}"
        for verb in ("queue", "project")
        for each in listed(helped(f"jbus-{verb}", monkeypatch))
    ]
    assert sorted(["jbus", *named, *under]) == PAGES


def fresh(tmp_path, run, **modules):
    """A fresh Python that imports jbus with `modules` beside its own, then runs `run`."""
    for name, source in modules.items():
        (tmp_path / f"{name}.py").write_text(source)
    code = f"import jbus\njbus.__path__.append({str(tmp_path)!r})\n{run}\n"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


SHOUT = """
from jbus import verbs

def _loud(parser):
    parser.add_argument("--loud", action="store_true")

def _shout(args, config):
    print(f"shouted at {config.server}, loud: {args.loud}")
    return 3

VERBS = (verbs.Verb("shout", "say it louder", _loud, _shout),)
"""


def test_a_new_module_s_verb_runs_with_no_line_in_cli(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text('server = "http://127.0.0.1:1/"\n')
    (config / "config.toml").chmod(0o600)
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(config))
    run = "from jbus import cli\nraise SystemExit(cli.main(['shout', '--loud']))"
    (tmp_path / "jbus").mkdir()
    ran = fresh(tmp_path / "jbus", run, shout=SHOUT)
    assert (ran.returncode, ran.stdout) == (3, "shouted at http://127.0.0.1:1, loud: True\n")
    helped = fresh(tmp_path / "jbus", "from jbus import cli\ncli.main(['--help'])")
    choices = listed(helped.stdout)
    assert choices.index("shout") > choices.index(verbs.FIRST[-1])
    assert "    shout               say it louder\n" in helped.stdout


def test_a_verb_two_modules_declare_fails_at_import_and_names_both(tmp_path):
    second = (
        'from jbus import verbs\nVERBS = (verbs.Verb("status", "again", verbs.nothing, print),)\n'
    )
    ran = fresh(tmp_path, "import jbus.cli", again=second)
    assert ran.returncode != 0
    last = ran.stderr.splitlines()[-1]
    assert last == "ValueError: status is declared in jbus.digest and in jbus.again", ran.stderr


@pytest.mark.parametrize(
    ("error", "said"),
    [
        (jbus.Refused("refused: not today"), "refused: not today\n"),
        (t3.T3Error("the server said no"), "the server said no\n"),
    ],
)
def test_a_refusal_or_a_t3_error_is_printed_and_the_answer_is_1(error, said, monkeypatch):
    def refuses(args, config):
        raise error

    verb = verbs.Verb("status", "", verbs.nothing, refuses, config=False)
    monkeypatch.setitem(cli.DECLARED, "status", verb)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["status"]) == 1
    assert out.getvalue() == said


def test_cli_runs_the_pass_s_one_verb_and_no_feature_s():
    mine = [name for name, verb in cli.DECLARED.items() if verb.run.__module__ == cli.__name__]
    assert mine == ["poll"]
    assert not [name for name in vars(cli) if name.startswith("_") and name[1:] in cli.DECLARED]


SHORT = {
    "poll",
    "alarm",
    "status",
    "queue",
    "plan",
    "project",
    "gate",
    "done",
    "t3",
    "queue-hold",
    "queue-apply",
}


@pytest.mark.parametrize("page", [page for page in PAGES if page != "jbus"])
def test_an_option_typed_short_is_taken_where_it_was_before_the_verbs_moved(page, monkeypatch):
    """`SHORT` is the pages whose parser took a short option before the verbs moved. It names
    no verb added since."""
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as stopped:
            cli.main([*page.split("-")[1:], "--he"])
    if page.removeprefix("jbus-") in SHORT:
        assert (stopped.value.code, out.getvalue()) == (0, (HELP / f"{page}.txt").read_text())
    else:
        assert stopped.value.code == 2


def test_a_gate_from_a_repo_the_config_does_not_name_is_refused(kitchen, tmp_path):
    """The skills are every repo's: a crewmate elsewhere does not speak as this project."""
    other = tmp_path / "another-repo"
    kitchen.git("init", "-q", str(other), cwd=tmp_path)
    kitchen.monkeypatch.chdir(other)
    lines = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=lines) == (
        1,
        "refused: no project for this repo (another-repo)\n",
    )
    assert kitchen.events() == []
    assert kitchen.main("--project", "demo", "gate", "alpha", stdin=lines) == (
        0,
        "queued: question 1\n",
    )


def test_the_words_python_3_12_3_hands_back_are_the_verbs_words():
    """That argparse fills `words` with nothing when it reads the number, and hands the words
    back unparsed: a plain string left over is a word, and so is all after `--`. An option
    left over is still not one."""
    args = argparse.Namespace(words=[])
    assert verbs.words_left(args, ["fine", "--strange", "--", "-x", "y"]) == ["--strange"]
    assert args.words == ["fine", "-x", "y"]
    given = argparse.Namespace(words=["kept"])
    assert verbs.words_left(given, ["--strange"]) == ["--strange"]
    assert given.words == ["kept"]
