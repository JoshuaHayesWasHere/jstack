"""Every `grep` in a `sh` block of the Markdown under `features/` runs as `command grep`.

In a Claude Code agent shell `grep` is a shell function that runs Claude Code's embedded ugrep
with defaults of its own, and it answers some calls otherwise than grep does: `grep -qvE` said
nothing was kept where grep said a line was, and the crew's Proved block printed "tests only"
for a change to source and tests. `command grep` skips any function of that name and runs the
grep on PATH, so a block decides from grep's own answer in every shell. `UGREP` stands in for
the function, with the answer it gave to every inverted match.
"""

import re
import subprocess

from test_portable_shell import BLOCK, markdown
from testing.paths import REPO

BARE = re.compile(r"(?<![\w.-])(?<!command )grep\b")
UGREP = """grep() {
    for one in "$@"; do
        case $one in
        -[!-]*v*)
            command grep "$@" > /dev/null
            return 1
            ;;
        esac
    done
    command grep "$@"
}
"""


def bare_greps(root):
    """Each line of a `sh` block that calls grep as anything but `command grep`, as `path:line`."""
    found = []
    for path in markdown(root):
        text = path.read_text()
        for block in BLOCK.finditer(text):
            first = text.count("\n", 0, block.start(2)) + 1
            for at, line in enumerate(block.group(2).splitlines()):
                if BARE.search(line):
                    found.append(f"{path.relative_to(root)}:{first + at}")
    return found


def test_every_grep_in_a_block_an_agent_runs_is_command_grep():
    assert bare_greps(REPO) == []


def in_agent_shell(path):
    """What the one `sh` block of `path` prints in a bash where `grep` is the `UGREP` function."""
    (block,) = BLOCK.finditer(path.read_text())
    script = "\n".join(line.strip() for line in block.group(2).splitlines())
    ran = subprocess.run(["bash", "-c", UGREP + script], capture_output=True, text=True)
    return ran.stdout


def test_a_bare_grep_planted_in_a_skill_or_template_block_is_found_and_misleads_it(tmp_path):
    """A bare grep is named by its line at the start of a line, after a pipe and inside `$( )`;
    `command grep`, a `pgrep` and a grep in the prose are not. The planted template's block
    says "tests only" for a source file in an agent shell until its grep is `command grep`."""
    skill = tmp_path / "features" / "demo" / "skills" / "demo" / "SKILL.md"
    template = tmp_path / "features" / "demo" / "templates" / "a-step.md"
    for path in (skill, template):
        path.parent.mkdir(parents=True)
    skill.write_text(
        "# demo\n\nRun grep here:\n\n```sh\n"
        'grep -q x "$B"\n'
        "n=$(printf '%s\\n' \"$s\" | grep -c .)\n"
        'command grep -q x "$B" || pgrep -x demo\n'
        "```\n"
    )
    template.write_text(
        "# a step\n\n   ```sh\n"
        "   if printf 'calc.py\\ntests/test_calc.py\\n' | grep -qvE '(^|/)tests/'; then\n"
        "       echo 'source and tests'\n"
        "   else\n"
        "       echo 'tests only'\n"
        "   fi\n"
        "   ```\n"
    )
    planted = ["features/demo/skills/demo/SKILL.md:6", "features/demo/skills/demo/SKILL.md:7"]
    assert bare_greps(tmp_path) == [*planted, "features/demo/templates/a-step.md:4"]
    assert in_agent_shell(template) == "tests only\n"
    template.write_text(template.read_text().replace("| grep", "| command grep"))
    assert bare_greps(tmp_path) == planted
    assert in_agent_shell(template) == "source and tests\n"
