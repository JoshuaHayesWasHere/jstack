"""Each command's page under `docs/` says what its `--help` says today, and nothing more.

The commands are the ones `pyproject.toml` lists. Each is asked for its `--help`, and so is
each verb the help names, down to the last one: that is the tree the pages are held to.

A page has a verb when it names the verb's command in full, as `jbus queue add`. It has a flag
of a verb, or a choice such as `login` of `jbus t3`, when one line names both the verb's
command and the flag. A flag of the command itself is looked for anywhere on the page, since
the page is about that one command.

The other way round, the code in the README and in every page is read as a shell would read
it: after a command's name, a word where a verb goes must be a verb, and a `--flag` must be a
flag of the verb it follows, in brackets or not. A name counts as a command where a shell
would run it: first in
its code, after `|`, `&&`, `;` or `--`, after the word `run`, or in a line that starts with
`uv`. So a line of output that names a command is not read as one. On a command's own page a
code span that starts with a `--flag` must be a flag of that command, so a page writes another
tool's flag behind that tool's name, as `git push --no-verify`.

The README's count of skills is held to the tree, and so is each count of commands that
the README or a page gives.
"""

import contextlib
import importlib
import io
import re
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from test_prose_lines import unwrapped

REPO = Path(__file__).parent.parent
README = REPO / "README.md"
DOCS = REPO / "docs"
PAGES = (README, *sorted(DOCS.glob("*.md")))
SCRIPTS = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"]
WIDTH = "200"
ENDS = ("|", "||", "&&", ";", "--", ">", ">>", "<", "<<")
STARTS = (*ENDS, "run")
NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


@dataclass(frozen=True)
class Node:
    """One command or verb, as its `--help` gives it."""

    path: tuple[str, ...]
    flags: dict[str, bool] = field(default_factory=dict)
    verbs: dict[str, "Node"] = field(default_factory=dict)
    choices: tuple[str, ...] = ()

    @property
    def command(self):
        return " ".join(self.path)

    def walk(self):
        yield self
        for verb in self.verbs.values():
            yield from verb.walk()


def help_of(path):
    """What `<command> <verbs> --help` prints, from the entry point `pyproject.toml` names."""
    module, _, name = SCRIPTS[path[0]].partition(":")
    main = getattr(importlib.import_module(module), name)
    out = io.StringIO()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("COLUMNS", WIDTH)
        patch.setenv("NO_COLOR", "1")
        with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as ended:
            main([*path[1:], "--help"])
    assert ended.value.code == 0, f"{' '.join(path)} --help exits {ended.value.code}"
    return out.getvalue()


def said_by(text):
    """The command a help text is of, its flags, and the words where a verb may go."""
    usage = text.split("\n\n")[0].removeprefix("usage:").split()
    command = []
    for word in usage:
        if word[0] in "[({-":
            break
        command.append(word)
    part, flags, words = "", {}, []
    for line in text.splitlines():
        if line and not line.startswith(" "):
            part = line.rstrip(":")
        elif part == "options":
            found = re.match(r"  (?:-\w(?: \S+)?, )?(--[\w-]+)(?: (\S+))?(?:  |$)", line)
            assert found or not line.startswith("  -"), f"an option line is not read: {line}"
            if found and found[1] != "--help":
                flags[found[1]] = found[2] is not None
        elif part == "positional arguments":
            listed = re.match(r"  \{([^}]+)\}", line)
            named = re.match(r"    ([\w-]+)(?:\s|$)", line)
            if listed:
                words += listed[1].split(",")
            elif named:
                words.append(named[1])
    return tuple(command), flags, tuple(dict.fromkeys(words))


def node(path):
    """A command or a verb, with every verb under it: a word is a verb when it has a help."""
    path = tuple(path)
    _, flags, words = said_by(help_of(path))
    verbs, choices = {}, []
    for word in words:
        under, _, _ = said_by(help_of((*path, word)))
        if under == (*path, word):
            verbs[word] = node(under)
        else:
            choices.append(word)
    return Node(path, flags, verbs, tuple(choices))


def has(text, word):
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def missing(tree, page):
    """What the help of a command has and its page does not, one line each."""
    lacks = []
    for at in tree.walk():
        if at is not tree and not has(page, at.command):
            lacks.append(f"{at.command}: the verb")
        beside = unwrapped(page) if at is not tree else [page]
        named = [line for line in beside if has(line, at.command)]
        for word in (*at.flags, *at.choices):
            if not any(has(line, word) for line in named):
                lacks.append(f"{at.command}: {word}")
    return lacks


