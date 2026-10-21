"""`scripts/check-jstack-docs.py`, the check of what the README and the docs say about the tree.

The script holds the rules; this module is its fixture runner. Each test runs it as a command,
on the tree or on a small tree with a fault put in, and reads the `FAIL <doc>:<line> <why>`
lines and the `<n> problems` line it prints.
"""

import importlib.util
import re
import shutil
import subprocess
import sys

import pytest

from testing.paths import REPO

SCRIPT = REPO / "scripts" / "check-jstack-docs.py"
ROOTS = ("skills", "features", "templates", "playbooks", "hooks", "docs")


def ran(root):
    """The FAIL lines the script prints on a root, with its count and exit code agreed."""
    done = subprocess.run(
        [sys.executable, "-I", SCRIPT, str(root)], capture_output=True, text=True, check=False
    )
    assert done.stderr == ""
    *found, count = done.stdout.splitlines()
    assert count == f"{len(found)} problems"
    assert done.returncode == (1 if found else 0)
    return found


def test_the_readme_and_the_docs_say_nothing_the_tree_does_not_have():
    assert ran(REPO) == []


def test_the_tree_is_read_whole_and_counted():
    spec = importlib.util.spec_from_file_location("check_jstack_docs", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = script
    spec.loader.exec_module(script)
    tree = script.Tree.read(REPO)
    assert all(tree.count(noun) >= 7 for noun in script.NOUNS)
    assert len(tree.models) >= 2
    assert len(script.docs_of(REPO)) > 40


@pytest.fixture
def copy(tmp_path):
    """A copy of the parts of the tree the checks read, for a test to put a fault into."""
    for source in REPO.iterdir():
        if source.is_file():
            shutil.copy(source, tmp_path / source.name)
    for name in ROOTS:
        shutil.copytree(REPO / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def test_a_copy_with_a_broken_link_an_unknown_skill_and_a_wrong_count_fails_each_time(copy):
    assert ran(copy) == []
    readme = copy / "README.md"
    readme.write_text(readme.read_text() + "\nSee [FAKE page](docs/fake-missing.md).\n")
    page = copy / "docs" / "state.md"
    page.write_text(page.read_text() + "\nRun `/fake-skill` first.\n")
    count = copy / "docs" / "playbooks.md"
    count.write_text(count.read_text() + "\nThe tree has 99 principles.\n")
    found = ran(copy)
    assert len(found) == 3, found
    assert found[0].startswith("FAIL README.md:") and "docs/fake-missing.md" in found[0]
    assert found[1].startswith("FAIL docs/playbooks.md:") and "counts 99 principles" in found[1]
    assert found[2].startswith("FAIL docs/state.md:") and "/fake-skill is named" in found[2]
    for line in found:
        assert re.match(r"FAIL [\w/.-]+:\d+ \S", line), line


def test_a_broken_anchor_in_the_tree_fails_with_its_line(copy):
    page = copy / "docs" / "state.md"
    lines = page.read_text().count("\n")
    page.write_text(page.read_text() + "See [the jbus page](jbus.md#no-such-heading).\n")
    assert ran(copy) == [
        f"FAIL docs/state.md:{lines + 1} the link jbus.md#no-such-heading goes to a heading "
        "that is not there"
    ]


def make(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


README = (
    "# FAKE\n\n| Command | Page |\n|---|---|\n| `fake-a` | a |\n| `fake-b` | b |\n\n"
    "[alpha](skills/alpha/SKILL.md) [beta](skills/beta/SKILL.md) [p](playbooks/p.md)\n"
)


@pytest.fixture
def small(tmp_path):
    return make(
        tmp_path,
        {
            "pyproject.toml": '[project.scripts]\nfake-a = "x:y"\nfake-b = "x:y"\n',
            "skills/alpha/SKILL.md": "# Alpha\n",
            "skills/beta/SKILL.md": "# Beta\n",
            "features/principles/skills/principle-one/SKILL.md": "# One\n",
            "playbooks/p.md": "# P\n",
            "templates/t.md": "# T\n",
            "features/jroles/docs/jroles.md": (
                "# jroles\n\n## Models\n\n| Model |\n|---|\n| `claude-fake-5-5` |\n"
            ),
            "README.md": README,
        },
    )


def test_the_small_tree_passes(small):
    assert ran(small) == []


def test_a_link_to_a_file_or_a_heading_that_is_not_there_is_found(small):
    make(
        small,
        {
            "docs/a.md": (
                "# Top\n\n## Same\n\n## Same\n\n## A `code` [heading](b.md) & more!\n"
                "[ok](b.md) [ok](b.md#the-second-one) [ok](#same-1) [ok](#a-code-heading--more)\n"
                "[web](https://example.com/x) [mail](mailto:a@b.c) [img](pic.svg)\n"
                "[gone](nope.md)\n[no heading](b.md#nowhere)\n[no self heading](#nowhere)\n"
                "`[inside code](nope.md)`\n```\n[in a fence](nope.md)\n## In a fence\n```\n"
                "[fenced heading](#in-a-fence)\n"
            ),
            "docs/b.md": "# B\n\n## The second one\n",
            "docs/pic.svg": "<svg/>",
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:10 the link nope.md goes to a file that is not there",
        "FAIL docs/a.md:11 the link b.md#nowhere goes to a heading that is not there",
        "FAIL docs/a.md:12 the link #nowhere goes to a heading that is not there",
        "FAIL docs/a.md:18 the link #in-a-fence goes to a heading that is not there",
    ]


def test_a_skill_named_that_the_tree_lacks_is_found_in_a_page_and_in_a_skill(small):
    make(
        small,
        {
            "docs/a.md": (
                "Run `/alpha run x`, then `/clear`, read `/tmp`, not `/tmp/x` or `/alpha/b`.\n"
                "Then `/gamma` and\n```\n/beta now\n/delta now\n```\n"
                "and `a /epsilon` is not read.\n"
                "The `alpha` skill, the skill `theta` and the `iota` skills.\n"
                "Use /alpha and /kappa now, not a/b, /tmp or `/alpha`; see /lambda/x.\n"
                "Built in: /loop, `/code-review high`, /simplify and /init.\n"
            ),
            "skills/beta/SKILL.md": "# Beta\n\nAsk `/zeta` for it.\n",
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:2 /gamma is named as a skill and skills/ has no gamma",
        "FAIL docs/a.md:5 /delta is named as a skill and skills/ has no delta",
        "FAIL docs/a.md:8 theta is named as a skill and skills/ has no theta",
        "FAIL docs/a.md:8 iota is named as a skill and skills/ has no iota",
        "FAIL docs/a.md:9 /kappa is named as a skill and skills/ has no kappa",
        "FAIL skills/beta/SKILL.md:3 /zeta is named as a skill and skills/ has no zeta",
    ]


def test_a_path_that_is_gone_is_found_and_one_somewhere_else_is_not_read(small):
    make(
        small,
        {
            "docs/a.md": (
                "`skills/alpha/SKILL.md` `templates/t.md` `skills/gone/SKILL.md`\n"
                "`skills/alpha/missing.md.` [a link](../templates/t.md)\n"
                "`~/.claude/skills/<name>` `$T/../playbooks/$name.md` `skills/*-mode/SKILL.md`\n"
                "`.cursor/skills/other` `skills/<skill>` and `../templates/t.md`\n"
            ),
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:1 skills/gone/SKILL.md is named and the tree has no such path",
        "FAIL docs/a.md:2 skills/alpha/missing.md is named and the tree has no such path",
    ]


def test_a_count_the_tree_disagrees_with_is_found_in_the_docs_and_not_in_a_skill(small):
    make(
        small,
        {
            "docs/a.md": (
                "`skills/` holds 2 skills and has one principle, so there are two commands.\n"
                "It has 12 skills, holds six commands and has three principles.\n"
                "The tree has 4 playbooks, and at most three skills run it. Seven commands.\n"
            ),
            "skills/beta/SKILL.md": "# Beta\n\nIt has 12 skills of its own.\n",
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:2 it counts 12 skills and the tree has 2",
        "FAIL docs/a.md:2 it counts 6 commands and the tree has 2",
        "FAIL docs/a.md:2 it counts 3 principles and the tree has 1",
        "FAIL docs/a.md:3 it counts 4 playbooks and the tree has 1",
    ]


def test_a_model_the_jroles_table_does_not_list_is_found(small):
    make(
        small,
        {
            "docs/a.md": (
                'Run it on `claude-fake-5-5`.\n```\n{"model": "claude-gone-4-7"}\n```\n'
                "Not `claude-fake-5-6` either, and claude-code is no model.\n"
            ),
        },
    )
    table = "the Models table of features/jroles/docs/jroles.md"
    assert ran(small) == [
        f"FAIL docs/a.md:3 the model claude-gone-4-7 is not in {table}",
        f"FAIL docs/a.md:5 the model claude-fake-5-6 is not in {table}",
    ]


def test_a_skill_playbook_or_command_no_table_or_link_lists_is_found(small):
    make(
        small,
        {
            "README.md": README.replace("| `fake-b` | b |\n", "").replace(
                " [p](playbooks/p.md)", ""
            ),
            "skills/gamma/SKILL.md": "# Gamma\n",
            "features/delta/SKILL.md": "# Delta\n",
            "features/eta/skills/epsilon/SKILL.md": "# Epsilon\n",
        },
    )
    assert ran(small) == [
        "FAIL README.md:1 no table row of the README names the command fake-b",
        "FAIL README.md:1 no page of the docs links playbooks/p.md",
        "FAIL README.md:1 no page of the docs links features/delta/SKILL.md",
        "FAIL README.md:1 no page of the docs links features/eta/skills/epsilon/SKILL.md",
        "FAIL README.md:1 no page of the docs links skills/gamma/SKILL.md",
    ]
