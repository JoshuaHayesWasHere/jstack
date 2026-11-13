"""`jbriefs.proved` reads each kind of `Proved:` line the crew skill's proof block prints: a run at
the base and at the head, a `none, <kind>` exemption, and a run at the head alone for a pull
request that changes only tests, whose code at the base is the head's own, and a run of a fork's
own tests over its base's patches and its head's."""

import subprocess

from jbriefs import cli, proved
from jmerge import ready

HEAD = "d" * 40
TESTS = "features/x/tests/test_x.py features/x/tests/test_y.py"


def result(line):
    return f"# alpha: a task\n\n## Result\nStatus: done\n{line}\n"


def test_a_tests_only_line_names_its_tests_and_its_head_run():
    said = proved.proved(result(f"Proved: {TESTS} head exit 0 at {HEAD}, tests only"))
    assert said == proved.Proved(
        tests=("features/x/tests/test_x.py", "features/x/tests/test_y.py"),
        head_exit=0,
        head=HEAD,
        tests_only=True,
    )


def test_a_tests_only_line_keeps_a_head_exit_that_is_not_0():
    said = proved.proved(result(f"Proved: {TESTS} head exit 1 at {HEAD}, tests only"))
    assert (said.head_exit, said.tests_only, said.fault) == (1, True, "")


def test_a_base_and_head_line_is_not_tests_only():
    base = "c" * 40
    said = proved.proved(result(f"Proved: {TESTS} base exit 1 at {base}, head exit 0 at {HEAD}"))
    assert (said.base_exit, said.head_exit, said.tests_only) == (1, 0, False)


def test_a_pull_request_that_only_deletes_a_conf_file_is_config_and_not_held():
    """Infra's rt-caller-proof-runner-off deleted one runner `.conf`, KEY=VALUE settings and no
    code, and its `Proved: none, config` line held it until `config` covered `*.conf`."""
    conf = "hosts/x/runners/y.conf"
    pull = ready.PullRequest(
        number=7,
        url="https://github.com/o/r/pull/7",
        title="",
        branch="alpha",
        head=HEAD,
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=(conf,),
        renamed=False,
        changed=1,
        removed=(conf,),
    )
    assert ready.short_on_proved(result("Proved: none, config"), pull) == ""


FORK_TESTS = "apps/server/src/jstack/JbusWork.test.ts apps/web/src/x.browser.test.tsx"


def test_a_fork_patches_line_names_the_fork_s_tests_and_both_runs():
    base = "c" * 40
    said = proved.proved(
        result(f"Proved: {FORK_TESTS} base exit 1 at {base}, head exit 0 at {HEAD}, fork patches")
    )
    assert said == proved.Proved(
        tests=("apps/server/src/jstack/JbusWork.test.ts", "apps/web/src/x.browser.test.tsx"),
        base_exit=1,
        base=base,
        head_exit=0,
        head=HEAD,
        fork=True,
    )


def test_only_fork_files_docs_and_config_are_inside_the_fork():
    packaging = "features/t3code-jstack/packaging"
    inside = (f"{packaging}/0030-a.patch", f"{packaging}/PKGBUILD", "features/x/docs/x.md")
    assert proved.outside_fork(inside) == ""
    assert proved.outside_fork((*inside, "features/x/tests/test_x.py")) == (
        "features/x/tests/test_x.py"
    )
    assert proved.outside_fork((f"{packaging}/0030-a.patch", "features/x/a.py")) == (
        "features/x/a.py"
    )


CHILDREN = '''"""Children of a thread."""

LIMIT = 3
"""How many children a thread keeps."""


def kept(children):
    """The children a thread keeps, the newest first."""
    # newest first
    return sorted(children, reverse=True)[:LIMIT]
'''


