"""A pull request that changes tests merges only once its Result's `Proved:` line shows those
tests fail over its merge-base's code and pass at its head. A suite that also passes at the base
proves nothing (#968's `Proves it` printed 853 passed at its base while its named test failed
there). One that changes no test is exempt, and a `Proved: none, <kind>` line it writes holds
where each file it changes is of that kind (`jbriefs.proved.EXEMPT`).

The first tests run `jmerge` against the fake `gh` and real origin of `test_home_merge`: a held, a
passing and an exempt pull request. The rest drive `ready.short_on_proved`, which `jmerge` calls
before a merge, through each way a line falls short."""

import re
import subprocess
from dataclasses import replace

import pytest

import jsettings
import test_home_merge as merge
from jbriefs import proved as proved_line
from jmerge import cli, forktests, ready

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


def test_a_pull_request_that_changes_a_typescript_test_and_has_no_proved_line_waits(merged):
    opened(merged, ("src/a.ts", "src/a.test.ts"))
    (said,) = merged.run()
    why = ready.PROVED_MISSING.format(tests="src/a.test.ts")
    assert said == f"wait 7 {merge.URL}: {why}"
    assert merged.untouched()


NODE_TESTS = (
    "src/a.test.ts",
    "tests/own-server.spec.ts",
    "a.test.js",
    "a.spec.jsx",
    "web/a.test.tsx",
    "a.spec.mjs",
    "a.test.mts",
    "a.spec.cjs",
)


def test_each_javascript_or_typescript_test_a_pull_request_changes_is_a_changed_test():
    pull = one("src/a.ts", "README.md", "src/test.ts", "a.test.json", "a_spec.ts", *NODE_TESTS)
    assert ready.changed_tests(pull) == NODE_TESTS


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
    assert said == f"wait 7 {merge.URL}: {ready.PROVED_MISSING.format(tests=PATCH)}"
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
        (one(PATCH, PKGBUILD), "", ready.PROVED_MISSING.format(tests=PATCH)),
        (one(PATCH, removed=(PATCH,)), "", ""),
        (one(PKGBUILD), "", ""),
        (one(PATCH, PKGBUILD, removed=(PATCH,)), "", ""),
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


def test_a_py_file_git_does_not_show_at_both_sides_is_no_docs_and_waits(merged):
    """jmerge asks git for the base and the head of each `.py` file a `none, docs` line covers:
    a file the pull request adds has no base, so its change is no docstring's alone."""
    opened(merged, ("a.py",), "Proved: none, docs\n")
    (said,) = merged.run()
    why = ready.PROVED_NOT_KIND.format(kinds="docs", path="a.py")
    assert said == f"wait 7 {merge.URL}: {why}"
    assert merged.untouched()