def code(text):
    """Each piece of code a page shows: a line of a fenced block, or one inline span."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        elif fenced:
            found.append(line.strip())
        else:
            found += re.findall(r"`([^`\n]+)`", line)
    return found


def words_of(piece):
    try:
        return shlex.split(piece)
    except ValueError:
        return piece.split()


def is_word(word):
    return re.fullmatch(r"[a-z][a-z0-9-]*", word) is not None


def gone(trees, text, own=None):
    """What a text's code says of a command that the command's help does not have."""
    found = []
    for piece in code(text):
        words = words_of(piece)
        if own and words and words[0].startswith("--"):
            flag = words[0].partition("=")[0]
            if re.fullmatch(r"--[a-z][\w-]*", flag) and not any(
                flag in at.flags for at in trees[own].walk()
            ):
                found.append(f"{own}: {flag}, in `{piece}`")
        for start, word in enumerate(words):
            if word in trees and (start == 0 or words[start - 1] in STARTS or words[0] == "uv"):
                after = strays(trees[word], words[start + 1 :])
                found += [f"{line}, in `{piece}`" for line in after]
    return found


def strays(at, words):
    """The verbs and flags in the words after a command's name that its help does not have."""
    found, skip, placed = [], False, False
    for word in filter(None, (word.strip("[]") for word in words)):
        if skip:
            skip = False
        elif word in ENDS or word in SCRIPTS:
            break
        elif word.startswith("--"):
            flag = word.partition("=")[0]
            if flag not in at.flags:
                found.append(f"{at.command}: {flag}")
            else:
                skip = at.flags[flag] and "=" not in word
        elif at.verbs and not placed:
            names = word.split("|")
            if not all(map(is_word, names)):
                break
            bad = [name for name in names if name not in at.verbs]
            if bad or len(names) > 1:
                found += [f"{at.command}: the verb {name}" for name in bad]
                break
            at = at.verbs[word]
        elif at.choices and not placed:
            placed = True
            names = word.split("|")
            if all(map(is_word, names)):
                found += [f"{at.command}: {name}" for name in names if name not in at.choices]
        else:
            placed = True
    return found


@pytest.fixture(scope="module")
def trees():
    return {command: node([command]) for command in SCRIPTS}


def test_the_walk_of_each_help_finds_the_verbs_under_verbs_and_which_flags_take_a_value(trees):
    assert sorted(trees) == ["jbriefs", "jbus", "jdrift", "jgauge", "jleak", "jmerge", "jroles"]
    bus = trees["jbus"]
    assert bus.flags == {"--project": True}
    assert "poll" in bus.verbs and "view" in bus.verbs
    assert sorted(bus.verbs["queue"].verbs) == [
        "add",
        "apply",
        "approve",
        "hold",
        "remove",
        "show",
        "verify",
    ]
    assert bus.verbs["queue"].verbs["add"].flags == {
        "--priority": True,
        "--depends": True,
        "--merge-after": True,
        "--entry": True,
        "--item": True,
    }
    assert bus.verbs["plan"].flags == {"--scope": True} and bus.verbs["plan"].choices == ("close",)
    assert bus.verbs["t3"].choices == ("login", "launch-test") and bus.verbs["t3"].verbs == {}
    assert sorted(trees["jgauge"].verbs) == ["context", "room", "sample", "session", "test-slot"]
    assert trees["jmerge"].flags["--check"] is False and trees["jmerge"].flags["--accept"] is True
    assert trees["jroles"].verbs == {} and "crew" in trees["jroles"].choices
    assert sum(len(at.verbs) for tree in trees.values() for at in tree.walk()) > 20
    assert sum(len(at.flags) for tree in trees.values() for at in tree.walk()) > 30


@pytest.mark.parametrize("line", ("  -x", "  --files A B  two of them", "  -q, --quiet, --hush"))
def test_an_option_line_the_walk_cannot_read_fails_and_is_not_passed_over(line):
    told = f"usage: demo [-h]\n\noptions:\n  -h, --help  show this help\n{line}\n"
    with pytest.raises(AssertionError, match="an option line is not read"):
        said_by(told)
    wrapped = told.replace(line, "  --wide WIDTH\n          what it is")
    assert said_by(wrapped)[1] == {"--wide": True}


@pytest.mark.parametrize("command", SCRIPTS)
def test_a_commands_page_has_every_verb_and_every_flag_its_help_has(trees, command):
    assert missing(trees[command], (DOCS / f"{command}.md").read_text()) == []


