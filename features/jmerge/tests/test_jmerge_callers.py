"""`jmerge` judges a pull request's passing check against what main changed since the check
started. A clean merge over main of a pull request that shares a file with main's changes has
GitHub merge main into its branch, so that its check runs over today's main, and a conflict waits
for a rebase. One that shares no file merges on its existing check, even where main's file
imports its files, is one they import, names their path, or is one CI reads: no path rule tells
which of main's changes its check would meet, so the fast guards on its merged tree catch that
clash where the repo names them (`test_jmerge_existing_check.py`), and main's own run where it
names none (Josh, 2026-11-05: "we don't need every pr to be up to date").

The tests run the command against a real origin, as
`features/jmerge/tests/test_jmerge_fresh.py` does, in a repo with no guards."""

import pytest

from jmerge import ready
from test_jmerge_fresh import Kitchen, url

CORE = "def f():\n    return 1\n"
CALLER = "from pkg import core\n\nassert core.f() == 1\n"


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


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ({"src/pkg/core.py": CORE + "\n# ours\n"}, {"src/pkg/caller.py": CALLER}),
        ({"src/pkg/caller.py": CALLER}, {"src/pkg/core.py": CORE + "\n# theirs\n"}),
        ({"src/pkg/core.py": CORE + "\n# ours\n"}, {"docs/notes.md": "see src/pkg/core.py\n"}),
        ({"src/pkg/core.py": CORE + "\n# ours\n"}, {"Makefile": "check:\n\ttrue\n"}),
    ],
    ids=["imports-it", "it-imports", "names-its-path", "ci-reads"],
)
def test_main_changing_another_file_cleanly_merges_it_on_its_existing_check(kitchen, ours, theirs):
    kitchen.crew("two", 7, ours)
    kitchen.on_main(theirs)
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")
    assert kitchen.updates() == []


def test_main_changing_its_own_file_cleanly_has_its_check_run_over_today_s_main(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    tip = kitchen.on_main({"src/pkg/core.py": "# theirs\n" + CORE, "src/pkg/caller.py": CALLER})
    asked = ready.BASE_MOVED_ASKED.format(base="main", tip=tip[:12])
    assert kitchen.run() == [f"wait 7 {url(7)}: {asked}"]
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []


def test_main_changing_the_pull_requests_own_lines_makes_it_wait_for_a_rebase(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_CONFLICT}"]
    assert kitchen.updates() == []
