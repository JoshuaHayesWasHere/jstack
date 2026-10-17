"""`scripts/select_tests.py <base> <head>` names the test files a diff needs, from the map in
verify-jstack's `features/`, and the map is whole: every test file is a feature's or
cross-cutting, every path is a feature's, and every test file it names is there.

The script is run as CI runs it, with `python3 -I -S`, so it imports nothing installed, in a
temporary git repo that holds a copy of it, of `src/` as it is, and of a map.
The map's own tests read the repo's map and the files git tracks."""

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)
OWNED = "src/ skills/ playbooks/ principles/ templates/ hooks/ docs/ scripts/".split()
ALSO = ("evals/", ".cursor/", "install.sh")
PACKAGES = sorted(path.parent.name for path in (REPO / "src").glob("*/__init__.py"))

README = """\
# A map

Cross-cutting: `tests/test_tree.py`
"""
ALPHA = """\
# Alpha

What alpha does.

Paths: `src/alpha/`, `docs/alpha.md`
Tests: `tests/test_alpha.py`, `tests/test_both.py`
"""
BETA = """\
# Beta

What beta does.

Paths: `src/beta/*.py`
Tests: `tests/test_beta.py`, `tests/test_both.py`
"""
TESTS = {
    "conftest.py": "from test_shared import Kitchen\n",
    "test_shared.py": "class Kitchen:\n    pass\n",
    "test_tree.py": "def test_tree():\n    pass\n",
    "test_alpha.py": "def test_alpha():\n    pass\n",
    "test_beta.py": "def test_beta():\n    pass\n",
    "test_both.py": "def test_both():\n    pass\n",
    "test_helper.py": "HELP = 1\n",
    "test_user.py": "    from test_helper import HELP\n",
    "test_user_of_user.py": "import test_user\n",
}


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def write(repo, files):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)


class Repo:
    """A repo with the script, a copy of `src/`, a map and a few tests."""

    def __init__(self, root, features=None):
        self.root = root
        shutil.copy2(SCRIPT, self.put("scripts/select_tests.py"))
        shutil.copytree(REPO / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        features = features or {"README.md": README, "alpha.md": ALPHA, "beta.md": BETA}
        write(root / select.MAP, features)
        write(root / "tests", TESTS)
        write(root, {"src/alpha/a.py": "A = 1\n", "src/beta/b.py": "B = 1\n", "README.md": "#\n"})
        git(root, "init", "-q", "-b", "main")
        self.base = self.commit()

    def put(self, name):
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        return self.root / name

    def commit(self):
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
        return git(self.root, "rev-parse", "HEAD")

    def change(self, files=(), gone=(), moved=()):
        """The head after writing `files`, deleting `gone` and moving each pair of `moved`."""
        for name in files:
            with self.put(name).open("a") as file:
                file.write("\n")
        for name in gone:
            git(self.root, "rm", "-q", name)
        for old, new in moved:
            self.put(new)
            git(self.root, "mv", old, new)
        return self.commit()

    def run(self, *args):
        return subprocess.run(
            [sys.executable, "-I", "-S", self.root / "scripts" / "select_tests.py", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def selected(self, head):
        ran = self.run(self.base, head)
        assert ran.returncode == 0, ran.stderr
        return ran.stdout.splitlines()


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_a_change_selects_the_tests_of_each_feature_that_owns_it_and_the_cross_cutting(repo):
    head = repo.change(["src/alpha/a.py"])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_both.py",
        "tests/test_tree.py",
    ]


def test_two_features_selected_at_once_name_a_shared_test_once(repo):
    head = repo.change(["docs/alpha.md", "src/beta/b.py"])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "tests/test_both.py",
        "tests/test_tree.py",
    ]


def test_a_star_stays_within_one_part_of_the_path(repo):
    head = repo.change(["src/beta/deeper/c.py"])

    assert repo.selected(head) == ["tests/test_tree.py"]


def test_a_path_no_feature_owns_selects_the_cross_cutting_alone(repo):
    head = repo.change(["README.md"])

    assert repo.selected(head) == ["tests/test_tree.py"]


@pytest.mark.parametrize(
    "path",
    [
        "Makefile",
        "pyproject.toml",
        ".github/workflows/check.yml",
        "tests/conftest.py",
        "tests/fixtures/t3/tool.json",
        "tests/helpers.py",
        ".cursor/skills/verify-jstack/features/alpha.md",
        "scripts/select_tests.py",
        "src/jmerge/ready.py",
        "src/jsettings/__init__.py",
        "src/jbriefs/skills.py",
    ],
)
def test_a_path_the_whole_suite_rests_on_selects_all(repo, path):
    head = repo.change([path])

    assert repo.selected(head) == ["all"]


def test_a_changed_test_selects_itself_and_each_test_that_imports_it_however_deep(repo):
    head = repo.change(["tests/test_helper.py"])

    assert repo.selected(head) == [
        "tests/test_helper.py",
        "tests/test_tree.py",
        "tests/test_user.py",
        "tests/test_user_of_user.py",
    ]


def test_a_test_module_conftest_imports_selects_all(repo):
    head = repo.change(["tests/test_shared.py"])

    assert repo.selected(head) == ["all"]


def test_a_deleted_test_is_not_named(repo):
    head = repo.change(["src/alpha/a.py"], gone=["tests/test_alpha.py"])

    assert repo.selected(head) == ["tests/test_both.py", "tests/test_tree.py"]


def test_a_moved_file_selects_the_feature_of_the_path_it_left(repo):
    head = repo.change(moved=[("src/alpha/a.py", "lib/a.py")])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_both.py",
        "tests/test_tree.py",
    ]


