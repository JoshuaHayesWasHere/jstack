"""How jstack lays out its tests, beyond the repo standard. A test file's cap is a `size` rule of
`.repo-standard.yml`, which `test_module_size.py` runs. When a test file grows past it, its author
splits it by feature into a folder of `tests/`, as happened with `features/jbus/tests/view/` and
`features/crew/tests/`. The rest is jstack's extension, and this file holds it.

With no `__init__.py` in `tests/`, pytest imports each test file there by its file name alone, so
two test files with the same name fail the run with "import file mismatch". So no two test files
share a name. A folder of `tests/` is a package, with an `__init__.py`, so pytest imports the
`conftest.py` of `view/` as `view.conftest`. If pytest imported it as `conftest`, a test that
imports from the `conftest` of `tests/` would get the folder's `conftest` instead.
"""

from testing.paths import REPO

READ_SET = (
    "features/*/tests/",
    "testing/tests/",
)


def test_no_two_test_files_have_one_name():
    names = {}
    for folder in sorted(REPO.glob("features/*/tests")):
        for path in sorted(folder.rglob("test_*.py")):
            if "fixtures" not in path.relative_to(folder).parts[:1]:
                names.setdefault(path.name, []).append(path.relative_to(REPO).as_posix())
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
