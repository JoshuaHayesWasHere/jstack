"""The `sh` blocks of a skill, and running one as its reader does.

A skill tells an agent to run a block, often "with the block at the top": the skill's first
block, which sets `$H`, `$T` and the helpers, goes in front of it in the same call. The
agent's shell is the user's, zsh here, so a block is run under a shell given by name. Every
test that lifts a block out of a skill, a playbook or a template lifts it with `blocks`, and
runs it with `run`. `conftest.py` names this module in `pytest_plugins`.
"""

import re
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).parent.parent
SKILLS = REPO / "skills"
FENCED = re.compile(r"^([ \t]*)```sh\n(.*?)^\1```$", re.M | re.S)
GUARD = 'if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi'
NAMED = re.compile(r"read `\$T/\.\./skills/([^/`]+)/([^/`]+\.md)` now")


def beside(line, path):
    """The files beside the skill at `path` that `line` says to read now."""
    return [
        path.parent / name
        for skill, name in NAMED.findall(line)
        if skill == path.parent.name and name != "SKILL.md"
    ]


def named(path):
    """Every file beside the skill at `path` that one of its lines says to read now."""
    return [found for line in path.read_text().splitlines() for found in beside(line, path)]


def as_read(path):
    """A skill's text as an agent reads it: each file beside it that a line says to read now
    follows that line. A file the line names that is not there fails the test."""
    out = []
    for line in path.read_text().splitlines(keepends=True):
        out += [line, *("\n" + found.read_text() for found in beside(line, path))]
    return "".join(out)


def blocks(text):
    """The body of every `sh` block in `text`, indent taken off, in order."""
    return [textwrap.dedent(body) for _, body in FENCED.findall(text)]


def located(text):
    """Each `sh` block of `text` with the number of its fence's line, in order."""
    return [
        (text.count("\n", 0, found.start()) + 1, textwrap.dedent(found.group(2)))
        for found in FENCED.finditer(text)
    ]


def skill_blocks(skill):
    """Every `sh` block of the skill named `skill`, as an agent reads it."""
    return blocks(as_read(SKILLS / skill / "SKILL.md"))


def block(skill, marker):
    """The one `sh` block of the skill named `skill`, as an agent reads it, that has `marker`
    in it."""
    (found,) = [one for one in skill_blocks(skill) if marker in one]
    return found


def top(skill):
    """The block at the top of the skill named `skill`: its first."""
    return skill_blocks(skill)[0]


def run(skill, body, shell="sh", **given):
    """Run `body` under `shell` with the block at the top of `skill` in front of it, in one
    call, as an agent runs a block "with the block at the top". `given` goes to
    `subprocess.run`: `cwd`, `env` and the like."""
    return subprocess.run(
        [shell, "-c", f"{top(skill)}\n{body}"], capture_output=True, text=True, **given
    )
