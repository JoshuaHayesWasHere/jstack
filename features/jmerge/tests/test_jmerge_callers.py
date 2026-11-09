"""`jmerge` judges a pull request's passing check against what main changed since the check
started. A clean merge over main merges it on its existing check, whether it shares a file with
main's changes or not, and even where main's file imports its files, is one they import, names
their path, or is one CI reads: no path rule tells which of main's changes its check would meet,
so main's own run over what moved catches that clash, and jbus reverts the one clear culprit
(Josh, 2026-11-05: "we don't need every pr to be up to date"). A conflict waits for a rebase.

The tests run the command against a real origin, as
`features/jmerge/tests/test_jmerge_fresh.py` does."""

import pytest

from test_jmerge_fresh import Kitchen

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


def test_main_changing_its_own_file_cleanly_merges_it_on_its_existing_check(kitchen):
    kitchen.crew("two", 7, {"src/pkg/core.py": CORE + "\n# ours\n"})
    kitchen.on_main({"src/pkg/core.py": "# theirs\n" + CORE, "src/pkg/caller.py": CALLER})
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")
    assert kitchen.updates() == []
    assert kitchen.at_main("src/pkg/core.py") == ("# theirs\n" + CORE + "\n# ours").strip()