def _git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    ran = subprocess.run(
        ["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return ran.stdout.strip()


def _changed(tmp_path, head_text):
    """A repo whose `origin/main` has `children.py` and whose head changes it to `head_text`,
    and the pull request of that head."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "children.py").write_text(CHILDREN)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    (tmp_path / "children.py").write_text(head_text)
    _git(tmp_path, "commit", "-q", "-am", "head")
    head = _git(tmp_path, "rev-parse", "HEAD")
    pull = ready.PullRequest(
        number=7,
        url="https://github.com/o/r/pull/7",
        title="",
        branch="alpha",
        head=head,
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=("children.py",),
        renamed=False,
        changed=1,
    )
    return pull, proved.prose_in(str(tmp_path), "origin/main", head)


DOCS_ONLY = (
    CHILDREN.replace("the newest first", "the newest first, as its doc says")
    .replace("# newest first", "# the newest first, by the stamp")
    .replace('"""How many', '"""The most')
)


def test_a_docstring_and_comment_change_to_a_py_file_proves_with_none_docs(tmp_path):
    """sidebar-home-start-says-docs fixed a docstring of jbus's children.py to agree with its
    doc, and its `Proved: none, docs` line held it, since no test fails over a docstring."""
    pull, prose = _changed(tmp_path, DOCS_ONLY)
    assert ready.short_on_proved(result("Proved: none, docs"), pull, prose=prose) == ""


def test_a_py_file_that_changes_code_beside_its_docstring_is_not_docs(tmp_path):
    pull, prose = _changed(tmp_path, DOCS_ONLY.replace("[:LIMIT]", "[: LIMIT + 1]"))
    said = ready.short_on_proved(result("Proved: none, docs"), pull, prose=prose)
    assert said == ready.PROVED_NOT_KIND.format(kinds="docs", path="children.py")


def test_a_docstring_only_py_change_is_no_config():
    """`docs` alone covers a docstring: a `none, config` line names no kind that does."""
    pull = ready.PullRequest(
        number=7,
        url="",
        title="",
        branch="alpha",
        head=HEAD,
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=("children.py",),
        renamed=False,
        changed=1,
    )
    said = ready.short_on_proved(result("Proved: none, config"), pull, prose=lambda path: True)
    assert said == ready.PROVED_NOT_KIND.format(kinds="config", path="children.py")


def test_a_file_added_deleted_or_unparsable_is_not_prose():
    assert not proved.prose_only(None, CHILDREN)
    assert not proved.prose_only(CHILDREN, None)
    assert not proved.prose_only("def (:\n", "def (:\n")


def test_a_statement_that_is_a_call_and_not_a_string_is_code():
    assert not proved.prose_only(CHILDREN, CHILDREN + "\nprint(LIMIT)\n")
    assert proved.prose_only(CHILDREN + "\nprint(LIMIT)\n", CHILDREN + "\nprint(LIMIT)  # it\n")


def test_a_head_that_shares_no_commit_with_its_base_is_not_prose(tmp_path):
    pull, _ = _changed(tmp_path, DOCS_ONLY)
    assert not proved.prose_in(str(tmp_path), "origin/gone", pull.head)("children.py")


def test_none_kinds_names_each_kind_in_order_or_the_first_file_of_none():
    assert proved.none_kinds(["pyproject.toml", "README.md"]) == (("docs", "config"), "")
    assert proved.none_kinds(["README.md", "a.py", "b.py"]) == ((), "a.py")
    assert proved.none_kinds(["a.py"], lambda path: True) == (("docs",), "")


def test_proved_none_prints_the_line_of_a_docstring_change(tmp_path, monkeypatch, capsys):
    pull, _ = _changed(tmp_path, DOCS_ONLY)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--proved-none", f"origin/main..{pull.head}"]) == 0
    assert capsys.readouterr().out == "Proved: none, docs\n"


def test_proved_none_names_the_file_of_no_kind_and_exits_1(tmp_path, monkeypatch, capsys):
    pull, _ = _changed(tmp_path, DOCS_ONLY.replace("[:LIMIT]", "[: LIMIT + 1]"))
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--proved-none", f"origin/main..{pull.head}"]) == 1
    assert capsys.readouterr().out == "no kind: children.py\n"


def test_proved_none_of_a_go_module_bump_prints_config(tmp_path, monkeypatch, capsys):
    """FAFU's af-vuln-go bumped Go modules for govulncheck findings, `go.mod` and `go.sum` and
    nothing else, and `--proved-none` said `no kind: frontdoor/go.mod` until `config` covered
    them, as it covers a `package.json` or a `*.lock` bump."""
    for path in ("frontdoor/go.mod", "frontdoor/go.sum", "go.work", "go.work.sum"):
        (tmp_path / path).parent.mkdir(exist_ok=True)
        (tmp_path / path).write_text("go 1.22\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    for path in ("frontdoor/go.mod", "frontdoor/go.sum", "go.work", "go.work.sum"):
        (tmp_path / path).write_text("go 1.24\n")
    _git(tmp_path, "commit", "-q", "-am", "bump")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--proved-none", "HEAD~1..HEAD"]) == 0
    assert capsys.readouterr().out == "Proved: none, config\n"


MAKEFILE = """\
# The checks a pull request runs, the guards first.
check-fast:
\t# the lint, then the guards
\tuv run pytest -q

define HELP
# the targets
endef
"""


def _make_changed(tmp_path, path, head_text):
    """A repo whose `origin/main` has the Makefile `path` and whose head changes it to
    `head_text`, the pull request of that head, and the `prose` its merge-base gives."""
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text(MAKEFILE)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    (tmp_path / path).write_text(head_text)
    _git(tmp_path, "commit", "-q", "-am", "head")
    head = _git(tmp_path, "rev-parse", "HEAD")
    pull = ready.PullRequest(
        number=7,
        url="https://github.com/o/r/pull/7",
        title="",
        branch="alpha",
        head=head,
        base="main",
        mergeable="MERGEABLE",
        waiting=(),
        files=(path,),
        renamed=False,
        changed=1,
    )
    return pull, proved.prose_in(str(tmp_path), "origin/main", head)


def test_a_makefile_comment_change_proves_with_none_docs(tmp_path, monkeypatch, capsys):
    """sc-makefile-guards-comment-repo-guards changed only the comment above `check-fast`, and
    `--proved-none` said `no kind: Makefile`, though no test fails over a comment."""
    for path in ("Makefile", "make/rules.mk"):
        root = tmp_path / path.replace("/", "-")
        root.mkdir()
        head_text = MAKEFILE.replace("the guards first.", "the guards first,\n# then the rest.")
        pull, prose = _make_changed(root, path, head_text.replace("# the lint", "  # the lint"))
        assert ready.short_on_proved(result("Proved: none, docs"), pull, prose=prose) == ""
        monkeypatch.chdir(root)
        assert cli.main(["--proved-none", f"origin/main..{pull.head}"]) == 0
        assert capsys.readouterr().out == "Proved: none, docs\n"


def test_a_makefile_that_changes_a_rule_or_a_define_beside_a_comment_is_no_kind(
    tmp_path, monkeypatch, capsys
):
    """A changed recipe line is code, and so is a `#` line inside a `define`, which is the
    variable's text, and a line a comment's trailing backslash swallows."""
    commented = MAKEFILE.replace("the guards first.", "the guards first, then the rest.")
    for at, head_text in enumerate(
        (
            commented.replace("pytest -q", "pytest -x"),
            MAKEFILE.replace("# the targets", "# the targets, each"),
            MAKEFILE.replace("the guards first.", "the guards first. \\"),
        )
    ):
        root = tmp_path / str(at)
        root.mkdir()
        pull, prose = _make_changed(root, "Makefile", head_text)
        said = ready.short_on_proved(result("Proved: none, docs"), pull, prose=prose)
        assert said == ready.PROVED_NOT_KIND.format(kinds="docs", path="Makefile")
        monkeypatch.chdir(root)
        assert cli.main(["--proved-none", f"origin/main..{pull.head}"]) == 1
        assert capsys.readouterr().out == "no kind: Makefile\n"


def test_proved_none_of_a_range_git_cannot_read_exits_1(tmp_path, monkeypatch, capsys):
    _changed(tmp_path, DOCS_ONLY)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--proved-none", "origin/gone..HEAD"]) == 1
    assert capsys.readouterr().out.startswith("no kind: git diff origin/gone HEAD failed")
