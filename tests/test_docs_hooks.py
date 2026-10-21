"""The table of hook entries in docs/configuration.md is the list `jinstall.needs` installs.

Each row of the table under "Hook entries" is read as a file, a key, a matcher and a script,
and each `HookGroup` and `StatusLine` of `needs()` the same way: a hook in one and not the
other fails. A git hook (`GitHook`) is no settings entry, so it is held to the lines under the
table instead: each one `needs()` puts is named there by its `.git/hooks/<name>` link and its
script, and no other is.
"""

import re

from jinstall.kinds import GitHook, HookGroup, StatusLine
from jinstall.machine import Machine
from jinstall.needs import needs
from testing.paths import REPO

PAGE = REPO / "docs" / "configuration.md"
ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)`(?:, matcher `([^`]+)`)? \| `([^`]+)` \| [^|]+ \|$")


def section():
    said = PAGE.read_text()
    start = said.index("\n## Hook entries\n")
    end = said.index("\n## ", start + 1)
    return said[start:end]


def table():
    """Each row, as (file, key, matcher, script), and the text under the table."""
    lines = section().splitlines()
    rows = [line for line in lines if line.startswith("| `")]
    under = "\n".join(lines[lines.index(rows[-1]) + 1 :])
    found = []
    for row in rows:
        match = ROW.match(row)
        assert match, f"a row that is not file, key, script, reader: {row}"
        found.append(match.groups())
    return found, under


def installed():
    """Each settings entry `needs()` puts, as a row of the table has it, and the git hooks."""
    machine = Machine.here(REPO)
    entries, git = [], []
    for need in needs(machine):
        kind = need.kind
        if isinstance(kind, HookGroup):
            shown = f"~/{kind.file.relative_to(machine.home)}"
            entries.append((shown, f"hooks.{kind.event}", kind.matcher, kind.script))
        elif isinstance(kind, StatusLine):
            shown = f"~/{kind.file.relative_to(machine.home)}"
            entries.append((shown, "statusLine", None, kind.script))
        elif isinstance(kind, GitHook):
            git.append(kind)
    return entries, git


def test_the_hook_table_lists_each_settings_entry_the_install_puts_and_no_other():
    rows, _ = table()
    entries, _ = installed()
    assert len(entries) >= 7
    assert sorted(rows, key=str) == sorted(entries, key=str)


def test_each_git_hook_the_install_links_has_its_line_under_the_table():
    _, under = table()
    _, git = installed()
    assert git
    for hook in git:
        line = next(
            (line for line in under.splitlines() if f"`.git/hooks/{hook.name}`" in line), ""
        )
        assert f"`{hook.script}`" in line, f"no line under the table names {hook.name}"
    named = set(re.findall(r"`\.git/hooks/([^`]+)`", under))
    assert named == {hook.name for hook in git}
