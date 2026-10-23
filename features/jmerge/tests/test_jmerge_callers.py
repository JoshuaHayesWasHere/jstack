"""`jmerge` judges a pull request's passing check against what main changed since the check
started. A change to main counts when it touches the pull request's files or CI's files
(`features/jmerge/tests/test_jmerge_fresh.py`). Since pstack #613, a change to main also counts
when it adds a caller of those files, or of something they depend on, in a file that the pull
request does not change. In a repo with a fresh-check file, such a pull request waits for a fresh
check. The check runs the repo's command on the head merged over today's main, and the pull request
merges when the check passes. A repo with no fresh-check file has no such check to run, so the
pull request merges on its green check and the merge line names what main changed.

The tests run the command against a real origin, as
`features/jmerge/tests/test_jmerge_fresh.py` does."""

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_fresh import BEFORE, STALE, STARTED, Kitchen, git, url, write

CORE = "def f():\n    return 1\n"
RENAMED = "def g():\n    return 1\n"
CALLER = "from pkg import core\n\nassert core.f() == 1\n"
IMPORT = "import sys\n\nsys.path.insert(0, 'src')\nimport pkg.caller\n"
RELATED = "fresh: none, main changed related {}; no fresh-check file"


def merged_over(kitchen, path, *flags, verb="merged"):
    """The pull request merges on its green check, and its line says what main changed."""
    (said,) = kitchen.run(*flags)
    assert said.startswith(f"{verb} 7 two "), said
    assert RELATED.format(path) in said, said
    return said


@pytest.fixture
def kitchen(tmp_path):
    return Kitchen(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/core.py": CORE,
            "docs/notes.md": "nothing here\n",
            "Makefile": "check:\n",
        },
    )


def test_main_adding_a_caller_of_a_changed_file_is_related(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/caller.py": CALLER})
    merged_over(kitchen, "src/pkg/caller.py")


def test_main_changing_what_a_changed_file_depends_on_is_related(kitchen):
    kitchen.crew("two", 7, {"src/pkg/caller.py": CALLER})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    merged_over(kitchen, "src/pkg/core.py")


def test_main_adding_a_caller_of_the_module_a_rename_left_is_related(kitchen):
    """A rename is the change most likely to break a caller, so a caller of the old module
    counts."""
    kitchen.crew("two", 7, {"src/pkg/core.py": None, "src/pkg/engine.py": CORE}, renamed=True)
    (kitchen.home.stub / "left-7").write_text("src/pkg/core.py\n")
    kitchen.pulls["two"] |= {
        "files": [merge.file("src/pkg/engine.py", renamed=True)],
        "changedFiles": 1,
    }
    kitchen.checked("two", STARTED)
    kitchen.on_main({"src/pkg/caller.py": CALLER})
    merged_over(kitchen, "src/pkg/caller.py", "--check", verb="ready")


def test_with_no_fresh_check_a_file_that_names_a_changed_path_does_not_hold_the_merge(kitchen):
    """Winnifred's #202: main changed `AGENTS.md`, which names the pull request's path. With no
    fresh-check file nothing can test the head over today's main, and a rebase would move the
    reviewed head for a file the pull request does not change, so it merges on its green check
    and says so, in its line and in merge.log."""
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"docs/notes.md": "see src/pkg/core.py\n"})
    said = merged_over(kitchen, "docs/notes.md")
    assert said in (kitchen.home.state / "merge.log").read_text()


def test_with_no_fresh_check_main_changing_the_pull_requests_own_file_still_waits(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": "# theirs\n" + CORE, "docs/notes.md": "src/pkg/core.py\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('src/pkg/core.py')}"]


def test_with_a_fresh_check_a_file_that_names_a_changed_path_queues_the_fresh_check(kitchen):
    (kitchen.home.state / "fresh-check").write_text("true\n")
    head = kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    main = kitchen.on_main({"docs/notes.md": "see src/pkg/core.py\n"})
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ")
    assert f"fresh: true passed on {head[:12]} over {main[:12]}" in said
    assert "fresh: none" not in said


def test_main_changing_only_unrelated_files_leaves_the_check_standing(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"docs/notes.md": "still nothing about the code\n"})
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")


