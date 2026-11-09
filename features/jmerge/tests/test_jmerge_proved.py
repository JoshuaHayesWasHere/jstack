"""A pull request that changes tests merges only once its Result's `Proved:` line shows those
tests fail over its merge-base's code and pass at its head. A suite that also passes at the base
proves nothing (#968's `Proves it` printed 853 passed at its base while its named test failed
there). One that changes no test is exempt, and a `Proved: none, <kind>` line it writes holds
where each file it changes is of that kind (`jbriefs.proved.EXEMPT`).

The first tests run `jmerge` against the fake `gh` and real origin of `test_home_merge`: a held, a
passing and an exempt pull request. The rest drive `ready.short_on_proved`, which `jmerge` calls
before a merge, through each way a line falls short."""

import re
from dataclasses import replace

import pytest

import test_home_merge as merge
from jbriefs import proved as proved_line
from jmerge import ready

TEST = "features/x/tests/test_x.py"
BASE = "c" * 40
HEAD = "d" * 40


def proved(base_exit=1, head_exit=0, tests=TEST, head=HEAD):
    return f"Proved: {tests} base exit {base_exit} at {BASE}, head exit {head_exit} at {head}\n"


PATCH = "features/t3code-jstack/packaging/0030-jstack-tree-home-start-says.patch"
PKGBUILD = "features/t3code-jstack/packaging/PKGBUILD"
FORK_TEST = "apps/server/src/jstack/JbusWork.test.ts"


def fork(base_exit=1, head_exit=0, tests=FORK_TEST, head=HEAD):
    return (
        f"Proved: {tests} base exit {base_exit} at {BASE}, head exit {head_exit} at {head}, "
        "fork patches\n"
    )


def head_alone(head_exit=0, tests=TEST, head=HEAD):
    return f"Proved: {tests} head exit {head_exit} at {head}, tests only\n"


@pytest.fixture
def merged(tmp_path):
    return merge.Merged(merge.Home(tmp_path), tmp_path)


def opened(merged, files, result=""):
    """The pull request lists `files`, and its brief's Result adds `result`."""
    merged.home.open_pull_request(merged.head, files=files)
    text = merge.brief(merge.review("clean", merged.head), result)
    (merged.home.tasks / "alpha.md").write_text(text)


def test_a_pull_request_that_changes_a_test_and_has_no_proved_line_waits(merged):
    opened(merged, ("a.py", TEST))
    (said,) = merged.run()
    why = ready.PROVED_MISSING.format(tests=TEST)
    assert said == f"wait 7 {merge.URL}: {why}"
    assert merged.untouched()


