"""Each feature declares its verbs of `jbus` beside its own code, and jbus builds the command from
those declarations.

`fixtures/jbus-help/` holds what `jbus --help` and each `jbus <verb> --help` printed before any
feature declared a verb outside `jbus.cli`, at 80 columns and with no colour. `jbus.txt` is `jbus
--help` with the verbs there were then, `verbs.FIRST`, so a verb added since does not change it.
`jbus-queue-add.txt` is `jbus queue add --help`. The tests run the real command and hold it to those
files, byte for byte.

`jbus` reads its verbs off the sources and imports only the module of the verb that runs. A test
holds what `jbus --help` and the `--help` of every verb, and of every verb under one, print to what
the parser prints when every verb takes its arguments, as when `jbus` imported every verb.
"""

import argparse
import contextlib
import importlib
import io
import pkgutil
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from jbus import cli, poll, t3, verbs
from test_jbus_kitchen import GATE

HELP = Path(__file__).parent / "fixtures" / "jbus-help"
READ_SET = ("features/jbus/tests/fixtures/jbus-help/",)
PAGES = sorted(path.stem for path in HELP.glob("*.txt"))


def unwrapped(text):
    """Return a help page with the `...` of a subcommand's usage beside its choices: Python 3.12's
    argparse puts it on a line of its own where the choices fill the line, and 3.13 does not."""
    return re.sub(r"\n +\.\.\.\n", " ...\n", text)


def helped(page, monkeypatch):
    """Return what `--help` prints for a page, with only the verbs of `verbs.FIRST`.
    `jbus-queue-add` is the page of `jbus queue add --help`."""
    monkeypatch.setattr(cli, "LISTED", {name: cli.LISTED[name] for name in verbs.FIRST})
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as stopped:
        cli.main([*page.split("-")[1:], "--help"])
    assert stopped.value.code == 0
    return unwrapped(out.getvalue())


@pytest.mark.parametrize("page", PAGES)
def test_help_prints_what_it_printed_before_the_verbs_moved(page, monkeypatch):
    assert helped(page, monkeypatch) == (HELP / f"{page}.txt").read_text()


def listed(page):
    """Return the verbs a help page lists, in its order."""
    return re.search(r"\{([a-z0-9,-]+)\}", page).group(1).split(",")


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
    """Run a fresh Python that imports jbus with `modules` beside its own, then runs `run`."""
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
    monkeypatch.setattr(verbs, "load_verb", lambda one: verb)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["status"]) == 1
    assert out.getvalue() == said


def test_the_pass_s_one_verb_is_in_poll_and_cli_runs_no_verb():
    assert [name for name, one in cli.LISTED.items() if one.module == poll.__name__] == ["poll"]
    assert not [one.name for one in cli.LISTED.values() if one.module == cli.__name__]
    assert not [name for name in vars(cli) if name.startswith("_") and name[1:] in cli.LISTED]


def walked(parser, typed):
    """Return what is typed for the help page of `parser` and of each verb under it."""
    found = [typed]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, under in action.choices.items():
                found += walked(under, [*typed, name])
    return found


