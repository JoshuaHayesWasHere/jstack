"""`scripts/check-jstack-docs.py` checks what the README and the docs say about the tree.

The script defines the rules, and this module runs it on fixtures. Each test runs the script as a
command, on the tree or on a small tree that has a fault in it. It then reads the `FAIL <doc>:<line>
<why>` lines and the `<n> problems` line that the script prints, after its `read` line.

Its `READ_SET` is the pages and the folders whose files the script counts or lists. A path a page
names is read only for whether it is there, so a change that removes one and edits no page does not
run this file: of 400 merges on main, 20 removed a file, and the 2 that edited no page removed
none a page named. Main's full run catches the rest.
"""

import re
import shutil
import subprocess
import sys

import pytest

from testing.paths import REPO

READ_SET = (
    "*.md",
    "features/*/docs/",
    "features/*/templates/",
    "features/*/hooks/",
    "feature.json",
)

SCRIPT = REPO / "scripts" / "check-jstack-docs.py"
ROOTS = (
    "skills",
    "features",
    "templates",
    "playbooks",
    "hooks",
    "docs",
    "scripts",
    "testing",
    ".github",
)


def printed(root):
    """What the script prints for `root`: its `read` line and its FAIL lines. It first asserts that
    the script's count of problems and its exit code agree with those lines."""
    done = subprocess.run(
        [sys.executable, "-I", SCRIPT, str(root)], capture_output=True, text=True, check=False
    )
    assert done.stderr == ""
    read, *found, count = done.stdout.splitlines()
    assert read.startswith("read ")
    assert count == f"{len(found)} problems"
    assert done.returncode == (1 if found else 0)
    return read, found


def ran(root):
    """The FAIL lines the script prints for `root`."""
    return printed(root)[1]


def test_the_trees_html_pages_are_read_and_named():
    read, _ = printed(REPO)
    pages = sorted(REPO.glob("features/*/docs/**/*.html"))
    assert pages
    for page in pages:
        assert page.relative_to(REPO).as_posix() in read.split()


