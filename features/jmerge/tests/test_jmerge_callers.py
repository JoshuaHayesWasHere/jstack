"""`jmerge` judges a pull request's passing check against what main changed since the check
started. Only a change to the pull request's own paths has its head merged over main with
`git merge-tree` (`features/jmerge/tests/test_jmerge_fresh.py`), and a clean merge merges on the
check it has. A file of main's that imports the pull request's files, one they import, one that
names their path, or one that CI reads leaves its check counted.

The tests run the command against a real origin, as
`features/jmerge/tests/test_jmerge_fresh.py` does."""

import pytest

from jmerge import ready
from test_jmerge_fresh import GH, Kitchen, url
from test_jmerge_rejudge import UPDATE

CORE = "def f():\n    return 1\n"
CALLER = "from pkg import core\n\nassert core.f() == 1\n"


@pytest.fixture
def kitchen(tmp_path):
    kitchen = Kitchen(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/core.py": CORE,
            "docs/notes.md": "nothing here\n",
            "Makefile": "check:\n",
        },
    )
    gh = kitchen.home.stub / "gh"
    gh.write_text(GH.replace("    *) exit 64 ;;\n", UPDATE + "    *) exit 64 ;;\n"))
    return kitchen


def merged_on_its_check(kitchen):
    """The pull request merges on the check it has, GitHub is not asked to update it, and its
    line carries no note about what main changed."""
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two "), said
    assert "fresh:" not in said, said
    assert not (kitchen.home.stub / "updated").exists()
    return said


def test_main_adding_a_file_that_imports_the_pull_requests_file_leaves_its_check_counted(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/caller.py": CALLER})
    merged_on_its_check(kitchen)


def test_main_changing_a_file_the_pull_request_imports_leaves_its_check_counted(kitchen):
    kitchen.crew("two", 7, {"src/pkg/caller.py": CALLER})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    merged_on_its_check(kitchen)


def test_main_changing_a_file_that_names_the_pull_requests_path_leaves_its_check_counted(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"docs/notes.md": "see src/pkg/core.py\n"})
    said = merged_on_its_check(kitchen)
    assert said in (kitchen.home.state / "merge.log").read_text()


def test_main_changing_a_path_ci_reads_leaves_its_check_counted(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"Makefile": "check:\n\ttrue\n"})
    merged_on_its_check(kitchen)


def test_main_changing_the_pull_requests_own_file_cleanly_leaves_its_check_counted(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": "# theirs\n" + CORE, "src/pkg/caller.py": CALLER})
    merged_on_its_check(kitchen)


def test_main_changing_the_pull_requests_own_lines_makes_it_wait_for_a_rebase(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_CONFLICT}"]
    assert not (kitchen.home.stub / "updated").exists()
