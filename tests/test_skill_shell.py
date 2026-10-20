"""Two lints over the shell a skill gives an agent, whose shell is zsh.

A block is sh: zsh reads it as sh only once it is asked to (`emulate sh`), and reads it its
own way before that. It splits no unquoted words, it fails a glob that matches nothing, and
`$path` is `$PATH`. So every block of a skill starts with the guard: the block at the top,
and each block after it too, since the text cannot say for sure which run alone. Under sh
the guard does nothing, and under zsh twice is the same as once.

A jstack command a skill, a playbook or a template names is parsed by that command's own
parser, its placeholders and variables filled by a stand-in, so a verb or a flag that does
not exist fails here and not in an agent's hands.
"""

import contextlib
import io
import os
import re
import shlex
import shutil
import subprocess

import pytest

from jbriefs import cli as jbriefs
from jbus import cli as jbus
from jbus import verbs
from jdrift import cli as jdrift
from jgauge import cli as jgauge
from jleak import cli as jleak
from jmerge import cli as jmerge
from jroles import cli as jroles
from skill_blocks import FENCED, GUARD, REPO, SKILLS, blocks, run

STAND_IN = "1"


def unguarded(text):
    """The first line of each block of a skill's text that has no guard."""
    return [body.splitlines()[0] for body in blocks(text) if GUARD not in body.splitlines()]


def unguarded_skills():
    """`<skill>: <first line>` for each block with no guard in a file of a skill's folder."""
    return [
        f"{path.relative_to(SKILLS).parts[0]}: {first}"
        for path in sorted(SKILLS.rglob("*.md"))
        for first in unguarded(path.read_text())
    ]


def test_every_skill_asks_zsh_to_read_its_blocks_as_sh():
    assert unguarded_skills() == []


def test_a_block_with_no_guard_is_named_also_after_a_block_at_the_top_that_has_it():
    text = (
        f"```sh\nH=~/here\n{GUARD}\n```\n\nRun this with the block at the top:\n\n"
        "```sh\necho $H\n```\n\nRun this alone:\n\n   ```sh\n   echo alone\n   ```\n"
    )
    assert unguarded(text) == ["echo $H", "echo alone"]


def test_a_block_inside_a_list_is_found_with_its_indent_taken_off():
    text = (
        "1. a\n\n   ```sh\n   if true; then\n       echo b\n   fi\n   ```\n\n```sh\necho c\n```\n"
    )
    assert blocks(text) == ["if true; then\n    echo b\nfi\n", "echo c\n"]


SPLIT = (
    'printed=" principles/a.md principles/b.md"\nfor cited in $printed; do echo "$cited"; done\n'
)


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
@pytest.mark.parametrize("skill", ["scout", "crew", "pr-review"])
def test_after_the_block_at_the_top_zsh_splits_words_as_sh_does(skill, tmp_path):
    """The loop the scout's playbook block ran at c228ac6, after the real block at the top of
    each skill whose top block lacked the guard: zsh splits no unquoted word until it is asked
    to read sh. The top block finds `$T` by the skill's link under `~/.claude/skills` and `$H`
    by the repo it runs in, both made up here."""
    user, repo = tmp_path / "user", tmp_path / "demo"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / skill).symlink_to(SKILLS / skill)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    env = {"HOME": str(user), "PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": os.devnull}
    said = {shell: run(skill, SPLIT, shell, cwd=repo, env=env) for shell in ("sh", "zsh")}
    assert [(done.stderr, done.stdout) for done in said.values()] == [
        ("", "principles/a.md\nprinciples/b.md\n")
    ] * 2


def parse_jbus(argv):
    """What `jbus` does with its words before it runs a verb: Python 3.12's argparse leaves a
    verb's words over, and `verbs.words_left` takes them back."""
    made = verbs.parser(jbus.DECLARED, jbus.__doc__)
    args, extra = made.parse_known_args(argv)
    extra = verbs.words_left(args, extra)
    if extra:
        made.error(f"unrecognized arguments: {' '.join(extra)}")


def parse_jbriefs(argv):
    if argv[:1] == ["pick"]:
        jbriefs.pick_parser().parse_args(argv[1:])
    else:
        jbriefs.parser().parse_args(argv)


