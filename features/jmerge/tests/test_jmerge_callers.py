"""`jmerge` judges a pull request's green against what main changed since its check started:
its own files and CI's (`features/jmerge/tests/test_jmerge_fresh.py`), and since pstack #613
a caller of its files or something they depend on, in files it does not change. Such a pull
request waits for a fresh check, which runs the repo's command on the head merged over
today's main and merges on a pass.

The command is run against a real origin, as in `features/jmerge/tests/test_jmerge_fresh.py`."""

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_fresh import BEFORE, STALE, STARTED, Kitchen, git, url, write

CORE = "def f():\n    return 1\n"
RENAMED = "def g():\n    return 1\n"
CALLER = "from pkg import core\n\nassert core.f() == 1\n"
IMPORT = "import sys\n\nsys.path.insert(0, 'src')\nimport pkg.caller\n"


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


def test_main_adding_a_caller_of_a_changed_file_makes_its_check_stale(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/caller.py": CALLER})
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('src/pkg/caller.py')}"]


def test_main_changing_what_a_changed_file_depends_on_makes_its_check_stale(kitchen):
    kitchen.crew("two", 7, {"src/pkg/caller.py": CALLER})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('src/pkg/core.py')}"]


def test_main_adding_a_caller_of_the_module_a_rename_left_makes_its_check_stale(kitchen):
    """A rename is the change most likely to break a caller: one of the old module counts."""
    kitchen.crew("two", 7, {"src/pkg/core.py": None, "src/pkg/engine.py": CORE}, renamed=True)
    (kitchen.home.stub / "left-7").write_text("src/pkg/core.py\n")
    kitchen.pulls["two"] |= {
        "files": [merge.file("src/pkg/engine.py", renamed=True)],
        "changedFiles": 1,
    }
    kitchen.checked("two", STARTED)
    kitchen.on_main({"src/pkg/caller.py": CALLER})
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {STALE.format('src/pkg/caller.py')}"]


def test_main_changing_a_file_that_names_a_changed_files_path_makes_its_check_stale(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"docs/notes.md": "see src/pkg/core.py\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('docs/notes.md')}"]


def test_main_changing_only_unrelated_files_leaves_the_check_standing(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"docs/notes.md": "still nothing about the code\n"})
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")


def test_the_fresh_check_runs_on_the_merge_result_and_catches_a_caller_main_added(kitchen):
    """The patch renames f, main adds a caller of f: each passes alone, the merge breaks.
    The fresh check runs on the merge, fails, and the pull request waits. Once the patch
    keeps a name the caller can call, the check passes over the same main and it merges."""
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