def test_jmerge_cli_asks_git_whether_a_py_file_changes_in_its_docstrings_alone(tmp_path):
    """`jmerge.cli.Repo.prose` fetches origin once and reads the file at the merge-base of the
    pull request's base on origin and at its head, so a docstring's rewording is docs and a
    changed line of code is not."""

    def git(*args):
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        ran = subprocess.run(
            ["git", *identity, *args], cwd=tmp_path, check=True, capture_output=True, text=True
        )
        return ran.stdout.strip()

    git("init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text('def f():\n    """Old words."""\n    return 1\n')
    (tmp_path / "b.py").write_text("X = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("remote", "add", "origin", str(tmp_path))
    git("switch", "-q", "-c", "alpha")
    (tmp_path / "a.py").write_text('def f():\n    """New words."""  # and a note\n    return 1\n')
    (tmp_path / "b.py").write_text("X = 2\n")
    git("commit", "-q", "-am", "head")
    one = ready.PullRequest(
        number=7,
        url="",
        title="",
        branch="alpha",
        head=git("rev-parse", "HEAD"),
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=("a.py", "b.py"),
        renamed=False,
        changed=2,
    )
    repo = cli.Repo(tmp_path, tmp_path / "state", None, False, user=jsettings.DEFAULTS)
    prose = repo.prose(one)
    assert (prose("a.py"), prose("b.py"), repo.fetched) == (True, False, True)


FORK_DOC = "features/t3code-jstack/docs/t3code-jstack.md"
TEST_PATCH = "features/t3code-jstack/packaging/0036-jstack-tree-scouts-from-work-test.patch"
CODE_PATCH = "features/t3code-jstack/packaging/0035-jstack-tree-held-owner.patch"
BASE_HELD = ready.PROVED_BASE_PASSED.format(exit=0, base=BASE[:12])


def patch(*paths, binary=False):
    """A fork patch as `git format-patch` writes it, touching `paths`."""
    body = "".join(
        f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
        "@@ -0,0 +1 @@\n+one line\n"
        for path in paths
    )
    binary_part = "GIT binary patch\nliteral 3\nKcmZ?wnK\n" if binary else ""
    return f"From 0 Mon Sep 17 00:00:00 2001\nSubject: [PATCH] x\n\n---\n{body}{binary_part}-- \n"


def pkgbuild(*series, tag="v0.1.7", ver="8f9a6c2e02", prepare="patch -p1"):
    names = "\n          ".join(series)
    sums = "\n            ".join("'SKIP'" for _ in ("tag", *series))
    return (
        f'_tag="${{T3CODE_JSTACK_TAG:-{tag}}}"\npkgver="0.1.7.jstack.{ver}"\npkgrel=1\n'
        f"_patches=({names})\nsha256sums=({sums})\nprepare() {{\n  {prepare}\n}}\n"
    )


def commit(merged, files, push_to="alpha"):
    """Write `files` in the crewmate's worktree, commit them and push them to `push_to`."""
    for path, text in files.items():
        (merged.tree / path).parent.mkdir(parents=True, exist_ok=True)
        (merged.tree / path).write_text(text)
    merge.git(merged.tree, "add", "-A")
    merge.git(merged.tree, "commit", "-q", "-m", "change")
    merge.git(merged.tree, "push", "-q", "origin", f"HEAD:{push_to}")
    return merge.git(merged.tree, "rev-parse", "HEAD")


def test_a_pull_request_of_tests_and_docs_whose_tests_pass_at_its_base_merges(merged):
    """A pull request that adds only a test of behaviour main already has passes at its base as
    at its head, since both run the same code: its proof block's line with base exit 0 is no
    hold, and it merges with no word of the user's."""
    files = (TEST, "features/x/docs/x.md")
    opened(merged, files, proved(base_exit=0, head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_fork_patch_of_tests_alone_whose_tests_pass_at_its_base_merges(merged):
    """#1535: a fork patch that adds a test of behaviour the fork already has, put on the series,
    with the doc that names it. Its fork line says base exit 0, as the base's series runs the same
    code, and jmerge reads the patch and the PKGBUILD from git, and merges it."""
    base = commit(
        merged,
        {
            PKGBUILD: pkgbuild(CODE_PATCH.rsplit("/", 1)[-1]),
            CODE_PATCH: patch("apps/web/src/tree.ts"),
        },
        push_to="main",
    )
    merged.start = base
    merge.git(merged.home.main, "fetch", "-q", "origin")
    merge.git(merged.home.main, "merge", "-q", "--ff-only", "origin/main")
    merged.head = commit(
        merged,
        {
            PKGBUILD: pkgbuild(
                CODE_PATCH.rsplit("/", 1)[-1], TEST_PATCH.rsplit("/", 1)[-1], ver="6ddbc07fb3"
            ),
            TEST_PATCH: patch(FORK_TEST),
            FORK_DOC: "the tree reads a scout from its work.json row\n",
        },
    )
    files = (FORK_DOC, TEST_PATCH, PKGBUILD)
    opened(merged, files, fork(base_exit=0, head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_fork_patch_that_changes_code_and_passes_at_its_base_still_waits(merged):
    merged.head = commit(
        merged, {TEST_PATCH: patch(FORK_TEST, "apps/server/src/jstack/JbusWork.ts")}
    )
    opened(merged, (TEST_PATCH, PKGBUILD), fork(base_exit=0, head=merged.head))
    (said,) = merged.run()
    why = ready.PROVED_BASE_PASSED.format(exit=0, base=BASE[:12])
    assert said == f"wait 7 {merge.URL}: {why}"
    assert merged.untouched()


@pytest.mark.parametrize(
    ("pull", "fork_tests", "short"),
    [
        (one(TEST, "README.md"), lambda path: False, ""),
        (one(TEST, "a.py"), lambda path: False, BASE_HELD),
        (one(TEST, "a.py"), lambda path: path == "a.py", BASE_HELD),
        (one(PATCH, PKGBUILD, FORK_DOC), lambda path: True, ""),
        (one(PATCH, PKGBUILD), lambda path: path == PATCH, BASE_HELD),
    ],
)
def test_a_line_that_passes_at_its_base_holds_only_where_the_pull_request_changes_code(
    pull, fork_tests, short
):
    """`fork_tests` speaks only for a fork's files: a `.py` file of this repo is code whatever it
    says, and a fork file it does not clear is code too."""
    line = fork(base_exit=0) if PATCH in pull.files else proved(base_exit=0, tests=TEST)
    assert ready.short_on_proved(result(line), pull, fork_tests=fork_tests) == short


def _side(files):
    return lambda path: files.get(path)


SERIES = ("0035-jstack-tree-held-owner.patch",)
ADDED = "0036-jstack-tree-scouts-from-work-test.patch"
DIR = "features/t3code-jstack/packaging/"


@pytest.mark.parametrize(
    ("base", "head", "alone"),
    [
        ({}, {TEST_PATCH: patch(FORK_TEST)}, True),
        ({}, {TEST_PATCH: patch(FORK_TEST, "docs/how.md")}, True),
        ({}, {TEST_PATCH: patch(FORK_TEST, "apps/server/src/a.ts")}, False),
        ({}, {TEST_PATCH: patch(FORK_TEST, "apps/web/package.json")}, False),
        ({}, {TEST_PATCH: patch(FORK_TEST, binary=True)}, False),
        ({}, {TEST_PATCH: "no diff here\n"}, False),
        ({TEST_PATCH: patch(FORK_TEST)}, {}, False),
        ({TEST_PATCH: patch("apps/server/src/a.ts")}, {TEST_PATCH: patch(FORK_TEST)}, False),
    ],
)
def test_a_fork_patch_changes_tests_alone_where_it_touches_tests_and_docs_at_both_sides(
    base, head, alone
):
    assert forktests.fork_tests_alone(TEST_PATCH, _side(base), _side(head)) is alone


def _fork(pkg, *added):
    return {
        DIR + "PKGBUILD": pkg,
        DIR + SERIES[0]: patch("apps/web/src/tree.ts"),
        **{DIR + name: patch(FORK_TEST) for name in added},
    }


@pytest.mark.parametrize(
    ("before", "after", "alone"),
    [
        (_fork(pkgbuild(*SERIES)), _fork(pkgbuild(*SERIES, ADDED, ver="6ddbc07fb3"), ADDED), True),
        (_fork(pkgbuild(*SERIES)), _fork(pkgbuild(*SERIES, ADDED, tag="v0.1.8"), ADDED), False),
        (_fork(pkgbuild(*SERIES)), _fork(pkgbuild(*SERIES, ADDED, prepare="true"), ADDED), False),
        (_fork(pkgbuild(*SERIES)), _fork(pkgbuild()), False),
        (_fork(pkgbuild(*SERIES, ADDED), ADDED), _fork(pkgbuild(*SERIES)), True),
        (
            _fork(pkgbuild(*SERIES)),
            {**_fork(pkgbuild(*SERIES, ADDED), ADDED), DIR + ADDED: patch("apps/a.ts")},
            False,
        ),
        (_fork(pkgbuild(*SERIES)), _fork(pkgbuild(*SERIES, "0037-gone.patch")), False),
    ],
)
def test_a_pkgbuild_changes_tests_alone_where_only_its_series_gains_or_loses_test_patches(
    before, after, alone
):
    assert forktests.fork_tests_alone(DIR + "PKGBUILD", _side(before), _side(after)) is alone


def test_any_other_fork_file_is_code():
    files = {DIR + "jstack.install": "post_install() { :; }\n"}
    assert not forktests.fork_tests_alone(DIR + "jstack.install", _side({}), _side(files))


def test_a_fork_file_of_a_head_with_no_merge_base_is_code(tmp_path):
    """With no merge-base there is no base to read the change from, so nothing is cleared."""
    git = ["git", "-C", str(tmp_path)]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "PKGBUILD").write_text(pkgbuild(TEST_PATCH.rsplit("/", 1)[-1]))
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run(
        [*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "head"], check=True
    )
    assert not forktests.in_repo(str(tmp_path), "no-such-base", "HEAD")(DIR + "PKGBUILD")