def test_the_same_commits_give_the_same_lines(repo):
    head = repo.change(["src/alpha/a.py", "tests/test_helper.py", "src/beta/b.py"])

    assert repo.run(repo.base, head).stdout == repo.run(repo.base, head).stdout


def test_with_no_way_to_read_a_pattern_it_selects_all(repo):
    head = repo.change(["src/alpha/a.py"])
    shutil.rmtree(repo.root / "src" / "jmerge")

    ran = repo.run(repo.base, head)

    assert ran.returncode == 0
    assert ran.stdout == "all\n"
    assert "no pattern can be read" in ran.stderr


def test_a_matcher_whose_names_moved_selects_all(repo):
    head = repo.change(["src/alpha/a.py"])
    ready = repo.root / "src" / "jmerge" / "ready.py"
    ready.write_text(ready.read_text().replace("def _protects(", "def _covers("))

    ran = repo.run(repo.base, head)

    assert ran.returncode == 0
    assert ran.stdout == "all\n"
    assert "ImportError" in ran.stderr


def test_a_commit_git_does_not_know_fails_with_what_git_said(repo):
    ran = repo.run(repo.base, "no-such-commit")

    assert ran.returncode == 1
    assert ran.stderr.startswith("select_tests.py: git diff failed: ")


def test_a_change_to_the_view_selects_its_browser_and_axe_drive(tmp_path):
    map = REPO / select.MAP
    repo = Repo(tmp_path, {path.name: path.read_text() for path in map.glob("*.md")})
    for test in (REPO / "tests").glob("*.py"):
        shutil.copy2(test, tmp_path / "tests" / test.name)
    repo.base = repo.commit()

    head = repo.change(["src/jbus/view/page.html"])

    selected = repo.selected(head)
    assert "tests/test_jbus_view_page.py" in selected
    assert set(select.cross_cutting()) <= set(selected)
    assert "tests/test_jbus_queue.py" not in selected


def tracked(*paths):
    """The files git has or would add under `paths`."""
    listed = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", *paths)
    return listed.splitlines()


def test_every_test_file_is_a_features_or_cross_cutting():
    named = {test for _, tests in select.features().values() for test in tests}
    named |= set(select.cross_cutting())

    assert [test for test in tracked("tests/test_*.py") if test not in named] == []


def test_every_path_is_owned_by_a_feature():
    owned = [paths for paths, _ in select.features().values()]

    assert [
        path
        for path in tracked(*OWNED, *ALSO)
        if not any(select.owns(patterns, path) for patterns in owned)
    ] == []


def test_every_test_file_the_map_names_is_there():
    named = [test for _, tests in select.features().values() for test in tests]

    missing = [test for test in [*named, *select.cross_cutting()] if not tracked(test)]
    assert missing == []


def test_every_feature_has_both_lines_and_patterns_jmerge_can_read():
    for name, (paths, tests) in select.features().items():
        assert paths, f"{name} has no Paths: line"
        assert tests, f"{name} has no Tests: line"
        assert select.ready().patterns_of("\n".join(paths)) == tuple(paths)


def imports(text):
    return set(re.findall(r"^\s*(?:from|import) (\w+)", text, re.M))


def reached(package):
    """The packages of `src/` that a package imports, itself and theirs included."""
    found, todo = set(), [package]
    while todo:
        one = todo.pop()
        found.add(one)
        for path in (REPO / "src" / one).rglob("*.py"):
            todo += sorted(imports(path.read_text()) & set(PACKAGES) - found)
    return found


def test_each_test_is_named_by_a_feature_that_owns_every_package_it_imports():
    modules = {path.stem: path.read_text() for path in (REPO / "tests").glob("*.py")}
    cross = set(select.cross_cutting())
    features = select.features().values()
    short = []
    for name in modules:
        test = f"tests/{name}.py"
        if not name.startswith("test_") or test in cross:
            continue
        seen, todo, packages = set(), [name], set()
        while todo:
            one = todo.pop()
            seen.add(one)
            packages |= imports(modules[one]) & set(PACKAGES)
            todo += sorted(imports(modules[one]) & set(modules) - seen)
        for package in sorted(set().union(*map(reached, packages)) if packages else ()):
            owner = f"src/{package}/__init__.py"
            if not any(select.owns(paths, owner) and test in tests for paths, tests in features):
                short.append(f"{test} imports {package}, and no feature that owns it names it")
    assert short == []
