"""`scripts/select_tests.py <base> <head>` names the test files a diff needs, from what the
tests import and name, and from the map in verify-jstack's `features/`.

The script is run as CI runs it, with `python3 -I -S`, so it imports nothing installed, in a
temporary git repo that holds a copy of it, of `src/` as it is, and of a few modules, docs and
tests of its own. The map's own tests read the repo's map and the files git tracks, and run
the tests' imports once, to see that the script found every import that was made."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys

import pytest

from testing.paths import REPO, sources

SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)
OWNED = "scripts/".split()
ALSO = (".claude/", ".cursor/", "install.sh")

README = """\
# A map

Cross-cutting:
- `tests/test_tree.py`
"""
ALPHA = """\
# Alpha

What alpha does.

Paths:
- `src/alpha/`
- `docs/alpha.md`
Tests:
- `tests/test_glob.py`
"""
BETA = """\
# Beta

What beta does.

Paths:
- `src/beta/*.py`
Tests: none
"""
FILES = {
    "src/alpha/__init__.py": "",
    "src/alpha/a.py": "from alpha import util\n",
    "src/alpha/util.py": "X = 1\n",
    "src/alpha/notes.txt": "notes\n",
    "src/beta/__init__.py": "",
    "src/beta/b.py": "import importlib\n\nimportlib.import_module('beta.plug')\n",
    "src/beta/plug.py": "P = 1\n",
    "src/gamma/__init__.py": "",
    "src/gamma/g.py": "G = 1\n",
    "tests/test_runs_gamma.py": "import subprocess\n\nsubprocess.run(['python', '-m', 'gamma'])\n",
    "tests/helper_data.py": "ROWS = 1\n",
    "tests/test_reads_helper.py": "H = Path('tests') / 'helper_data.py'\n",
    "docs/alpha.md": "# alpha\n",
    "skills/one/SKILL.md": "one\n",
    "skills/two/SKILL.md": "two\n",
    "tests/fixtures/shapes/a.json": "{}\n",
    "tests/fixtures/shapes/b.json": "{}\n",
    "tests/fixtures/orphan/x.json": "{}\n",
    "README.md": "#\n",
    "conftest.py": 'pytest_plugins = ["testing.fixtures", "test_shared"]\n',
    "testing/__init__.py": "",
    "testing/fixtures.py": (
        "import pytest\n\nimport daemons\nfrom test_kit import Kit\n\n"
        "tidy = daemons.tidy\n\n\n@pytest.fixture\ndef kit():\n    return Kit()\n"
    ),
    "tests/test_shared.py": (
        "import pytest\n\n\n@pytest.fixture\ndef shared():\n    pass\n\n\n"
        "def test_shared():\n    pass\n"
    ),
    "tests/test_own_shared.py": (
        "import pytest\n\n\n@pytest.fixture\ndef shared():\n    pass\n\n\n"
        "def test_it(shared):\n    pass\n"
    ),
    "tests/daemons.py": "def tidy():\n    pass\n",
    "tests/test_kit.py": "class Kit:\n    pass\n",
    "tests/test_uses_kit.py": "def test_it(kit):\n    pass\n",
    "tests/test_tree.py": "def test_tree():\n    pass\n",
    "tests/test_alpha.py": "from alpha import a\n",
    "tests/test_beta.py": "import beta.b\n",
    "tests/helper.py": "import alpha.util\n",
    "tests/test_helped.py": "from helper import HELP\n",
    "tests/test_glob.py": "def test_glob():\n    pass\n",
    "tests/test_doc.py": "from pathlib import Path\n\nDOC = Path('docs') / 'alpha.md'\n",
    "tests/test_one.py": "from pathlib import Path\n\nS = Path('skills') / 'one' / 'SKILL.md'\n",
    "tests/test_two.py": "SKILL = 'skills/two/SKILL.md'\n",
    "tests/test_shapes.py": "S = Path('tests') / 'fixtures' / 'shapes'\n",
    "tests/test_helper.py": "HELP = 1\n",
    "tests/test_user.py": "def use():\n    from test_helper import HELP\n",
    "tests/test_user_of_user.py": "import test_user\n",
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
    """A repo with the script, a copy of each folder of packages, a map and a few modules and
    tests."""

    def __init__(self, root, features=None, files=None):
        self.root = root
        shutil.copy2(SCRIPT, self.put("scripts/select_tests.py"))
        for folder in sources():
            shutil.copytree(
                folder,
                root / folder.relative_to(REPO),
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        features = features or {"README.md": README, "alpha.md": ALPHA, "beta.md": BETA}
        cross = {select.CROSS: features.pop("README.md")} if "README.md" in features else {}
        write(root / select.MAP, features)
        write(root, cross)
        write(root, FILES if files is None else files)
        git(root, "init", "-q", "-b", "main")
        self.base = self.commit()

    def commit_head(self):
        return git(self.root, "rev-parse", "HEAD")

    def put(self, name):
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        return self.root / name

    def commit(self):
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
        return git(self.root, "rev-parse", "HEAD")

    def change(self, files=(), gone=(), moved=(), text=None):
        """The head after writing `files`, deleting `gone` and moving each pair of `moved`."""
        for name in files:
            with self.put(name).open("a") as file:
                file.write(text or "\n")
        for name in gone:
            git(self.root, "rm", "-q", name)
        for old, new in moved:
            self.put(new)
            git(self.root, "mv", old, new)
        return self.commit()

    def run(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-I", "-S", self.root / "scripts" / "select_tests.py", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            env=env,
        )

    def selected(self, head):
        ran = self.run(self.base, head)
        assert ran.returncode == 0, ran.stderr
        return ran.stdout.splitlines()


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_a_changed_module_selects_each_test_that_imports_it_directly_or_by_a_chain(repo):
    head = repo.change(["src/alpha/util.py"])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


MOVED = {
    "features/delta/src/delta/__init__.py": "",
    "features/delta/src/delta/d.py": "from delta import util\n\nROWS = 'rows.txt'\n",
    "features/delta/src/delta/util.py": "U = 1\n",
    "features/delta/src/delta/rows.txt": "rows\n",
    "features/delta/tests/test_delta.py": "from delta import d\n",
    "tests/test_runs_delta.py": "import subprocess\n\nsubprocess.run(['python', '-m', 'delta'])\n",
}


@pytest.mark.parametrize(
    "path", ["features/delta/src/delta/util.py", "features/delta/src/delta/rows.txt"]
)
def test_a_change_in_a_feature_src_selects_its_importers_and_the_tests_that_run_its_package(
    tmp_path, path
):
    repo = Repo(tmp_path, files={**FILES, **MOVED})
    head = repo.change([path])

    selected = repo.selected(head)

    assert {"features/delta/tests/test_delta.py", "tests/test_runs_delta.py"} <= set(selected)
    assert "tests/test_alpha.py" not in selected


def test_a_module_imported_by_name_is_imported_by_the_module_that_imports_by_name(repo):
    head = repo.change(["src/beta/plug.py"])

    assert repo.selected(head) == ["tests/test_beta.py", "tests/test_tree.py"]


def test_a_test_that_runs_a_package_in_a_process_of_its_own_is_selected_by_a_change_to_it(repo):
    head = repo.change(["src/gamma/g.py"])

    assert repo.selected(head) == ["tests/test_runs_gamma.py", "tests/test_tree.py"]


def test_a_changed_test_module_selects_the_tests_that_spell_its_path(repo):
    head = repo.change(["tests/helper_data.py"])

    assert "tests/test_reads_helper.py" in repo.selected(head)


def test_a_file_in_a_package_that_is_no_module_selects_the_tests_of_the_modules_beside_it(repo):
    head = repo.change(["src/alpha/notes.txt"])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


def test_a_doc_selects_the_tests_that_name_it_and_the_tests_its_feature_lists(repo):
    head = repo.change(["docs/alpha.md"])

    assert repo.selected(head) == [
        "tests/test_doc.py",
        "tests/test_glob.py",
        "tests/test_tree.py",
    ]


def test_a_skill_selects_the_tests_that_name_its_directory_and_not_the_other_skills(repo):
    assert repo.selected(repo.change(["skills/one/SKILL.md"])) == [
        "tests/test_one.py",
        "tests/test_tree.py",
    ]
    repo.base = repo.commit_head()
    assert repo.selected(repo.change(["skills/two/SKILL.md"])) == [
        "tests/test_tree.py",
        "tests/test_two.py",
    ]


def test_a_file_no_feature_owns_and_no_test_names_selects_the_cross_cutting_alone(repo):
    head = repo.change(["README.md"])

    assert repo.selected(head) == ["tests/test_tree.py"]


def test_a_star_stays_within_one_part_of_the_path(repo):
    head = repo.change(["docs/other/alpha.md"])

    assert repo.selected(head) == ["tests/test_tree.py"]


def test_an_edit_to_a_feature_file_selects_that_features_tests_and_not_all(repo):
    head = repo.change([f"{select.MAP}/alpha.md"])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


@pytest.fixture
def paged(tmp_path):
    """The repo with alpha's page moved into its feature's folder, as `verify.md`."""
    features = {"README.md": README, "beta.md": BETA}
    return Repo(tmp_path, features, files={**FILES, "features/alpha/verify.md": ALPHA})


def test_a_page_in_its_features_folder_selects_its_tests_for_a_path_it_owns(paged):
    head = paged.change(["docs/alpha.md"])

    assert paged.selected(head) == [
        "tests/test_doc.py",
        "tests/test_glob.py",
        "tests/test_tree.py",
    ]


def test_an_edit_to_a_page_in_its_features_folder_selects_that_features_tests(paged):
    head = paged.change(["features/alpha/verify.md"])

    assert paged.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


def test_a_feature_with_a_page_in_both_places_selects_all(tmp_path):
    features = {"README.md": README, "alpha.md": ALPHA, "beta.md": BETA}
    repo = Repo(tmp_path, features, files={**FILES, "features/alpha/verify.md": ALPHA})
    head = repo.change(["src/alpha/a.py"])

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    assert SUMMARY.fullmatch(lines[0])["forced"] == "unread"


def test_an_edit_to_the_maps_readme_selects_the_cross_cutting_and_not_all(repo):
    head = repo.change([select.CROSS])

    assert repo.selected(head) == ["tests/test_tree.py"]


@pytest.mark.parametrize(
    "path", ["pyproject.toml", "uv.lock", "conftest.py", "testing/fixtures.py"]
)
def test_a_path_every_test_rests_on_selects_all(repo, path):
    head = repo.change([path], text="# changed\n")

    assert repo.selected(head) == ["all"]


def test_a_test_module_a_plugin_loads_for_every_test_selects_all(repo):
    head = repo.change(["tests/daemons.py"], text="# changed\n")

    assert repo.selected(head) == ["all"]


def test_a_test_module_only_a_fixture_uses_selects_the_tests_that_ask_for_the_fixture(repo):
    head = repo.change(["tests/test_kit.py"], text="# changed\n")

    assert repo.selected(head) == [
        "tests/test_kit.py",
        "tests/test_tree.py",
        "tests/test_uses_kit.py",
    ]


FEATURE = {
    "features/x/tests/test_feature.py": (
        "from alpha import a\nfrom helper import HELP\n\n\ndef test_it(shared):\n    pass\n"
    ),
}


@pytest.mark.parametrize(
    "path",
    ["src/alpha/util.py", "tests/helper.py", "tests/test_shared.py", *FEATURE],
)
def test_a_test_in_a_features_own_folder_is_selected_like_one_of_tests(repo, path):
    write(repo.root, FEATURE)
    repo.base = repo.commit()

    assert "features/x/tests/test_feature.py" in repo.selected(repo.change([path]))


def test_a_test_module_named_as_a_plugin_selects_the_tests_that_ask_for_its_fixture(repo):
    """A test that has a fixture of the same name of its own does not ask for the plugin's."""
    write(repo.root, FEATURE)
    repo.base = repo.commit()

    assert repo.selected(repo.change(["tests/test_shared.py"])) == [
        "features/x/tests/test_feature.py",
        "tests/test_shared.py",
        "tests/test_tree.py",
    ]