PARSERS = {
    "jbus": parse_jbus,
    "jmerge": lambda argv: jmerge.parser().parse_args(argv),
    "jgauge": lambda argv: jgauge.parser().parse_args(argv),
    "jroles": lambda argv: jroles.parser().parse_args(argv[:1] if argv[:1] == ["mirror"] else argv),
    "jbriefs": parse_jbriefs,
    "jdrift": lambda argv: jdrift.parser().parse_args(argv),
    "jleak": lambda argv: jleak.parser().parse_args(argv),
}
CALL = re.compile(
    r"(?:\buv run(?: --[\w-]+)* --project \S+(?: --[\w-]+)* )?(?:[\w%~.${}/-]*/)?"
    rf"\b({'|'.join(PARSERS)})(?=\s|$|`|')"
)
BEFORE = re.compile(
    r"(?:^|[|;&(!`{]|\b(?:then|do|else|if|elif|while|until|exec|time)|-c\s+['\"]|ExecStart=)\s*$"
)
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]*>")
VARIABLE = re.compile(r"\$(?:\{[^}]*\}|\w+|[0-9@*#?$!])")
UNKNOWN = ("invalid choice", "unrecognized arguments", "ambiguous option")


def substituted(code):
    """`code` with each `<placeholder>` and each `$(...)` made the stand-in, and the code inside
    each `$(...)`, which is read for calls of its own. One the line leaves open runs to its end."""
    code, inside = PLACEHOLDER.sub(STAND_IN, code), []
    while (start := code.find("$(")) >= 0:
        depth, end = 0, len(code)
        for at in range(start + 1, len(code)):
            depth += {"(": 1, ")": -1}.get(code[at], 0)
            if depth == 0:
                end = at
                break
        inside.append(code[start + 2 : end])
        code = code[:start] + STAND_IN + code[end + 1 :]
    return code, inside


