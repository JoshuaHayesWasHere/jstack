"""A pull request that changes tests merges only once its Result's `Proved:` line shows those
tests fail over its merge-base's code and pass at its head. A suite that also passes at the base
proves nothing (#968's `Proves it` printed 853 passed at its base while its named test failed
there). One that changes no test is exempt, and a `Proved: none, <kind>` line it writes holds
where each file it changes is of that kind (`jbriefs.parse.EXEMPT`).

The first tests run `jmerge` against the fake `gh` and real origin of `test_home_merge`: a held, a
passing and an exempt pull request. The rest drive `ready.short_on_proved`, which `jmerge` calls
before a merge, through each way a line falls short."""

import json
import re
from dataclasses import replace

import pytest

import test_home_merge as merge
from jbriefs import parse
from jmerge import ready

TEST = "features/x/tests/test_x.py"
BASE = "c" * 40
HEAD = "d" * 40


def proved(base_exit=1, head_exit=0, tests=TEST):
    return f"Proved: {tests} base exit {base_exit} at {BASE}, head exit {head_exit} at {HEAD}\n"


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
    opened(merged, ("a.py", TEST), proved())
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_docs_and_config_pull_request_that_says_so_is_exempt_and_merges(merged):
    opened(merged, ("README.md", ".github/workflows/check.yml"), "Proved: none, docs and config\n")
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_pull_request_whose_tests_pass_at_its_base_waits(merged):
    opened(merged, ("a.py", TEST), proved(base_exit=0))
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
    ],
)
def test_the_line_holds_only_where_the_tests_it_names_fail_at_the_base_and_pass_at_the_head(
    pull, line, short
):
    assert ready.short_on_proved(result(line), pull) == short
    if short:
        assert ready.code_of(short).startswith("proved-")
        assert ready.step_of(ready.code_of(short)) == "result"


def test_the_last_proved_line_under_the_result_is_the_one_read():
    text = f"Proved: none, docs\n{result(proved(base_exit=0))}{proved()}"
    assert parse.proved(text) == parse.Proved((TEST,), 1, BASE, 0, HEAD)
    assert parse.proved("# alpha\nProved: none, docs\n") is None


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
        replace(pull, files=(), removed=()), [{"filename": TEST, "status": "removed"}, {"filename": "a.py"}]
    )
    assert full.removed == (TEST,)