def test_a_fixture_selects_the_tests_that_name_it(repo):
    head = repo.change(["tests/fixtures/shapes/a.json"])

    assert repo.selected(head) == ["tests/test_shapes.py", "tests/test_tree.py"]


def test_a_fixture_no_test_names_selects_all(repo):
    head = repo.change(["tests/fixtures/orphan/x.json"])

    assert repo.selected(head) == ["all"]


def test_a_changed_test_selects_itself_and_each_test_that_imports_it_however_deep(repo):
    head = repo.change(["tests/test_helper.py"])

    assert repo.selected(head) == [
        "tests/test_helper.py",
        "tests/test_tree.py",
        "tests/test_user.py",
        "tests/test_user_of_user.py",
    ]


NESTED = {
    "tests/area/__init__.py": "",
    "tests/area/scene.py": "import alpha.util\n",
    "tests/area/conftest.py": "import pytest\n\n\n@pytest.fixture\ndef spot():\n    pass\n",
    "tests/area/test_area_one.py": "from area.scene import S\n",
    "tests/area/test_area_two.py": "def test_two(spot):\n    pass\n",
}


@pytest.mark.parametrize(
    ("path", "chosen"),
    [
        ("src/alpha/util.py", {"tests/area/test_area_one.py"}),
        ("tests/area/scene.py", {"tests/area/test_area_one.py"}),
        ("tests/area/conftest.py", {"tests/area/test_area_one.py", "tests/area/test_area_two.py"}),
        ("tests/area/test_area_two.py", {"tests/area/test_area_two.py"}),
    ],
)
def test_a_test_file_in_a_folder_of_tests_is_selected_by_its_imports_and_its_folders_conftest(
    repo, path, chosen
):
    write(repo.root, NESTED)
    repo.base = repo.commit()

    selected = repo.selected(repo.change([path]))

    assert {one for one in selected if one.startswith("tests/area/")} == chosen