def printed(parse, argv):
    """Return what `parse(argv)` prints before it exits 0."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as stopped:
        parse(argv)
    assert stopped.value.code == 0, argv
    return out.getvalue()


def test_every_help_prints_what_the_parser_of_every_verb_prints(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    every = [verbs.load_verb(one) for one in cli.LISTED.values()]
    eager = verbs.parser(cli.LISTED, cli.__doc__, every)
    pages = walked(eager, [])
    assert len(pages) > len(every)
    for typed in pages:
        assert printed(cli.main, [*typed, "--help"]) == printed(
            eager.parse_args, [*typed, "--help"]
        )


def loaded_by(argv):
    """Return the modules of jbus that a fresh Python has loaded once `cli.main(argv)` ends."""
    run = (
        "import contextlib, io, sys\nfrom jbus import cli\n"
        "with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):\n"
        f"    cli.main({argv!r})\n"
        "print(*sorted(name for name in sys.modules if name.startswith('jbus')))"
    )
    ran = subprocess.run([sys.executable, "-c", run], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    return set(ran.stdout.split())


def test_help_imports_the_module_of_no_verb_and_a_verb_s_help_imports_its_own():
    modules = {one.module for one in cli.LISTED.values()} - {cli.__name__, verbs.__name__}
    assert loaded_by(["--help"]) & modules == set()
    assert loaded_by(["--help"]) <= {"jbus", "jbus.cli", "jbus.party", "jbus.sources", "jbus.verbs"}
    assert "jbus.digest" in loaded_by(["status", "--help"])
    assert "jbus.poll" not in loaded_by(["status", "--help"])


def test_a_verb_that_runs_with_no_error_imports_no_t3(tmp_path):
    ran = loaded_by(["forget", str(tmp_path / "outside")])
    assert "jbus.forget" in ran
    assert "jbus.t3" not in ran


def test_what_the_sources_list_is_what_the_modules_declare_once_imported():
    imported = {
        verb.name: (verb.help, module.name)
        for module in pkgutil.iter_modules(jbus.__path__, "jbus.")
        if not module.name.endswith(".__main__")
        for verb in getattr(importlib.import_module(module.name), "VERBS", ())
    }
    assert {one.name: (one.help, one.module) for one in cli.LISTED.values()} == imported


@pytest.mark.parametrize(
    "written",
    [
        'HELP = "said"\nVERBS = (verbs.Verb("shout", HELP, verbs.nothing, print),)',
        'VERBS = (verbs.Verb("shout", "say" + " it", verbs.nothing, print),)',
        'VERBS = [verbs.Verb("shout", "say it", verbs.nothing, print)]',
        "VERBS = (*OTHER,)",
        "VERBS: tuple",
    ],
)
def test_a_verbs_whose_name_and_help_are_not_written_out_fails_at_import(tmp_path, written):
    ran = fresh(tmp_path, "import jbus.cli", odd="from jbus import verbs\n" + written + "\n")
    assert ran.returncode != 0
    assert ran.stderr.splitlines()[-1] == (
        "ValueError: jbus.odd: VERBS is not a tuple of Verb(<name>, <help>, ...) with the name "
        "and the help written out"
    ), ran.stderr


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
    """`SHORT` lists the pages whose parser took a short option before the verbs moved out of
    `jbus.cli`. It names no verb added since."""
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as stopped:
            cli.main([*page.split("-")[1:], "--he"])
    if page.removeprefix("jbus-") in SHORT:
        said = unwrapped(out.getvalue())
        assert (stopped.value.code, said) == (0, (HELP / f"{page}.txt").read_text())
    else:
        assert stopped.value.code == 2


def test_a_gate_from_a_repo_the_config_does_not_name_is_refused(kitchen, tmp_path):
    """Every repo has the same skills, so jbus refuses a gate that a crewmate sends from a repo
    the config does not name, and does not file it under this project."""
    other = tmp_path / "another-repo"
    kitchen.git("init", "-q", str(other), cwd=tmp_path)
    kitchen.monkeypatch.chdir(other)
    lines = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=lines) == (
        1,
        "not asked: refused: no project for this repo (another-repo)\n",
    )
    assert kitchen.events() == []
    assert kitchen.main("--project", "demo", "gate", "alpha", stdin=lines) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )


def test_the_words_python_3_12_3_hands_back_are_the_verbs_words():
    """argparse fills `words` with nothing when it reads the number, and hands the words back
    unparsed. A plain string left over is a word, and so is everything after `--`. An option left
    over is still not a word."""
    args = argparse.Namespace(words=[])
    assert verbs.words_left(args, ["fine", "--strange", "--", "-x", "y"]) == ["--strange"]
    assert args.words == ["fine", "-x", "y"]
    given = argparse.Namespace(words=["kept"])
    assert verbs.words_left(given, ["--strange"]) == ["--strange"]
    assert given.words == ["kept"]


class Terminal(io.StringIO):
    """A stdin that is a terminal: a read of it waits for a line nobody types."""

    def isatty(self):
        return True

    def read(self, *_):
        raise AssertionError("read a terminal, which waits until somebody types")


@pytest.mark.parametrize(
    ("argv", "what"),
    [
        (["queue", "add", "alpha", "--priority", "1"], "the brief"),
        (["done", "alpha"], "the result's lines"),
        (["gate", "alpha"], "the gate's lines"),
        (["queue", "apply"], "the verbs"),
    ],
    ids=["queue-add", "done", "gate", "queue-apply"],
)
def test_a_verb_that_reads_stdin_refuses_a_terminal_at_once(kitchen, argv, what):
    """A thread has no one to type at its terminal, so a verb that reads its text from stdin
    refuses a terminal before it reads, and names what to pipe in."""
    verb = " ".join(one for one in argv if not one.startswith("-") and not one.isdigit())
    verb, given = verb.removesuffix(" alpha"), " <slug>" if "alpha" in argv else ""
    lead = "not asked: " if verb == "gate" else ""
    assert kitchen.main("--project", "demo", *argv, stdin=Terminal()) == (
        1,
        f"{lead}refused: stdin is a terminal, and jbus {verb} reads {what} from it: pipe them in, "
        f"as in jbus {verb}{given} < <file>\n",
    )
    assert kitchen.events() == []


OFF = "2026-10-12 08:00 ET"
CLOCK = "the clock reads 2026-10-12 11:00 ET"


@pytest.mark.parametrize(
    ("argv", "kept"),
    [
        (
            ["--project", "demo", "answer", "1", "--by", "user", "--at", OFF, "--default", "yes"],
            "acts.jsonl",
        ),
    ],
    ids=["answer"],
)
def test_a_typed_at_far_off_the_clock_is_refused_and_nothing_is_kept(kitchen, argv, kept):
    """A time an agent types is when the user said it, which it reads from `date` or the
    message. One hours off the clock is a guess: jbus refuses it and keeps no record of it."""
    lines = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert kitchen.main("--project", "demo", "gate", "alpha", stdin=lines)[0] == 0
    assert kitchen.main(*argv) == (
        1,
        f"refused: --at {OFF} is 180 minutes off the clock, and {CLOCK}: take the time from "
        "date or from the message's own timestamp, never a guess\n",
    )
    assert not (kitchen.state / kept).exists()


@pytest.mark.parametrize(
    ("clock", "taken", "refused"),
    [
        (datetime(2026, 11, 1, 5, 30, tzinfo=UTC), "EDT", "EST"),
        (datetime(2026, 11, 1, 6, 30, tzinfo=UTC), "EST", "EDT"),
    ],
    ids=["first-01:30", "second-01:30"],
)
def test_the_hour_that_occurs_twice_is_read_by_its_zone_word(monkeypatch, clock, taken, refused):
    """When the clocks go back, 01:30 occurs twice, an hour apart. A typed `--at` names which
    one by its zone word, and is held to the clock as that one."""
    user = jsettings.Settings(zone=ZoneInfo("America/New_York"))
    monkeypatch.setattr(verbs, "clock", lambda: clock)
    verbs.typed_at(user, f"2026-11-01 01:30 {taken}")
    with pytest.raises(jbus.Refused) as off:
        verbs.typed_at(user, f"2026-11-01 01:30 {refused}")
    assert str(off.value).startswith(f"refused: --at 2026-11-01 01:30 {refused} is 60 minutes off")
