"""No Python file of `tests/` is over `CAP` lines except the ones on `ALLOWED`. A file on the
list that is back under the cap fails until it leaves the list, so the list only shrinks. When
a test file grows past the cap, its author splits it by feature into a folder of `tests/`, as
happened with `features/jbus/tests/view/` and `features/crew/tests/`.

With no `__init__.py` in `tests/`, pytest imports each test file there by its file name alone, so
two test files with the same name fail the run with "import file mismatch". So no two test files
share a name. A folder of `tests/` is a package, with an `__init__.py`, so pytest imports the
`conftest.py` of `view/` as `view.conftest`. If pytest imported it as `conftest`, a test that
imports from the `conftest` of `tests/` would get the folder's `conftest` instead.
"""

from pathlib import Path

from testing.paths import REPO

CAP = 1500
ALLOWED = {"features/pr-review/tests/test_pr_review_skill.py"}


def files(root):
    """Each Python file of `tests/` under `root`, and of each feature's `tests/`, except the
    fixtures, with its count of lines."""
    found = {}
    for folder in [root / "tests", *sorted(root.glob("features/*/tests"))]:
        for path in sorted(folder.rglob("*.py")):
            named = path.relative_to(root).as_posix()
            if "fixtures" not in path.relative_to(folder).parts[:1]:
                found[named] = len(path.read_text().splitlines())
    return found


def against_the_cap(root, allowed):
    """`(over, under)`: the files over the cap that the list does not hold, and the files on
    the list that are no longer over it."""
    sizes = files(root)
    over = sorted(name for name, lines in sizes.items() if lines > CAP and name not in allowed)
    under = sorted(name for name in allowed if sizes.get(name, 0) <= CAP)
    return over, under


def test_no_file_of_the_tests_is_over_the_cap_but_the_allowed_and_each_allowed_one_is():
    assert against_the_cap(REPO, ALLOWED) == ([], [])


def test_a_file_over_the_cap_fails_and_an_allowed_file_back_under_it_fails_too(tmp_path):
    long, short = "x = 1\n" * (CAP + 1), "x = 1\n" * CAP
    (tmp_path / "tests" / "area").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir()
    (tmp_path / "tests" / "test_grown.py").write_text(long)
    (tmp_path / "tests" / "area" / "helpers.py").write_text(long)
    (tmp_path / "tests" / "test_allowed.py").write_text(long)
    (tmp_path / "tests" / "test_split.py").write_text(short)
    (tmp_path / "tests" / "fixtures" / "made.py").write_text(long)

    allowed = {"tests/test_allowed.py", "tests/test_split.py", "tests/test_gone.py"}

    assert against_the_cap(tmp_path, allowed) == (
        ["tests/area/helpers.py", "tests/test_grown.py"],
        ["tests/test_gone.py", "tests/test_split.py"],
    )


def test_no_two_test_files_have_one_name():
    names = {}
    for name in files(REPO):
        if Path(name).name.startswith("test_"):
            names.setdefault(Path(name).name, []).append(name)
    assert [found for found in names.values() if len(found) > 1] == []


def test_each_folder_of_the_tests_is_a_package():
    folders = {
        path.parent
        for root in (REPO / "testing" / "tests", *REPO.glob("features/*/tests"))
        for path in root.rglob("*.py")
        if path.parent != root and "fixtures" not in path.relative_to(REPO).parts
    }
    assert (
        sorted(
            folder.relative_to(REPO).as_posix()
            for folder in folders
            if not (folder / "__init__.py").exists()
        )
        == []
    )