def test_the_summary_counts_a_test_file_in_a_folder_of_tests(repo, tmp_path):
    write(repo.root, NESTED)
    repo.base = repo.commit()
    head = repo.change(["pyproject.toml"])
    flat = len(list((repo.root / "tests").glob("test_*.py")))

    _, lines = summary(repo, head, tmp_path)

    assert int(SUMMARY.fullmatch(lines[0])["of"]) == flat + 2


def test_a_deleted_test_is_not_named(repo):
    head = repo.change(["src/alpha/util.py"], gone=["tests/test_alpha.py"])

    assert repo.selected(head) == [
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


def test_a_moved_module_selects_the_tests_that_imported_it_from_where_it_was(repo):
    head = repo.change(moved=[("src/alpha/a.py", "lib/a.py")])

    assert repo.selected(head) == [
        "tests/test_alpha.py",
        "tests/test_glob.py",
        "tests/test_helped.py",
        "tests/test_tree.py",
    ]


def test_the_same_commits_give_the_same_lines(repo):
    head = repo.change(["src/alpha/a.py", "tests/test_helper.py", "src/beta/b.py"])

    assert repo.run(repo.base, head).stdout == repo.run(repo.base, head).stdout


@pytest.mark.parametrize(
    "path", ["src/alpha/a.py", "src/jbriefs/skills.py", "tests/test_helper.py", "docs/alpha.md"]
)
def test_a_bare_python_selects_what_the_venv_selects(repo, path):
    head = repo.change([path])
    script = repo.root / "scripts" / "select_tests.py"
    bare = subprocess.run(
        [sys.executable, "-I", "-S", script, repo.base, head],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    venv = subprocess.run(
        [sys.executable, script, repo.base, head], cwd=repo.root, capture_output=True, text=True
    )

    assert (bare.stderr, venv.stderr) == ("", "")
    assert bare.stdout == venv.stdout


def test_with_no_way_to_read_a_pattern_it_selects_all(repo):
    head = repo.change(["src/alpha/a.py"])
    shutil.rmtree(repo.root / "features" / "jmerge" / "src" / "jmerge")

    ran = repo.run(repo.base, head)

    assert ran.returncode == 0
    assert ran.stdout == "all\n"
    assert "nothing can be read" in ran.stderr


def test_a_matcher_whose_names_moved_selects_all(repo):
    head = repo.change(["src/alpha/a.py"])
    ready = repo.root / "features" / "jmerge" / "src" / "jmerge" / "ready.py"
    ready.write_text(ready.read_text().replace("def _protects(", "def _covers("))

    ran = repo.run(repo.base, head)

    assert ran.returncode == 0
    assert ran.stdout == "all\n"
    assert "ImportError" in ran.stderr


def test_a_module_that_does_not_parse_selects_all_and_names_it(repo):
    head = repo.change(["src/alpha/a.py"], text="def (\n")

    ran = repo.run(repo.base, head)

    assert ran.returncode == 0
    assert ran.stdout == "all\n"
    assert "src/alpha/a.py" in ran.stderr


def test_a_commit_git_does_not_know_fails_with_what_git_said(repo):
    ran = repo.run(repo.base, "no-such-commit")

    assert ran.returncode == 1
    assert ran.stderr.startswith("select_tests.py: git diff failed: ")


def whole(tmp_path):
    """A repo with the map, the tests, the plugins and the fixtures of this one."""
    map = REPO / select.MAP
    repo = Repo(tmp_path, {path.name: path.read_text() for path in map.glob("*.md")}, files={})
    shutil.copy2(REPO / "conftest.py", repo.put("conftest.py"))
    shutil.copy2(REPO / select.CROSS, repo.put(select.CROSS))
    for page in REPO.glob(f"features/*/{select.PAGE}"):
        shutil.copy2(page, repo.put(page.relative_to(REPO).as_posix()))
    tests = [*(REPO / "tests").rglob("*"), *REPO.glob("features/*/tests/**/*")]
    for test in [*tests, *(REPO / "testing").rglob("*.py")]:
        named = test.relative_to(REPO).as_posix()
        if test.is_file() and (select.FIXTURES.match(named) or test.suffix == ".py"):
            shutil.copy2(test, repo.put(named))
    repo.base = repo.commit()
    return repo


def test_a_change_to_the_view_selects_its_tests_but_not_the_browser_drive_of_its_page(tmp_path):
    repo = whole(tmp_path)

    head = repo.change(["features/jbus/src/jbus/view/page.html"])

    selected = repo.selected(head)
    assert "features/jbus/tests/view/test_view_server.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]
    assert set(select.cross_cutting()) <= set(selected)
    assert "features/jdrift/tests/test_drift.py" not in selected


@pytest.mark.parametrize("panel", ["bus", "checks", "words", "you"])
def test_a_change_to_a_panel_selects_the_tests_of_the_view_under_tests_view(panel, tmp_path):
    repo = whole(tmp_path)

    head = repo.change([f"features/jbus/src/jbus/view/panels/{panel}/panel.py"])

    selected = repo.selected(head)
    assert f"features/jbus/tests/view/test_view_{panel}.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]


SUMMARY = re.compile(
    r"check-fast selection=(?P<selection>all|some) files=(?P<files>\d+) of=(?P<of>\d+)"
    r" changed=(?P<changed>\d+) imports=(?P<imports>\d+) names=(?P<names>\d+)"
    r" features=(?P<features>\d+) cross-cutting=(?P<cross>\d+) forced-by=(?P<forced>\S+)"
)


def summary(repo, head, tmp_path):
    file = tmp_path / "summary.md"
    env = {"PATH": "/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(file)}
    ran = repo.run(repo.base, head, env=env)
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.splitlines(), file.read_text().strip().splitlines()


def test_the_selection_is_added_to_the_job_summary_as_a_line_a_collector_can_read(repo, tmp_path):
    head = repo.change(["src/alpha/util.py", "docs/alpha.md"])
    total = len(list((repo.root / "tests").glob("test_*.py")))

    printed, lines = summary(repo, head, tmp_path)

    assert len(lines) == 1
    found = SUMMARY.fullmatch(lines[0])
    assert found, lines[0]
    assert (found["selection"], int(found["files"]), int(found["of"])) == (
        "some",
        len(printed),
        total,
    )
    assert int(found["changed"]) == 2
    assert [found[key] for key in ("imports", "names", "features", "cross", "forced")] == [
        "2",
        "1",
        "1",
        "1",
        "-",
    ]


def test_an_all_says_which_path_forced_it(repo, tmp_path):
    head = repo.change(["pyproject.toml"])
    total = len(list((repo.root / "tests").glob("test_*.py")))

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    found = SUMMARY.fullmatch(lines[0])
    assert found, lines[0]
    assert (found["selection"], int(found["files"]), int(found["of"])) == ("all", total, total)
    assert found["forced"] == "pyproject.toml"


def test_an_unread_map_says_so_in_the_summary(repo, tmp_path):
    head = repo.change(["src/alpha/a.py"])
    shutil.rmtree(repo.root / "features" / "jmerge" / "src" / "jmerge")

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    assert SUMMARY.fullmatch(lines[0])["forced"] == "unread"


def test_a_list_holds_the_entries_under_its_label_up_to_the_next_label_or_a_blank_line():
    text = "Paths:\n- `src/a/`\n- `docs/a.md`\nTests: none\n\n- `src/b/`\n"

    assert select.listed(text, "Paths") == ["src/a/", "docs/a.md"]
    assert select.listed(text, "Tests") == []


@pytest.mark.parametrize("label", ["Paths", "Tests", "Cross-cutting"])
@pytest.mark.parametrize(
    "lines",
    [["{label}: `src/a/`, `src/b/`"], ["{label}:", "- `src/a/`, `src/b/`"]],
    ids=["on the label line", "on a list line"],
)
def test_a_line_that_holds_two_entries_is_refused(label, lines):
    text = "\n".join(line.format(label=label) for line in lines) + "\n"

    with pytest.raises(select.Unread, match=label):
        select.listed(text, label)


@pytest.mark.parametrize("line", ["* `src/b/`", "-`src/b/`", "  - `src/b/`", "src/b/"])
def test_a_list_line_that_is_not_an_entry_is_refused_and_does_not_end_the_list(line):
    text = f"Paths:\n- `src/a/`\n{line}\n- `src/c/`\n"

    with pytest.raises(select.Unread, match="not one entry"):
        select.listed(text, "Paths")


def test_a_map_line_with_two_entries_selects_all(tmp_path):
    two = ALPHA.replace("- `src/alpha/`\n- `docs/alpha.md`", "- `src/alpha/`, `docs/alpha.md`")
    repo = Repo(tmp_path, features={"README.md": README, "alpha.md": two, "beta.md": BETA})
    head = repo.change(["src/alpha/a.py"])

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    assert SUMMARY.fullmatch(lines[0])["forced"] == "unread"


def tracked(*paths):
    """The files git has or would add under `paths`."""
    listed = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", *paths)
    return listed.splitlines()


def test_every_path_is_owned_by_a_feature():
    owned = [paths for paths, _ in select.features().values()]

    assert [
        path
        for path in tracked(*OWNED, *ALSO)
        if not any(select.owns(patterns, path) for patterns in owned)
    ] == []


def test_every_root_the_ownership_test_reads_holds_a_file():
    """A move that empties a root folder drops it here too, or the ownership test reads a
    folder that is gone and names it as covered."""
    assert [root for root in (*OWNED, *ALSO) if not tracked(root)] == []


def test_every_test_file_the_map_names_is_there():
    named = [test for _, tests in select.features().values() for test in tests]

    missing = [test for test in [*named, *select.cross_cutting()] if not tracked(test)]
    assert missing == []


def test_every_feature_has_both_lines_and_patterns_jmerge_can_read():
    for name, page in select.pages().items():
        lines = (REPO / page).read_text().splitlines()
        for label in ("Paths:", "Tests:"):
            assert any(line.startswith(label) for line in lines), f"{name} has no {label}"
        paths = select.features()[name][0]
        assert paths, f"{name} has no Paths"
        assert select.ready().patterns_of("\n".join(paths)) == tuple(paths)


def test_a_features_tests_line_names_only_what_no_import_and_no_name_selects():
    """The tests of a feature come from what they import and what they name. A `Tests:` entry
    is the test that reads a feature's files with no string that shows it (a glob over a tree),
    so one that an import or a name already selects is a hand list the code makes needless."""
    shown = []
    for name, (owned, listed_tests) in select.features().items():
        mine = [one for one, path in select.modules().items() if owns_module(owned, path)]
        seen = select.test_files(select.importers(mine))
        for path in tracked():
            if select.owns(owned, path) and path not in select.modules().values():
                seen |= select.readers(path)
        shown += [f"{name} lists {test}" for test in listed_tests if test in seen]
    assert shown == []


def owns_module(owned, path):
    return path.startswith("src/") and select.owns(owned, path)


def test_every_test_file_is_run_by_a_change_to_something_or_is_cross_cutting():
    cross = set(select.cross_cutting())
    every = {path for path in tracked() if not path.startswith(".")} - {"conftest.py"}
    run = set(cross)
    for path in sorted(every):
        tests, _ = select.selection([path])
        run |= set(tests) - {"all"}
    left = [
        test
        for test in tracked("tests/", "features/")
        if select.TEST.fullmatch(test) and test not in run and not select.opens_browser(test)
    ]
    assert left == []


ORACLE = """
import builtins, importlib, json, sys
from pathlib import Path

tests, *folders = sys.argv[1:]
sys.path[:0] = [tests, *folders]
seen, failed = set(), []
real = builtins.__import__


def hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = real(name, globals, locals, fromlist, level)
    importer = (globals or {}).get("__name__")
    if importer and not level:
        seen.add((importer, name))
        seen.update((importer, f"{name}.{one}") for one in fromlist or ())
    return module


builtins.__import__ = hook
for path in sorted(Path(tests).rglob("*.py")):
    name = ".".join(path.relative_to(tests).with_suffix("").parts).removesuffix(".__init__")
    if name.startswith("fixtures."):
        continue
    try:
        importlib.import_module(name)
    except BaseException as error:
        failed.append(f"{name}: {error!r}")
print(json.dumps({"seen": sorted(seen), "failed": failed}))
"""


def test_the_import_graph_has_every_import_that_importing_the_tests_makes():
    ran = subprocess.run(
        [
            sys.executable,
            "-c",
            ORACLE,
            str(REPO / "tests"),
            *map(str, sorted(REPO.glob("features/*/tests"))),
            *map(str, sources()),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    found = json.loads(ran.stdout.splitlines()[-1])
    graph = select.edges()
    missing = [
        f"{importer} imports {name}"
        for importer, name in found["seen"]
        if importer in graph
        for reached in sorted(select.parents(name) & select.modules().keys())
        if reached != importer and reached not in graph[importer]
    ]
    assert (missing, found["failed"]) == ([], [])


BROWSER_MODULE = "import pytest\n\npytestmark = [pytest.mark.timeout(9), pytest.mark.browser]\n"
BROWSER_TEST = (
    "import beta.b\nimport pytest\n\n\n@pytest.mark.browser\ndef test_beta():\n    pass\n"
)


def test_a_test_module_marked_browser_is_not_selected_by_a_change_that_reaches_it(repo):
    write(repo.root, {"tests/test_alpha.py": BROWSER_MODULE + "from alpha import a\n"})
    repo.base = repo.commit()

    head = repo.change(["src/alpha/a.py"])
    assert "tests/test_alpha.py" not in repo.selected(head)
    repo.base = repo.commit_head()
    assert "tests/test_alpha.py" not in repo.selected(repo.change(["tests/test_alpha.py"]))


def test_a_test_module_that_imports_a_browser_module_is_still_selected(repo):
    write(repo.root, {"tests/test_helper.py": BROWSER_MODULE + "HELP = 1\n"})
    repo.base = repo.commit()

    selected = repo.selected(repo.change(["tests/test_helper.py"]))
    assert "tests/test_helper.py" not in selected
    assert "tests/test_user.py" in selected


def test_a_module_with_one_test_marked_is_selected_whole_and_make_leaves_that_test_out(repo):
    write(repo.root, {"tests/test_beta.py": BROWSER_TEST})
    repo.base = repo.commit()

    assert "tests/test_beta.py" in repo.selected(repo.change(["src/beta/b.py"]))


SMALL = {
    "conftest.py": "",
    "tests/test_tree.py": "def test_tree():\n    pass\n",
    **{f"tests/test_{name}.py": "def test_it():\n    pass\n" for name in "abcd"},
}


def outputs(repo, head, tmp_path):
    """What the selection printed, its summary line, and what it gave the step's outputs."""
    file, output = tmp_path / "summary.md", tmp_path / "output"
    env = {"PATH": "/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(file), "GITHUB_OUTPUT": str(output)}
    ran = repo.run(repo.base, head, env=env)
    assert ran.returncode == 0, ran.stderr
    given = dict(line.split("=", 1) for line in output.read_text().splitlines())
    return ran.stdout.splitlines(), SUMMARY.fullmatch(file.read_text().strip()), given


def test_a_selection_of_four_fifths_of_the_test_files_or_more_is_the_whole_suite(tmp_path):
    """Five test files: three changed and the cross-cutting one are four of them, 80%."""
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert printed == ["all"]
    assert (line["selection"], line["files"], line["of"], line["forced"]) == (
        "all",
        "5",
        "5",
        "share",
    )
    assert given == {"selection": "all"}


def test_a_selection_under_four_fifths_runs_only_what_it_selected(tmp_path):
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["tests/test_a.py", "tests/test_b.py"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert printed == ["tests/test_a.py", "tests/test_b.py", "tests/test_tree.py"]
    assert (line["selection"], line["files"], line["forced"]) == ("some", "3", "-")
    assert given == {"selection": "some"}


def test_a_path_that_forces_all_says_all_to_the_steps_outputs(repo, tmp_path):
    head = repo.change(["pyproject.toml"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert (printed, line["forced"], given) == (["all"], "pyproject.toml", {"selection": "all"})
