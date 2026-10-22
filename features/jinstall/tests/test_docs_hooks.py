"""The hook entries `jinstall.needs` installs are the ones the features declare.

Each hook, status line and git hook of every `features/<name>/feature.json`, read by the
generator's own crawl, is one `HookGroup`, `StatusLine` or `GitHook` of `needs()`, and
`needs()` has no other: a hook in one and not the other fails. The install reads them from
`skills.json`, so this also holds the generated file to the manifests. The hooks `needs()`
hard-coded before it read them are pinned too, so the install writes what it wrote then.
"""

import sys
from pathlib import PurePosixPath

from jinstall.harnesses import HARNESSES
from jinstall.kinds import GitHook, HookGroup, StatusLine
from jinstall.machine import Machine
from jinstall.needs import Level, needs
from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))
from jtrees.crawl import crawl

HOOKED = (HookGroup, StatusLine, GitHook)


def declared(machine):
    """Each hook kind the features' manifests ask the install for."""
    files = {one.name: machine.home / one.hooks for one in HARNESSES if one.hooks}
    found = []
    for feature in crawl(REPO).features:
        for hook in feature.hooks:
            script = f"hooks/{PurePosixPath(hook.script).name}"
            found += [
                HookGroup(
                    files[harness],
                    hook.event,
                    hook.matcher or None,
                    script,
                    refuses=hook.refuses,
                    harness=harness,
                )
                for harness in hook.harnesses
            ]
        if feature.status_line:
            script = f"hooks/{PurePosixPath(feature.status_line).name}"
            found.append(StatusLine(files["claude-code"], script))
        found += [GitHook(name, script) for name, script in feature.git_hooks]
    return found


def test_the_install_puts_each_hook_the_features_declare_and_no_other():
    machine = Machine.here(REPO)
    built = [need.kind for need in needs(machine) if isinstance(need.kind, HOOKED)]
    assert len(built) >= 8
    assert sorted(built, key=str) == sorted(declared(machine), key=str)


def hard_coded(machine):
    """The hook needs `needs()` hard-coded on origin/migration (needs.py:203-237), in its
    order, as (name, level, kind): what the manifests must give the install, one for one."""
    settings = machine.home / ".claude" / "settings.json"
    codex = machine.home / ".codex" / "hooks.json"
    pushed = machine.checkout / ".git" / "hooks" / "pre-push"
    return [
        (
            f"hook {settings} SessionStart",
            Level.HARD,
            HookGroup(settings, "SessionStart", "startup", "hooks/home-start.sh"),
        ),
        (
            f"hook {settings} UserPromptSubmit",
            Level.HARD,
            HookGroup(settings, "UserPromptSubmit", None, "hooks/skill-tips.sh"),
        ),
        (
            f"hook {settings} PostToolUse",
            Level.HARD,
            HookGroup(settings, "PostToolUse", None, "hooks/home-gauge.sh"),
        ),
        (
            f"hook {settings} PreToolUse",
            Level.HARD,
            HookGroup(settings, "PreToolUse", None, "hooks/home-gauge.sh"),
        ),
        (
            f"hook {codex} SessionStart",
            Level.HARD,
            HookGroup(codex, "SessionStart", "startup", "hooks/home-start.sh", harness="codex"),
        ),
        (
            f"hook {settings} PreToolUse",
            Level.HARD,
            HookGroup(settings, "PreToolUse", "Bash", "hooks/outbound-command.sh", refuses=True),
        ),
        (
            f"hook {pushed} pre-push",
            Level.HARD,
            GitHook("pre-push", "features/jleak/hooks/pre-push.sh"),
        ),
        (f"statusline {settings}", Level.OPTIONAL, StatusLine(settings)),
    ]


def test_the_install_builds_from_the_manifests_the_hook_needs_it_hard_coded():
    """The same needs, and in each file the groups of each event in the same order, which is
    the order a fresh install writes them in."""
    machine = Machine.here(REPO)
    hooked = (HookGroup, StatusLine, GitHook)
    built = [(n.name, n.level, n.kind) for n in needs(machine) if isinstance(n.kind, hooked)]
    expected = hard_coded(machine)
    assert sorted(built, key=str) == sorted(expected, key=str)

    def by_entry(found):
        each = {}
        for name, _, kind in found:
            each.setdefault(name, []).append(kind)
        return each

    assert by_entry(built) == by_entry(expected)
