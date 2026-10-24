"""Every sed script in the tree's shell ends each command before a `}` with a `;` or a newline,
the way POSIX writes a `{ }` group, so macOS's BSD sed takes it as GNU sed does.

GNU sed takes `/a/{p}`, and BSD sed stops on it with "extra characters at the end of p command"
and prints nothing, so a block that reads a brief that way gets nothing from it on a Mac. A `}`
is a command too, and BSD sed wants a `;` after it before the next `}`. GNU sed has no BSD mode,
so off a Mac this guard is the check: it reads the sed scripts on each line of shell that
`test_portable_shell.shell` gives, and names each `}` that follows a command with no `;` between.
"""

import re
import subprocess

import pytest

from test_portable_shell import shell
from testing.paths import REPO

SED = re.compile(r"\bsed((?:\s+-[A-Za-z]+)*)\s+")
QUOTED = re.compile(r"('[^']*'|\"(?:[^\"\\]|\\.)*\")\s*")
MORE = re.compile(r"-e\s+")
EXPANSION = re.compile(r"\$\{[^}]*\}|\$\w+")
TO_THE_LINE = "aicrw"
LABEL = "bt:"


def scripts(line):
    """The sed scripts a line of shell runs: the quoted word after `sed` and its flags, and each
    one after a later `-e`, with a double-quoted word's shell expansions in place of their
    values."""
    for call in SED.finditer(line):
        at = call.end()
        while quoted := QUOTED.match(line, at):
            word = quoted.group(1)
            if word.startswith('"'):
                yield EXPANSION.sub("1", word[1:-1])
            else:
                yield word[1:-1]
            more = MORE.match(line, quoted.end())
            if more is None:
                break
            at = more.end()


def delimited(script, at):
    """The offset just past the text that ends at the next unescaped copy of the character at
    `at`, as a regular expression or a part of `s` ends."""
    if at >= len(script):
        return at
    delimiter, at = script[at], at + 1
    while at < len(script) and script[at] != delimiter:
        at += 2 if script[at] == "\\" else 1
    return at + 1


def address(script, at):
    """The offset just past the address, the `!`s and the blanks before a command."""
    for _ in range(2):
        if script[at : at + 1] == "/":
            at = delimited(script, at)
        elif script[at : at + 1] == "\\":
            at = delimited(script, at + 1)
        else:
            at = re.compile(r"\d*\$?").match(script, at).end()
        at = re.compile(r"(?:[~+]\d+)?\s*").match(script, at).end()
        if script[at : at + 1] != ",":
            break
        at = re.compile(r",\s*").match(script, at).end()
    return re.compile(r"[!\s]*").match(script, at).end()


def unended(script):
    """The offset of each `}` in a sed script that the command before it runs into, with no `;`
    or newline to end that command: BSD sed refuses each one."""
    found, open_command, at = [], False, 0
    while at < len(script):
        char = script[at]
        if char in ";\n":
            open_command, at = False, at + 1
            continue
        if char.isspace():
            at += 1
            continue
        if char == "}":
            if open_command:
                found.append(at)
            open_command, at = True, at + 1
            continue
        at = address(script, at)
        command = script[at : at + 1]
        if command == "{":
            open_command, at = False, at + 1
            continue
        if command in ("s", "y"):
            at = delimited(script, delimited(script, at + 1) - 1)
            at = re.compile(r"[gpIiMme\d]*").match(script, at).end()
        elif command and command in TO_THE_LINE:
            end = script.find("\n", at)
            at = len(script) if end < 0 else end
        elif command and command in LABEL:
            at = re.compile(r".[^;\n]*").match(script, at).end()
        else:
            at = re.compile(r"(?s).?\d*").match(script, at).end()
        open_command = True
    return found


def refused(root):
    """Each line of shell whose sed script BSD sed refuses, as `path:line: the script`."""
    return [
        f"{path.relative_to(root)}:{at}: {script}"
        for path, at, line in shell(root)
        for script in scripts(line)
        if unended(script)
    ]


def test_every_sed_script_in_the_tree_ends_each_command_before_a_brace():
    assert refused(REPO) == []


@pytest.mark.parametrize(
    ("gnu", "portable"),
    [
        (
            "/^Task:/,/^Pull request:/{/^Pull request:/!{/^Skills:/!p}}",
            "/^Task:/,/^Pull request:/{/^Pull request:/!{/^Skills:/!p;};}",
        ),
        ("/a/{s/x/y/g}", "/a/{s/x/y/g;}"),
        ("/a/{p;q}", "/a/{p;q;}"),
        ("/a/{p }", "/a/{p\n}"),
        ("1,3{p}", "1,3{p;}"),
    ],
)
def test_a_command_run_into_a_brace_is_found_and_its_ended_form_is_not(gnu, portable):
    assert unended(gnu) and not unended(portable)


@pytest.mark.parametrize(
    "script",
    [
        "s|{slug}|<slug>|g",
        r"s/^x \([0-9a-f]\{12\}\)[0-9a-f]\{28\}$/\1/p",
        "/[^[:space:]]/{s/^[[:space:]]*//;s/[[:space:]]*$//;p;q;}",
        "/^## Result/,$p",
        "/a}/p",
    ],
)
def test_a_brace_that_ends_no_group_is_not_found(script):
    assert unended(script) == []


def test_a_planted_brace_is_named_by_its_line_and_its_ended_form_reads_the_same_on_gnu(tmp_path):
    """The guard names the line of a block whose sed runs a `p` into `}`. With `;` before each
    `}` it names nothing, and GNU sed prints the same lines from both forms, so the fix leaves
    what a Linux run reads as it was."""
    gnu, portable = (
        "sed -n '/^Task:/,/^Pull request:/{/^Pull request:/!{/^Skills:/!p" + ends + '}\' "$B"'
        for ends in ("}", ";};")
    )
    skill = tmp_path / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"# demo\n\n```sh\necho one\n{gnu}\n```\n")
    (found,) = refused(tmp_path)
    assert found.split(": ", 1)[0] == "features/demo/SKILL.md:5"
    skill.write_text(f"# demo\n\n```sh\necho one\n{portable}\n```\n")
    assert refused(tmp_path) == []
    brief = tmp_path / "brief.md"
    brief.write_text("Size: S\nTask: make it so\nSkills: tdd\nWhere: a.py\nPull request: yes\n")

    def run(line):
        said = subprocess.run(
            ["sh", "-c", line],
            env={"B": str(brief), "PATH": "/usr/bin:/bin"},
            text=True,
            capture_output=True,
            check=True,
        )
        return said.stdout

    assert run(gnu) == run(portable) == "Task: make it so\nWhere: a.py\n"