def test_a_pull_request_whose_tests_fail_at_its_base_and_pass_at_its_head_merges(merged):
    opened(merged, ("a.py", TEST), proved(head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_proved_line_of_a_head_whose_patch_changed_since_waits(merged):
    """The line is of main's own commit, whose patch is not the head's, as the line of a head
    before a fix for a review's finding is."""
    opened(merged, ("a.py", TEST), proved(head=merged.start))
    (said,) = merged.run()
    why = ready.PROVED_STALE.format(at=merged.start[:12], head=merged.head[:12])
    assert said == f"wait 7 {merge.URL}: {why}"
    assert merged.untouched()


def test_a_docs_and_config_pull_request_that_says_so_is_exempt_and_merges(merged):
    opened(merged, ("README.md", ".github/workflows/check.yml"), "Proved: none, docs and config\n")
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_pull_request_that_changes_only_tests_and_says_so_merges_on_its_head_run(merged):
    """A test made faster passes at its base too, since the code under it is the head's own: its
    proof is the run at the head, and only where every file it changes is a test."""
    opened(merged, (TEST, "features/x/tests/conftest.py"), head_alone(head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_pull_request_that_changes_code_and_says_tests_only_waits(merged):
    opened(merged, ("a.py", TEST), head_alone(head=merged.head))
    (said,) = merged.run()
    assert said.startswith(f"wait 7 {merge.URL}: its Result's Proved: line says tests only")
    assert merged.untouched()


def test_a_pull_request_that_changes_tests_docs_and_config_merges_on_its_head_run(merged):
    """A removal of tests has no base run that fails, and the docs lint makes it carry the edit to
    the doc that named them: docs and config change no code, so its head run proves it."""
    files = (TEST, "features/x/docs/x.md", "pyproject.toml")
    opened(merged, files, head_alone(head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_fork_patch_pull_request_waits_until_its_fork_line_binds_its_head(merged):
    """A fork's tests are inside its patches, so no repo test changes: jmerge still waits for the
    line that runs them over the base's patches and the head's, and merges once it binds."""
    opened(merged, (PATCH, PKGBUILD))
    (said,) = merged.run()
    assert (
        said == f"wait 7 {merge.URL}: {ready.PROVED_MISSING.format(tests=f'{PATCH}, {PKGBUILD}')}"
    )
    assert merged.untouched()
    opened(merged, (PATCH, PKGBUILD), fork(head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_pull_request_whose_tests_pass_at_its_base_waits(merged):
    opened(merged, ("a.py", TEST), proved(base_exit=0, head=merged.head))
    (said,) = merged.run()
    assert re.fullmatch(f"wait 7 {re.escape(merge.URL)}: its Proved: line says .* exit 0 .*", said)
    assert merged.untouched()


def one(*files, removed=()):
    return ready.PullRequest(
        number=7,
        url=merge.URL,
        title="",
        branch="alpha",
        head=HEAD,
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=files,
        renamed=False,
        changed=len(files),
        removed=removed,
    )


def result(line=""):
    return f"# alpha: a task\n\n## Result\nStatus: done\n{line}"


@pytest.mark.parametrize(
    ("pull", "line", "short"),
    [
        (one("a.py", TEST), proved(), ""),
        (one("a.py", TEST), proved(tests=f"{TEST}, b_test.py"), ""),
        (one("a.py", "tests/conftest.py"), "", ""),
        (one("a.py", TEST), "", ready.PROVED_MISSING.format(tests=TEST)),
        (
            one("a.py", TEST),
            proved(base_exit=0),
            ready.PROVED_BASE_PASSED.format(exit=0, base=BASE[:12]),
        ),
        (
            one("a.py", TEST),
            proved(base_exit=5),
            ready.PROVED_BASE_PASSED.format(exit=5, base=BASE[:12]),
        ),
        (
            one("a.py", TEST),
            proved(base_exit=124),
            ready.PROVED_BASE_PASSED.format(exit=124, base=BASE[:12]),
        ),
        (
            one("a.py", TEST),
            proved(head_exit=1),
            ready.PROVED_HEAD_FAILED.format(exit=1, head=HEAD[:12]),
        ),
        (
            one("a.py", TEST, "b/b_test.py"),
            proved(),
            ready.PROVED_UNNAMED.format(tests="b/b_test.py"),
        ),
        (one("a.py", TEST, "b/b_test.py", removed=("b/b_test.py",)), proved(), ""),
        (one("docs/how.md", "jmerge.md"), "Proved: none, docs\n", ""),
        (one("pyproject.toml", "uv.lock", ".gitignore"), "Proved: none, config\n", ""),
        (
            one("a.md", TEST),
            "Proved: none, docs\n",
            ready.PROVED_NOT_EXEMPT.format(tests=TEST),
        ),
        (
            one("a.md", "a.py"),
            "Proved: none, docs\n",
            ready.PROVED_NOT_KIND.format(kinds="docs", path="a.py"),
        ),
        (
            one("a.md"),
            "Proved: none, refactor\n",
            ready.PROVED_UNREAD.format(fault="names refactor, which is no kind of docs, config"),
        ),
        (
            one("a.py", TEST),
            "Proved: yes, it passed\n",
            ready.PROVED_UNREAD.format(
                fault="is not <tests> base exit <n> at <base>, head exit <n> at <head>"
            ),
        ),
        (one(TEST, "features/x/tests/conftest.py", "tests/data/a.json"), head_alone(), ""),
        (one(TEST, "features/x/tests/helpers.py"), head_alone(), ""),
        (one(TEST, "README.md", "features/x/docs/x.md", "pyproject.toml"), head_alone(), ""),
        (
            one(
                TEST,
                "features/x/tests/test_gone.py",
                "CONTRIBUTING.md",
                removed=("features/x/tests/test_gone.py",),
            ),
            head_alone(),
            "",
        ),
        (
            one(TEST, "README.md", "a.py"),
            head_alone(),
            ready.PROVED_UNREAD.format(
                fault="says tests only, and it changes a.py, which is no test file, docs or config"
            ),
        ),
        (
            one("a.py", TEST),
            head_alone(),
            ready.PROVED_UNREAD.format(
                fault="says tests only, and it changes a.py, which is no test file, docs or config"
            ),
        ),
        (
            one(TEST, "x/ok.py", removed=("x/ok.py",)),
            head_alone(),
            ready.PROVED_UNREAD.format(
                fault="says tests only, and it changes x/ok.py, which is no test file, docs or "
                "config"
            ),
        ),
        (one(PATCH, PKGBUILD), fork(), ""),
        (one(PATCH, PKGBUILD, "features/t3code-jstack/docs/t3code-jstack.md"), fork(), ""),
        (one(PATCH, PKGBUILD), "", ready.PROVED_MISSING.format(tests=f"{PATCH}, {PKGBUILD}")),
        (one(PATCH, removed=(PATCH,)), "", ""),
        (
            one(PATCH),
            "Proved: none, config\n",
            ready.PROVED_NOT_KIND.format(kinds="config", path=PATCH),
        ),
        (
            one(PATCH, "features/jbus/src/jbus/a.py"),
            fork(),
            ready.PROVED_UNREAD.format(
                fault="says fork patches, and it changes features/jbus/src/jbus/a.py, which is no "
                "fork patch, docs or config"
            ),
        ),
        (
            one(PATCH, TEST),
            fork(),
            ready.PROVED_UNREAD.format(
                fault=f"says fork patches, and it changes {TEST}, which is no fork patch, docs or "
                "config"
            ),
        ),
        (one(PATCH), fork(base_exit=0), ready.PROVED_BASE_PASSED.format(exit=0, base=BASE[:12])),
        (one(PATCH), fork(head_exit=1), ready.PROVED_HEAD_FAILED.format(exit=1, head=HEAD[:12])),
        (
            one(TEST),
            head_alone(head_exit=1),
            ready.PROVED_HEAD_FAILED.format(exit=1, head=HEAD[:12]),
        ),
        (
            one(TEST, "b/b_test.py"),
            head_alone(),
            ready.PROVED_UNNAMED.format(tests="b/b_test.py"),
        ),
    ],
)
def test_the_line_holds_only_where_the_tests_it_names_fail_at_the_base_and_pass_at_the_head(
    pull, line, short
):
    assert ready.short_on_proved(result(line), pull) == short
    if short:
        assert ready.code_of(short).startswith("proved-")
        assert ready.step_of(ready.code_of(short)) == "result"


@pytest.mark.parametrize(
    ("line", "pull"),
    [(proved, one("a.py", TEST)), (head_alone, one(TEST)), (fork, one(PATCH, PKGBUILD))],
)
def test_a_line_of_another_head_holds_only_where_the_head_carries_its_patch(line, pull):
    earlier = "e" * 40
    text = result(line(head=earlier))
    assert ready.short_on_proved(text, pull) == ready.PROVED_STALE.format(
        at=earlier[:12], head=HEAD[:12]
    )
    assert ready.short_on_proved(text, pull, lambda at: at == earlier) == ""
    assert (
        ready.short_on_proved(result("Proved: none, docs\n"), one("a.md"), lambda at: False) == ""
    )


def test_the_last_proved_line_under_the_result_is_the_one_read():
    text = f"Proved: none, docs\n{result(proved(base_exit=0))}{proved()}"
    assert proved_line.proved(text) == proved_line.Proved((TEST,), 1, BASE, 0, HEAD)
    assert proved_line.proved("# alpha\nProved: none, docs\n") is None


def test_github_s_deleted_files_are_the_ones_it_removes():
    listed = {
        "number": 7,
        "url": merge.URL,
        "headRefName": "alpha",
        "headRefOid": HEAD,
        "files": [
            {"path": TEST, "changeType": "DELETED"},
            {"path": "a.py", "changeType": "MODIFIED"},
        ],
        "changedFiles": 2,
    }
    pull = ready.pull_request(listed)
    assert pull.removed == (TEST,)
    assert ready.changed_tests(pull) == ()
    full = ready.listed_in_full(
        replace(pull, files=(), removed=()),
        [{"filename": TEST, "status": "removed"}, {"filename": "a.py"}],
    )
    assert full.removed == (TEST,)
