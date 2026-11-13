"""No module of a feature's `src/`, test file or SKILL.md grows past its cap. A long module is one
that many changes touch: every change appends to it, and every rebase conflicts on it. A feature
goes in a module of its own.

The caps are the `size` rules of `.repo-standard.yml`: 800 lines for a module of a feature's `src/`,
1500 for a test file of a feature's `tests/` or of `testing/tests/`, and 400 for a SKILL.md. Each
rule's `over` holds the files that were over the cap when the cap was set, with their length then. A
listed file that is back under the cap, or gone, fails until it leaves the list, so the list only
shrinks. The repo standard's `size` guard holds the rules (features/repo-standard/docs/guards.md),
and this test runs it on jstack.
"""

from repo_standard.cli import main
from repo_standard.config import load
from repo_standard.tree import chosen, tracked
from testing.paths import REPO

READ_SET = (
    "features/*/src/",
    "features/*/tests/",
    "testing/tests/",
    "SKILL.md",
    ".repo-standard.yml",
)


def test_jstack_passes_the_size_guard(capsys):
    assert main(["size", "--root", str(REPO)]) == 0
    assert capsys.readouterr().out == ""


def test_each_size_rule_picks_the_files_it_caps():
    paths = tracked(REPO)
    picked = [chosen(paths, rule.files, rule.exclude) for rule in load(REPO).part("size")]
    modules, tests, skills = picked
    assert "features/jbus/src/jbus/queue.py" in modules
    assert "features/repo-guards/tests/test_module_size.py" in tests
    assert "testing/tests/test_workflows.py" in tests
    assert not [name for name in tests if "/tests/fixtures/" in name]
    assert {"features/crew/SKILL.md", "features/home/skills/handoff/SKILL.md"} <= set(skills)