def words(rest, quote):
    """The words of a call, up to the first operator or redirection outside quotes, and whether
    each of its flags is written out. A variable in quotes is one word, the stand-in; one
    outside quotes, `${...}` included, is any number of words, and none here. A flag named by
    a variable, `"--$which"`, is chosen when the block runs, and cannot be read here."""
    if quote:
        rest = rest.split(quote, 1)[0]
    rest = re.sub(r"\$\{[^}]*\}", "$V", rest)
    lexer = shlex.shlex(rest, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True
    raw, found, written = [], [], True
    for token in lexer:
        if set(token) <= set("();<>|&"):
            if token[0] in "<>" and raw and raw[-1].isdigit():
                found.pop()
            break
        raw.append(token)
        if VARIABLE.fullmatch(token):
            continue
        word = "".join(shlex.split(token))
        written = written and not (word.startswith("-") and VARIABLE.search(word))
        found.append(VARIABLE.sub(STAND_IN, word))
    return found, written


def calls(code):
    """Each jstack call in a piece of shell: its command, its words and whether its flags are
    written out (`words`). A call stands at the
    start of the code, after an operator, after a keyword a command follows, after `sh -c '`,
    or after a unit's `ExecStart=` (`BEFORE`)."""
    code, inside = substituted(code)
    for each in inside:
        yield from calls(each)
    for found in CALL.finditer(code):
        before = code[: found.start()]
        if not BEFORE.search(before):
            continue
        quote = re.search(r"-c\s+(['\"])\s*$", before)
        yield found.group(1), *words(code[found.end() :], quote and quote.group(1))


def shell(path):
    """Each piece of shell in a file, with the number of its line and whether it is a whole
    call: every line of an `sh` block, with a line that ends in a backslash joined to the next,
    and every line of a file that is not Markdown, are; a span in backquotes in prose is not."""
    text = path.read_text()
    lines = text.splitlines()
    if path.suffix != ".md":
        for number, line in enumerate(lines, 1):
            yield number, line, True
        return
    inside = set()
    for found in FENCED.finditer(text):
        first = text.count("\n", 0, found.start()) + 2
        inside.update(range(first, first + found.group(2).count("\n")))
    joined, at = "", None
    for number, line in enumerate(lines, 1):
        if number in inside:
            joined, at = joined + line.removesuffix("\\"), at or number
            if not line.endswith("\\"):
                yield at, joined, True
                joined, at = "", None
        else:
            for span in re.findall(r"(?<!`)`([^`]+)`(?!`)", line):
                yield number, span, False


def refused(command, argv):
    """What the command's parser says of `argv`, or None where it takes it."""
    said = io.StringIO()
    with contextlib.redirect_stderr(said), contextlib.redirect_stdout(io.StringIO()):
        try:
            PARSERS[command](argv)
        except SystemExit as exit:
            if exit.code:
                return said.getvalue().strip().splitlines()[-1]
    return None


def printed(span, blocks_text):
    """Whether a span in backquotes quotes what a block prints: its words up to the first
    placeholder, variable or colon stand in a block, and not where a call starts."""
    head = re.split(r"[<$:]", span)[0].strip()
    for found in re.finditer(re.escape(head), blocks_text):
        line = blocks_text[blocks_text.rfind("\n", 0, found.start()) + 1 : found.start()]
        if not BEFORE.search(line):
            return True
    return False


def problems(paths, root=REPO):
    """`<file>:<line>: <the call, filled in>: <what its parser said>` for each call refused.
    Prose names a verb or a flag with no other argument, so a span in backquotes fails only
    on what a parser says of a verb or a flag it does not have (`UNKNOWN`), and so does a call
    whose flag is chosen when the block runs."""
    blocks_text = "\n".join(
        body for path in paths if path.suffix == ".md" for body in blocks(path.read_text())
    )
    for path in paths:
        for number, piece, whole in shell(path):
            for command, argv, written in calls(piece):
                why = refused(command, argv)
                if not why or not (whole and written) and not any(kind in why for kind in UNKNOWN):
                    continue
                if not whole and printed(piece, blocks_text):
                    continue
                yield f"{path.relative_to(root)}:{number}: {shlex.join([command, *argv])}: {why}"


NAMED = [
    path
    for directory in ("skills", "playbooks", "templates")
    for path in sorted((REPO / directory).rglob("*"))
    if path.is_file()
]


def test_every_jstack_command_a_skill_playbook_or_template_names_parses():
    assert list(problems(NAMED)) == []


def test_the_lint_reads_calls_in_blocks_in_backquotes_and_in_units(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "Run `jgauge test-slott --short`, then `jbus gate` with no slug, which is prose.\n\n"
        "```sh\n"
        "if said=$(printf %s \"$x\" | jbus gate '<slug>' 2>&1); then echo ok; fi\n"
        "uv run --project \"$T/..\" jmerge --home '<id>' $flags \\\n"
        "    --nope\n"
        'echo "jbus merges: send nothing"\n'
        "jbus queue add\n"
        "```\n\n"
        "On `jbus merges: send nothing`, send nothing. The word jroles cook is prose.\n"
    )
    unit = tmp_path / "a.service"
    unit.write_text("[Service]\nExecStart=%h/.local/bin/jbus --project p ci --nope\n")
    assert [line.split(": ", 2)[:2] for line in problems([page, unit], tmp_path)] == [
        ["page.md:1", "jgauge test-slott --short"],
        ["page.md:5", "jmerge --home 1 --nope"],
        ["page.md:8", "jbus queue add"],
        ["a.service:2", "jbus --project p ci --nope"],
    ]


@pytest.mark.parametrize(
    ("line", "fails"),
    [
        ("jgauge test-slot -- make check", False),
        ("jgauge test-slott -- make check", True),
        ("jbus --project hydra answer 4 --by Josh --at now --default", False),
        ("jbus queue add a-slug --nope", True),
        ("jbriefs pick -", False),
        ("jbriefs --skills <brief>", False),
        ("jroles crew", False),
        ("jroles cook", True),
        ("jdrift --strict", False),
        ("jleak --all", False),
        ('said=$(uv run --project "$T/.." jgauge room --light) || said=no', False),
        ('said=$(uv run --project "$T/.." jgauge rooms --light) || said=no', True),
        ('x=$(printf %s "$(jroles cook)")', True),
        ("jbus queue add '<slug>' --priority '<n>' --entry '<entry>' < brief.md 2>&1", False),
        ('jbus plan ${scope:+--scope "$scope"}', False),
    ],
)
def test_a_call_is_held_to_its_commands_own_parser(line, fails):
    ((command, argv, _),) = calls(line)
    assert (refused(command, argv) is not None) == fails


def test_a_flag_named_by_a_variable_is_read_only_for_a_verb_it_does_not_have():
    ((_, argv, written),) = calls('jbus answer "$n" --by "$by" --at "$at" "--$which" -- "$a"')
    assert (argv[:1], written) == (["answer"], False)


def test_each_command_is_parsed_by_the_module_its_entry_point_runs():
    scripts = (REPO / "pyproject.toml").read_text().split("[project.scripts]")[1]
    named = dict(re.findall(r'^(j\w+) = "(j\w+)\.cli:main"', scripts, re.M))
    assert {command: named.get(command) for command in PARSERS} == {c: c for c in PARSERS}
