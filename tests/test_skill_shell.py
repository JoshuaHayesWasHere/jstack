"""Two lints over the shell a skill gives an agent, whose shell is zsh.

A block is sh: zsh reads it as sh only once it is asked to (`emulate sh`), and reads it its
own way before that. It splits no unquoted words, it fails a glob that matches nothing, and
`$path` is `$PATH`. So every skill's blocks start with the guard: in the block at the top,
for a skill whose blocks run "with the block at the top", and in each block otherwise.

A jstack command a skill, a playbook or a template names is parsed by that command's own
parser, its placeholders and variables filled by a stand-in, so a verb or a flag that does
not exist fails here and not in an agent's hands.
"""

import contextlib
import io
import re
import shlex
import shutil

import pytest

from jbriefs import cli as jbriefs
from jbus import cli as jbus
from jbus import verbs
from jdrift import cli as jdrift
from jgauge import cli as jgauge
from jleak import cli as jleak
from jmerge import cli as jmerge
from jroles import cli as jroles
from skill_blocks import FENCED, GUARD, REPO, SKILLS, as_read, blocks, run

AT_THE_TOP = re.compile(r"\bat (?:the|its) top\b")
STAND_IN = "1"


def unguarded(text):
    """The first line of each block of a skill's text that must have the guard and has not."""
    found = blocks(text)
    need = found[:1] if AT_THE_TOP.search(text) else found
    return [body.splitlines()[0] for body in need if GUARD not in body.splitlines()]


def unguarded_skills():
    return [
        f"{path.parent.name}: {first}"
        for path in sorted(SKILLS.glob("*/SKILL.md"))
        for first in unguarded(as_read(path))
    ]


def test_every_skill_asks_zsh_to_read_its_blocks_as_sh():
    assert unguarded_skills() == []


def test_a_skill_with_no_guard_in_its_block_at_the_top_is_named():
    text = "```sh\nH=~/here\n```\n\nRun this with the block at the top:\n\n```sh\necho $H\n```\n"
    assert unguarded(text) == ["H=~/here"]
    assert unguarded(text.replace("H=~/here\n", f"H=~/here\n{GUARD}\n")) == []


def test_a_skill_with_no_block_at_the_top_has_the_guard_in_each_block():
    text = f"```sh\n{GUARD}\necho a\n```\n\n```sh\necho b\n```\n"
    assert unguarded(text) == ["echo b"]


def test_a_block_inside_a_list_is_found_with_its_indent_taken_off():
    text = (
        "1. a\n\n   ```sh\n   if true; then\n       echo b\n   fi\n   ```\n\n```sh\necho c\n```\n"
    )
    assert blocks(text) == ["if true; then\n    echo b\nfi\n", "echo c\n"]


PLAYBOOK = "Run by: a scout, with a request.\n\n1. Read principles/a.md and principles/b.md.\n"


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_the_scouts_playbook_block_prints_the_same_under_zsh_as_under_sh(tmp_path):
    root = tmp_path / "root"
    (root / "playbooks").mkdir(parents=True)
    (root / "principles").mkdir()
    (root / "templates").mkdir()
    (root / "playbooks" / "look.md").write_text(PLAYBOOK)
    for name in "ab":
        (root / "principles" / f"{name}.md").write_text(f"the principle {name}\n")
    (tmp_path / "scouts").mkdir()
    (tmp_path / "scouts" / "a-question.md").write_text("# a-question\nPlaybook: look\n")
    body = next(one for one in blocks(as_read(SKILLS / "scout" / "SKILL.md")) if "printed=" in one)
    filled = f'H="{tmp_path}"\nT="{root}/templates"\nS=a-question\n{body}'
    said = {}
    for shell in ("sh", "zsh"):
        done = run("scout", filled, shell, cwd=REPO)
        assert done.stderr == ""
        said[shell] = done.stdout
    assert said["zsh"] == said["sh"]
    assert "the principle b" in said["zsh"]


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
    """`code` with each `$(...)` and each `<placeholder>` made the stand-in."""
    code = PLACEHOLDER.sub(STAND_IN, code)
    while (start := code.find("$(")) >= 0:
        depth, end = 0, start + 1
        for end in range(start + 1, len(code)):
            depth += {"(": 1, ")": -1}.get(code[end], 0)
            if depth == 0:
                break
        code = code[:start] + STAND_IN + code[end + 1 :]
    return code


def words(rest, quote):
    """The words of a call, up to the first operator or redirection outside quotes. A variable
    in quotes is one word, the stand-in; one outside quotes is any number, and none here."""
    if quote:
        rest = rest.split(quote, 1)[0]
    lexer = shlex.shlex(rest, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True
    found = []
    for token in lexer:
        if set(token) <= set("();<>|&"):
            if token[0] in "<>" and found and found[-1].isdigit():
                found.pop()
            break
        if not VARIABLE.fullmatch(token):
            found.append(VARIABLE.sub(STAND_IN, "".join(shlex.split(token))))
    return found


def calls(code):
    """Each jstack call in a piece of shell: its command and its words. A call stands at the
    start of the code, after an operator, after a keyword a command follows, after `sh -c '`,
    or after a unit's `ExecStart=` (`BEFORE`)."""
    code = substituted(code)
    for found in CALL.finditer(code):
        before = code[: found.start()]
        if not BEFORE.search(before):
            continue
        quote = re.search(r"-c\s+(['\"])\s*$", before)
        yield found.group(1), words(code[found.end() :], quote and quote.group(1))


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
    on what a parser says of a verb or a flag it does not have (`UNKNOWN`)."""
    blocks_text = "\n".join(
        body for path in paths if path.suffix == ".md" for body in blocks(path.read_text())
    )
    for path in paths:
        for number, piece, whole in shell(path):
            for command, argv in calls(piece):
                why = refused(command, argv)
                if not why or not whole and not any(kind in why for kind in UNKNOWN):
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
    ],
)
def test_a_call_is_held_to_its_commands_own_parser(line, fails):
    ((command, argv),) = calls(line)
    assert (refused(command, argv) is not None) == fails


def test_each_command_is_parsed_by_the_module_its_entry_point_runs():
    scripts = (REPO / "pyproject.toml").read_text().split("[project.scripts]")[1]
    named = dict(re.findall(r'^(j\w+) = "(j\w+)\.cli:main"', scripts, re.M))
    assert {command: named.get(command) for command in PARSERS} == {c: c for c in PARSERS}