@pytest.fixture
def copy(tmp_path):
    """A copy of the parts of the tree the checks read, for a test to put a fault into."""
    for source in REPO.iterdir():
        if source.is_file():
            shutil.copy(source, tmp_path / source.name)
    for name in (one for one in ROOTS if (REPO / one).is_dir()):
        shutil.copytree(REPO / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def test_a_copy_with_a_broken_link_an_unknown_skill_and_a_wrong_count_fails_each_time(copy):
    assert ran(copy) == []
    readme = copy / "README.md"
    readme.write_text(readme.read_text() + "\nSee [FAKE page](docs/fake-missing.md).\n")
    page = copy / "features" / "home" / "docs" / "state.md"
    page.write_text(page.read_text() + "\nRun `/fake-skill` first.\n")
    readme.write_text(readme.read_text() + "\nThe tree has 99 principles.\n")
    found = ran(copy)
    assert len(found) == 3, found
    assert found[0].startswith("FAIL README.md:") and "docs/fake-missing.md" in found[0]
    assert found[1].startswith("FAIL README.md:") and "counts 99 principles" in found[1]
    assert (
        found[2].startswith("FAIL features/home/docs/state.md:")
        and "/fake-skill is named" in found[2]
    )
    for line in found:
        assert re.match(r"FAIL [\w/.-]+:\d+ \S", line), line


def test_a_broken_anchor_in_the_tree_fails_with_its_line(copy):
    page = copy / "features" / "home" / "docs" / "state.md"
    lines = page.read_text().count("\n")
    link = "../../jbus/docs/jbus.md#no-such-heading"
    page.write_text(page.read_text() + f"See [the jbus page]({link}).\n")
    assert ran(copy) == [
        f"FAIL features/home/docs/state.md:{lines + 1} the link {link} goes to a heading "
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


def test_a_repo_path_that_is_gone_is_found_in_contributing_security_and_the_docs(small):
    make(
        small,
        {
            "scripts/real.py": "",
            "testing/real.py": "",
            ".github/workflows/real.yml": "",
            "CONTRIBUTING.md": (
                "Run `scripts/real.py` and `testing/real.py`, see `.github/workflows/real.yml`.\n"
                "Edit `features/x/y.py` and `features/jroles/docs/jroles.md`.\n"
                "Not `features/*/docs` or `features/<name>/src`.\n"
                "And `scripts/deploy` is elsewhere.\n"
            ),
            "SECURITY.md": "Report it as `.github/SECURITY.yml` says, and `scripts/gone.sh`.\n",
            "docs/a.md": "`testing/gone.py` and [real](../scripts/real.py)\n",
        },
    )
    assert ran(small) == [
        "FAIL CONTRIBUTING.md:2 features/x/y.py is named and the tree has no such path",
        "FAIL SECURITY.md:1 .github/SECURITY.yml is named and the tree has no such path",
        "FAIL SECURITY.md:1 scripts/gone.sh is named and the tree has no such path",
        "FAIL docs/a.md:1 testing/gone.py is named and the tree has no such path",
    ]


def test_a_skill_names_a_file_beside_it_and_a_page_may_not(small):
    make(
        small,
        {
            "features/crew/SKILL.md": "# Crew\n\n`scripts/runs.sh` and `scripts/gone.sh`\n",
            "features/crew/scripts/runs.sh": "#!/bin/sh\n",
            "docs/a.md": "[crew](../features/crew/SKILL.md) `scripts/runs.sh`\n",
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:1 scripts/runs.sh is named and the tree has no such path",
        "FAIL features/crew/SKILL.md:3 scripts/gone.sh is named and the tree has no such path",
    ]


def test_a_skill_names_a_moved_playbook_or_skill_file_where_the_layout_puts_it(small):
    make(
        small,
        {
            "features/crew/SKILL.md": "# Crew\n",
            "features/crew/side.md": "# Side\n",
            "features/crew/playbooks/moved.md": "# Moved\n",
            "skills/beta/SKILL.md": (
                "# Beta\n\n`playbooks/moved.md` `skills/crew/side.md` `skills/crew/SKILL.md`\n"
                "`playbooks/gone.md` `skills/crew/none.md` `skills/gone/SKILL.md`\n"
            ),
            "docs/a.md": (
                "`playbooks/moved.md` `skills/crew/side.md`\n"
                "[moved](../features/crew/playbooks/moved.md) [crew](../features/crew/SKILL.md)\n"
            ),
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:1 playbooks/moved.md is named and the tree has no such path",
        "FAIL docs/a.md:1 skills/crew/side.md is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 playbooks/gone.md is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 skills/crew/none.md is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 skills/gone/SKILL.md is named and the tree has no such path",
    ]


def test_a_skill_names_a_moved_template_or_hook_where_the_layout_puts_it(small):
    make(
        small,
        {
            "features/home/feature.json": (
                '{"hooks": [{"event": "SessionStart", "script": "hooks/moved.sh"}],'
                ' "gitHooks": [{"name": "pre-push", "script": "hooks/pre-push.sh"}]}'
            ),
            "features/home/templates/moved.md": "# Moved\n",
            "features/home/hooks/moved.sh": "#!/bin/sh\n",
            "features/home/hooks/pre-push.sh": "#!/bin/sh\n",
            "skills/beta/SKILL.md": (
                "# Beta\n\n`templates/moved.md` `hooks/moved.sh`\n"
                "`templates/gone.md` `hooks/gone.sh` `hooks/pre-push.sh`\n"
            ),
            "docs/a.md": "`templates/moved.md` `hooks/moved.sh`\n",
        },
    )
    assert ran(small) == [
        "FAIL docs/a.md:1 templates/moved.md is named and the tree has no such path",
        "FAIL docs/a.md:1 hooks/moved.sh is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 templates/gone.md is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 hooks/gone.sh is named and the tree has no such path",
        "FAIL skills/beta/SKILL.md:4 hooks/pre-push.sh is named and the tree has no such path",
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


def test_an_html_page_of_the_docs_is_read_as_its_text_its_code_and_its_links(small):
    make(
        small,
        {
            "features/x/docs/a.html": (
                "<!doctype html>\n<style>\n.a { background: url(/gamma) }\n"
                "/* claude-gone-1-1 skills/gone/SKILL.md */\n</style>\n"
                "<p>Run <code>/alpha &lt;slug&gt;</code>,"
                ' see <a class="x" href="#top">top</a>.</p>\n'
                '<h2 id="top">The script installs the two commands.</h2>\n'
                "<p>It installs the nine commands and has 3 skills.</p>\n"
                "<h4>/gamma</h4><p>Type <code>/delta now</code>"
                " on <code>claude-fake-5-5</code>.</p>\n"
                '<p><a href="b.html#there">b</a> <a href="b.html#nowhere">b</a>'
                ' <a href="gone.html">g</a> <a href="#nowhere">n</a></p>\n'
                "<p><code>skills/alpha/SKILL.md</code> <code>skills/gone/SKILL.md</code>"
                " and claude-gone-4-7.</p>\n"
            ),
            "features/x/docs/b.html": '<p id="there">B</p>\n',
        },
    )
    page, table = "features/x/docs/a.html", "the Models table of features/jroles/docs/jroles.md"
    read, found = printed(small)
    assert page in read.split() and "features/x/docs/b.html" in read.split()
    assert found == [
        f"FAIL {page}:8 it counts 3 skills and the tree has 2",
        f"FAIL {page}:8 it counts 9 commands and the tree has 2",
        f"FAIL {page}:9 /delta is named as a skill and skills/ has no delta",
        f"FAIL {page}:9 /gamma is named as a skill and skills/ has no gamma",
        f"FAIL {page}:10 the link b.html#nowhere goes to a heading that is not there",
        f"FAIL {page}:10 the link gone.html goes to a file that is not there",
        f"FAIL {page}:10 the link #nowhere goes to a heading that is not there",
        f"FAIL {page}:11 skills/gone/SKILL.md is named and the tree has no such path",
        f"FAIL {page}:11 the model claude-gone-4-7 is not in {table}",
    ]