def test_a_page_that_lacks_a_verb_a_flag_or_a_choice_is_found(trees):
    page = (DOCS / "jbus.md").read_text()
    assert missing(trees["jbus"], page.replace("jbus digest", "jbus summary")) == [
        "jbus digest: the verb",
        "jbus digest: --json",
        "jbus digest: --since",
    ]
    assert missing(trees["jbus"], page.replace("--sha", "--sum")) == ["jbus queue approve: --sha"]
    assert missing(trees["jbus"], page.replace("launch-test", "launch")) == ["jbus t3: launch-test"]
    assert missing(trees["jbus"], page.replace("--project", "--repo")) == [
        "jbus: --project",
        "jbus project add: --project-id",
    ]
    assert missing(trees["jmerge"], "# jmerge\n\n`jmerge --check`\n")[:2] == [
        "jmerge: --sweep",
        "jmerge: --claims",
    ]
    apart = "`jbus queue hold <slug>` and, lines later,\n`--by <who>`"
    assert "jbus queue remove: --by" in missing(trees["jbus"], apart)


@pytest.mark.parametrize("path", PAGES, ids=lambda path: path.name)
def test_a_page_names_no_verb_and_no_flag_that_the_help_does_not_have(trees, path):
    own = path.stem if path.stem in SCRIPTS else None
    assert gone(trees, path.read_text(), own) == []


def test_a_verb_or_a_flag_that_is_gone_is_found_in_a_span_and_in_a_block(trees):
    assert gone(trees, "Run `jgauge run -- make check` first.") == [
        "jgauge: the verb run, in `jgauge run -- make check`"
    ]
    assert gone(trees, "```sh\nuv run jbus --project demo queue drop a-slug\n```\n") == [
        "jbus queue: the verb drop, in `uv run jbus --project demo queue drop a-slug`"
    ]
    assert gone(trees, "`jbus queue show|add|drop`") == [
        "jbus queue: the verb drop, in `jbus queue show|add|drop`"
    ]
    assert gone(trees, "`jmerge --check --dry-run`") == [
        "jmerge: --dry-run, in `jmerge --check --dry-run`"
    ]
    assert gone(trees, "`jbus queue add a-slug --by me`") == [
        "jbus queue add: --by, in `jbus queue add a-slug --by me`"
    ]
    assert gone(trees, "`jbus t3 logout`") == ["jbus t3: logout, in `jbus t3 logout`"]
    assert gone(trees, "`jbus view [--port <port>] [--bind <address>]`") == [
        "jbus view: --bind, in `jbus view [--port <port>] [--bind <address>]`"
    ]
    assert gone(trees, "`--land-all` lands them.", own="jmerge") == [
        "jmerge: --land-all, in `--land-all`"
    ]


def test_what_the_help_has_and_what_is_no_code_of_a_command_is_let_through(trees):
    told = "\n".join(
        (
            "`jbus --project demo answer 3 --by Alex --at '2026-01-02 10:00 ET' --default yes`",
            "`jbus queue show|add|approve|hold|remove|apply` and `jbus queue <verb>`",
            "`jgauge test-slot --slots 2 -- make check --here`",
            "`uv run jgauge room --wait 5 || jbus status`",
            "jbus makes no judgment call, and `jbus.timer` runs `jbus poll`.",
            "`git push --no-verify` and `gh pr create --body-file <file>`",
            "`jroles <role>`, `jroles crew`, `jleak --as title -`",
        )
    )
    assert gone(trees, told) == []
    assert gone(trees, "`--force-with-lease` is git's.") == []
    assert gone(trees, "`--sweep`, `--accept <n>`", own="jmerge") == []


def counts(text, noun):
    """Each number a text gives before a noun, in digits or as a word up to ten."""
    found = re.findall(rf"\b(\d+|{'|'.join(NUMBERS)}) {noun}\b", text, re.I)
    return [int(word) if word.isdigit() else NUMBERS.index(word.lower()) for word in found]


def test_the_readme_counts_the_skills_and_the_commands_as_the_tree_has_them():
    said = README.read_text()
    skills = [path for path in (REPO / "skills").iterdir() if (path / "SKILL.md").is_file()]
    listed = re.findall(r"^\| `([\w-]+)` \| `/", said, re.M)
    assert len(skills) > 20 and set(listed) < {path.name for path in skills}
    assert counts(said, "skills") == [len(skills), len(listed)]
    assert counts(said, "skills run the flow") == [len(listed)]
    assert counts(said, "are loaded by name") == [len(skills) - len(listed)]
    told = "\n".join(path.read_text() for path in PAGES)
    assert set(counts(told, "commands")) == {len(SCRIPTS)}
    assert counts("It has 12 skills, Six commands and other skills.", "skills") == [12]