def test_the_fresh_check_runs_on_the_merge_result_and_catches_a_caller_main_added(kitchen):
    """The patch renames f, and main adds a caller of f. Each passes alone, and the merge
    breaks. The fresh check runs on the merge, fails, and the pull request waits. Once the
    patch keeps a name that the caller can call, the check passes over the same main and the
    pull request merges."""
    (kitchen.home.state / "fresh-check").write_text("python3 check.py\n")
    kitchen.on_main({"check.py": IMPORT})
    tree = kitchen.tmp / "trees" / "two"
    head = kitchen.crew("two", 7, {"src/pkg/core.py": RENAMED})
    main = kitchen.on_main({"src/pkg/caller.py": CALLER})
    fails = f"wait 7 {url(7)}: python3 check.py fails on {head[:12]} over today's main {main[:12]}"
    assert kitchen.after_check() == [fails]
    assert "AttributeError" in (kitchen.home.state / "fresh" / "7.log").read_text()

    write(tree, {"src/pkg/core.py": RENAMED + "\nf = g\n"})
    git(tree, "commit", "-q", "-m", "keep f", at=BEFORE)
    git(tree, "push", "-q")
    head = git(tree, "rev-parse", "HEAD")
    kitchen.pulls["two"]["headRefOid"] = head
    kitchen.brief("two", head)
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ")
    assert f"fresh: python3 check.py passed on {head[:12]} over {main[:12]}" in said


def test_a_python_file_is_named_by_its_dotted_path_and_each_tail_of_it():
    assert ready.modules("src/jmerge/ready.py") == ("src.jmerge.ready", "jmerge.ready", "ready")
    assert ready.modules("src/jmerge/__init__.py") == ("src.jmerge", "jmerge")
    assert ready.modules("tests/conftest.py") == ("tests.conftest", "conftest")
    assert ready.modules("docs/jmerge.md") == ()


def test_imports_are_every_module_a_file_loads_relative_ones_read_from_its_package():
    text = (
        "import a.b.c\nfrom jmerge import cli, ready\nfrom . import sweep\nfrom .proof import x\n"
    )
    assert ready.imports("src/jmerge/claims.py", text) == {
        "a",
        "a.b",
        "a.b.c",
        "jmerge",
        "jmerge.cli",
        "jmerge.ready",
        "src",
        "src.jmerge",
        "src.jmerge.sweep",
        "src.jmerge.proof",
        "src.jmerge.proof.x",
    }
    assert ready.imports("src/jmerge/claims.py", "def (:") == set()
    assert ready.imports("docs/x.md", "import os") == set()
    ours = {"app2/models.py": "X = 1\n"}
    theirs = {
        "app1/views.py": "from .models import X\n",
        "app2/views.py": "from .models import X\n",
    }
    assert ready.callers_and_dependencies(ours, theirs) == ("app2/views.py",)


def test_callers_and_dependencies_go_both_ways_and_skip_the_rest():
    ours = {"src/jmerge/ready.py": "import re\nfrom jmerge.rangediff import Verdict\n"}
    theirs = {
        "tests/test_ready.py": "from jmerge import ready\n",
        "src/jmerge/rangediff.py": "",
        "tests/conftest.py": "",
        "skills/crew/SKILL.md": "python -c 'from jmerge import cli, ready'\n",
        "docs/jmerge.md": "the rules are in src/jmerge/ready.py\n",
        "features/jbus/src/jbus/merge.py": "import re\n",
        "README.md": "Makefile and re\n",
        "tests/test_other.py": "import jbus.merge\n",
    }
    assert ready.callers_and_dependencies(ours, theirs) == (
        "tests/test_ready.py",
        "src/jmerge/rangediff.py",
        "docs/jmerge.md",
    )
    ours = {"tests/test_ready.py": "from jmerge import ready\n"}
    assert ready.callers_and_dependencies(ours, {"tests/conftest.py": ""}) == ("tests/conftest.py",)
    ours = {"tests/test_a.py": "from test_b import X\n"}
    theirs = {"tests/test_b.py": "X = 1\n"}
    assert ready.callers_and_dependencies(ours, theirs) == ("tests/test_b.py",)
    ours = {"src/pkg/engine.py": CORE, "src/pkg/core.py": ""}
    theirs = {"src/pkg/caller.py": CALLER}
    assert ready.callers_and_dependencies(ours, theirs) == ("src/pkg/caller.py",)
