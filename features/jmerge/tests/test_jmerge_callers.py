"""`jmerge` judges a pull request's passing check against what main changed since the check
started. Any change of main's has its head merged over main with `git merge-tree`
(`features/jmerge/tests/test_jmerge_fresh.py`): a clean merge has GitHub merge main into its
branch, so that its check runs over today's main, and a conflict waits for a rebase. A file of
main's that imports the pull request's files, one they import, one that names their path, or one
that CI reads is no exception: no path rule tells which of main's changes its check would meet.

The tests run the command against a real origin, as
`features/jmerge/tests/test_jmerge_fresh.py` does."""

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
        (
            {"src/pkg/core.py": CORE + "\n# ours\n"},
            {"src/pkg/core.py": "# theirs\n" + CORE, "src/pkg/caller.py": CALLER},
        ),
    ],
    ids=["imports-it", "it-imports", "names-its-path", "ci-reads", "its-own-file-cleanly"],
)
def test_main_changing_any_file_cleanly_has_its_check_run_over_today_s_main(kitchen, ours, theirs):
    kitchen.crew("two", 7, ours)
    tip = kitchen.on_main(theirs)
    asked = ready.BASE_MOVED_ASKED.format(base="main", tip=tip[:12])
    assert kitchen.run() == [f"wait 7 {url(7)}: {asked}"]
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []


def test_main_changing_the_pull_requests_own_lines_makes_it_wait_for_a_rebase(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": CORE + "\n# theirs\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_CONFLICT}"]
    assert kitchen.updates() == []
