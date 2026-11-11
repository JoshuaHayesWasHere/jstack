"""`scripts/select_tests.py <base> <head>` names the test files a diff needs, from what the
tests import and name, and from the map in verify-jstack's `features/`.

The test runs the script as CI runs it, with `python3 -I -S`, so it imports nothing installed.
It runs it in a temporary git repo that holds a copy of the script, a copy of the packages
the script imports from this checkout to read the map's patterns, and a few modules, docs and
tests of its own: the folders its `READ_SET` names, so a change runs these tests only where it
reaches the selector. The tests that run the selector on this repo's own tree, its table of
rules and the map's tests, are in test_select_tests_rules.py, which every change runs, and the
rules' mutants in test_select_tests_mutants.py."""

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from testing.paths import REPO, sources

SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)
READ_SET = ("features/jbriefs/src/", "features/jmerge/src/", "features/jsettings/src/")

README = """\
# A map

Cross-cutting:
- `testing/tests/test_tree.py`
"""
ALPHA = """\
# Alpha

What alpha does.

Paths:
- `src/alpha/`
- `docs/alpha.md`
Tests:
- `testing/tests/test_glob.py`
"""
BETA = """\
# Beta

What beta does.

Paths:
- `src/beta/*.py`
Tests: none
"""
KIT = """\
# Kit

The tests of this repo that only a change to themselves would select, listed so a rule owns each.

Paths:
- `kit/`
Tests:
- `testing/tests/test_helper.py`
- `testing/tests/test_kit.py`
- `testing/tests/test_own_shared.py`
- `testing/tests/test_shared.py`
"""
FILES = {
    f"{select.MAP}/kit.md": KIT,
    "src/alpha/__init__.py": "",
    "src/alpha/a.py": "from alpha import util\n",
    "src/alpha/util.py": "X = 1\n",
    "src/alpha/notes.txt": "notes\n",
    "src/beta/__init__.py": "",
    "src/beta/b.py": "import importlib\n\nimportlib.import_module('beta.plug')\n",
    "src/beta/plug.py": "P = 1\n",
    "src/gamma/__init__.py": "",
    "src/gamma/g.py": "G = 1\n",
    "testing/tests/test_runs_gamma.py": (
        "import subprocess\n\nsubprocess.run(['python', '-m', 'gamma'])\n"
    ),
    "testing/tests/helper_data.py": "ROWS = 1\n",
    "testing/tests/test_reads_helper.py": "H = Path('testing') / 'tests' / 'helper_data.py'\n",
    "docs/alpha.md": "# alpha\n",
    "skills/one/SKILL.md": "one\n",
    "skills/two/SKILL.md": "two\n",
    "testing/tests/fixtures/shapes/a.json": "{}\n",
    "testing/tests/fixtures/shapes/b.json": "{}\n",
    "testing/tests/fixtures/orphan/x.json": "{}\n",
    "README.md": "#\n",
    "conftest.py": 'pytest_plugins = ["testing.fixtures", "test_shared"]\n',
    "testing/__init__.py": "",
    "testing/fixtures.py": (
        "import pytest\n\nimport daemons\nfrom test_kit import Kit\n\n"
        "tidy = daemons.tidy\n\n\n@pytest.fixture\ndef kit():\n    return Kit()\n"
    ),
    "testing/tests/test_shared.py": (
        "import pytest\n\n\n@pytest.fixture\ndef shared():\n    pass\n\n\n"
        "def test_shared():\n    pass\n"
    ),
    "testing/tests/test_own_shared.py": (
        "import pytest\n\n\n@pytest.fixture\ndef shared():\n    pass\n\n\n"
        "def test_it(shared):\n    pass\n"
    ),
    "testing/tests/daemons.py": "def tidy():\n    pass\n",
    "testing/tests/test_kit.py": "class Kit:\n    pass\n",
    "testing/tests/test_uses_kit.py": "def test_it(kit):\n    pass\n",
    "testing/tests/test_tree.py": "def test_tree():\n    pass\n",
    "testing/tests/test_alpha.py": "from alpha import a\n",
    "testing/tests/test_beta.py": "import beta.b\n",
    "testing/tests/helper.py": "import alpha.util\n",
    "testing/tests/test_helped.py": "from helper import HELP\n",
    "testing/tests/test_glob.py": "def test_glob():\n    pass\n",
    "testing/tests/test_doc.py": "from pathlib import Path\n\nDOC = Path('docs') / 'alpha.md'\n",
    "testing/tests/test_one.py": (
        "from pathlib import Path\n\nS = Path('skills') / 'one' / 'SKILL.md'\n"
    ),
    "testing/tests/test_two.py": "SKILL = 'skills/two/SKILL.md'\n",
    "testing/tests/test_shapes.py": "S = Path('testing') / 'tests' / 'fixtures' / 'shapes'\n",
    "testing/tests/test_helper.py": "HELP = 1\n",
    "testing/tests/test_user.py": "def use():\n    from test_helper import HELP\n",
    "testing/tests/test_user_of_user.py": "import test_user\n",
}


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def write(repo, files):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)


LOADS = """
import sys
sys.path[:0] = sys.argv[1:]
import jmerge.ready
for one in list(sys.modules.values()):
    print(getattr(one, "__file__", None) or "")
"""


@cache
def packages():
    """The folders of packages that importing jmerge's reader of patterns loads, as
    `select_tests.py`'s `ready()` imports it: the only code of this checkout the script runs.
    A copy of every folder would have the script parse each of this repo's modules on each run,
    about 2 s of a core for every test that runs it."""
    ran = subprocess.run(
        [sys.executable, "-I", "-S", "-c", LOADS, *map(str, sources())],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = [Path(one) for one in ran.stdout.splitlines() if one]
    return [folder for folder in sources() if any(one.is_relative_to(folder) for one in loaded)]


class Repo:
    """A repo with the script, a copy of the folders of packages it imports, a map and a few
    modules and tests."""

    def __init__(self, root, features=None, files=None, facts=True):
        """`facts` starts the repo with the script's kept facts of a repo of `FILES` (`kept()`),
        as a run on a developer's checkout starts from the last run's."""
        self.root = root
        shutil.copy2(SCRIPT, self.put("scripts/select_tests.py"))
        for folder in packages():
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
        if facts:
            (root / ".git" / select.KEPT).write_bytes(kept())
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
        """Write `files`, delete `gone`, move each pair of `moved`, and return the new head."""
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


@cache
def kept():
    """The facts (`select.KEPT`) one run of this checkout's script keeps in a repo of `FILES`.
    Without them each test's first run parses every module of the copied packages, about 0.1 s
    of a core. They are kept under a hash of the script, jmerge's reader of patterns, the Python
    and the repo's skills, and by the hash of each module's text, so a test whose script, skills
    or modules differ parses afresh what differs, as a run on a developer's checkout does."""
    with tempfile.TemporaryDirectory() as held:
        repo = Repo(Path(held), facts=False)
        repo.selected(repo.change(["src/alpha/util.py"]))
        return (repo.root / ".git" / select.KEPT).read_bytes()


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_the_read_set_names_every_folder_of_packages_a_repo_copies():
    """A change to a package the copy holds selects these tests through the `READ_SET`. An import
    jmerge's reader of patterns gains copies one more folder, and it must join the read set."""
    assert {f"{folder.relative_to(REPO).as_posix()}/" for folder in packages()} == set(READ_SET)


def test_a_changed_module_selects_each_test_that_imports_it_directly_or_by_a_chain(repo):
    head = repo.change(["src/alpha/util.py"])

    assert repo.selected(head) == [
        "testing/tests/test_alpha.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
    ]


MOVED = {
    "features/delta/src/delta/__init__.py": "",
    "features/delta/src/delta/d.py": "from delta import util\n\nROWS = 'rows.txt'\n",
    "features/delta/src/delta/util.py": "U = 1\n",
    "features/delta/src/delta/rows.txt": "rows\n",
    "features/delta/tests/test_delta.py": "from delta import d\n",
    "testing/tests/test_runs_delta.py": (
        "import subprocess\n\nsubprocess.run(['python', '-m', 'delta'])\n"
    ),
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

    assert {"features/delta/tests/test_delta.py", "testing/tests/test_runs_delta.py"} <= set(
        selected
    )
    assert "testing/tests/test_alpha.py" not in selected


def test_a_module_imported_by_name_is_imported_by_the_module_that_imports_by_name(repo):
    head = repo.change(["src/beta/plug.py"])

    assert repo.selected(head) == ["testing/tests/test_beta.py", "testing/tests/test_tree.py"]


LOADER = {
    "src/reg/__init__.py": "",
    "src/reg/kinds.py": (
        "import importlib\n\n\nclass Kind:\n    pass\n\n\n"
        "def found():\n    return importlib.import_module('reg.plug')\n"
    ),
    "src/reg/plug.py": "P = 1\n",
    "src/reg/run.py": "from reg import kinds\n\nFOUND = kinds.found()\n",
    "testing/tests/test_kind.py": "from reg.kinds import Kind\n",
    "testing/tests/test_run.py": "import reg.run\n",
    "testing/tests/test_calls.py": "from reg.kinds import found\n\n\ndef test_it():\n    found()\n",
    "testing/tests/test_typed.py": (
        "from typing import TYPE_CHECKING\n\nfrom reg.kinds import Kind\n\n"
        "if TYPE_CHECKING:\n    from reg.plug import P\n"
    ),
}


def test_a_module_imported_by_name_in_a_function_is_imported_only_where_that_function_is_called(
    tmp_path,
):
    """`reg.kinds` imports `reg.plug` by name only inside `found`. A test that imports `Kind` from
    it never runs `found`, so a change to `reg.plug` does not reach it. A test that calls `found`,
    or imports a module that calls it on import, does run it."""
    repo = Repo(tmp_path, files={**FILES, **LOADER})
    head = repo.change(["src/reg/plug.py"])

    selected = repo.selected(head)

    assert {"testing/tests/test_run.py", "testing/tests/test_calls.py"} <= set(selected)
    assert "testing/tests/test_kind.py" not in selected


HELD = {
    "src/reg/later.py": (
        "from functools import partial\n\nfrom reg import kinds\n\nLATER = partial(kinds.found)\n"
    ),
    "src/reg/lookup.py": (
        "import reg.kinds\n\n\ndef get():\n    return getattr(reg.kinds, 'found')()\n"
    ),
    "src/reg/table.py": (
        "import importlib\n\n\nclass Table:\n"
        "    def load(self):\n        return importlib.import_module('reg.plug')\n"
    ),
    "src/reg/menu.py": (
        "import importlib\n\nTITLE = 'menu'\n\n\n"
        "def load():\n    return importlib.import_module('reg.plug')\n\n\nMENU = (load,)\n"
    ),
    "src/reg/mapped.py": (
        "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n\n\n"
        "list(map(load, ['reg.plug']))\n"
    ),
    "src/reg/wraps.py": (
        "import importlib\n\n\ndef plugged(f):\n    importlib.import_module('reg.plug')\n"
        "    return f\n\n\n@plugged\ndef thing():\n    pass\n"
    ),
    "src/reg/hooks.py": (
        "import importlib\n\nHOOKS = []\n\n\ndef hook(f):\n    HOOKS.append(f)\n    return f\n\n\n"
        "@hook\ndef load():\n    return importlib.import_module('reg.plug')\n"
    ),
    "testing/tests/test_later.py": "import reg.later\n",
    "testing/tests/test_mapped.py": "import reg.mapped\n",
    "testing/tests/test_wraps.py": "import reg.wraps\n",
    "testing/tests/test_hooks.py": "import reg.hooks\n",
    "testing/tests/test_menu.py": "from reg.menu import MENU\n\n\ndef test_it():\n    MENU[0]()\n",
    "testing/tests/test_title.py": "from reg.menu import TITLE\n\n\ndef test_it():\n    TITLE\n",
    "src/reg/verbs.py": (
        "import importlib\nfrom dataclasses import dataclass\n\nTITLE = 'verbs'\n\n\n"
        "@dataclass\nclass Verb:\n    name: str\n    run: object\n\n\n"
        "def load():\n    return importlib.import_module('reg.plug')\n\n\n"
        "VERBS = (Verb('load', load),)\n"
    ),
    "testing/tests/test_lookup.py": "import reg.lookup\n",
    "testing/tests/test_table.py": "from reg.table import Table\n",
    "testing/tests/test_verbs.py": (
        "from reg.verbs import VERBS\n\n\ndef test_it():\n    VERBS[0].run()\n"
    ),
    "testing/tests/test_verb_title.py": (
        "from reg.verbs import TITLE\n\n\ndef test_it():\n    TITLE\n"
    ),
}


@pytest.mark.parametrize(
    "test",
    [
        "test_later.py",
        "test_lookup.py",
        "test_table.py",
        "test_menu.py",
        "test_mapped.py",
        "test_wraps.py",
        "test_hooks.py",
        "test_verbs.py",
    ],
)
def test_a_function_that_imports_by_name_reaches_the_tests_that_may_call_it_however_they_name_it(
    tmp_path, test
):
    """A function named but not called, as `partial(kinds.found)` holds it; one named by a string
    to `getattr`; a method, which an object calls where no import names it; a registry that
    holds one, `MENU = (load,)`, whose reader may call it; one passed to `map` on import; a
    decorator that imports by name; and one a decorator may register: each may run."""
    repo = Repo(tmp_path, files={**FILES, **LOADER, **HELD})
    head = repo.change(["src/reg/plug.py"])

    assert f"testing/tests/{test}" in repo.selected(head)


@pytest.mark.parametrize("test", ["test_title.py", "test_verb_title.py"])
def test_a_registry_that_holds_a_function_that_imports_by_name_reaches_only_its_readers(
    tmp_path, test
):
    """`MENU = (load,)` and `VERBS = (Verb('load', load),)` only hold `load`: building a dataclass
    of the module stores its arguments and runs none of them."""
    repo = Repo(tmp_path, files={**FILES, **LOADER, **HELD})
    head = repo.change(["src/reg/plug.py"])

    assert f"testing/tests/{test}" not in repo.selected(head)


EXPORTED = {
    "re-export": (
        "from reg.kinds import found\n",
        "from reg import found\n\n\ndef test_it():\n    found()\n",
    ),
    "star": ("", "from reg.kinds import *\n\n\ndef test_it():\n    found()\n"),
    "star re-export": (
        "from reg.kinds import *\n",
        "import reg\n\n\ndef test_it():\n    reg.found()\n",
    ),
}


@pytest.mark.parametrize("way", EXPORTED)
def test_a_function_that_imports_by_name_reaches_the_tests_that_call_it_through_a_re_export(
    tmp_path, way
):
    """A package that re-exports `found`, by name or with a star, and a test that star-imports
    it, each reach the module that defines it, so a change to what `found` loads selects the
    test that calls it there, and not one that only imports the package."""
    package, test = EXPORTED[way]
    files = {
        **FILES,
        **LOADER,
        "src/reg/__init__.py": package,
        "testing/tests/test_exported.py": test,
        "testing/tests/test_package.py": "import reg\n",
    }
    repo = Repo(tmp_path, files=files)
    head = repo.change(["src/reg/plug.py"])

    selected = repo.selected(head)

    assert "testing/tests/test_exported.py" in selected
    assert "testing/tests/test_package.py" not in selected


def test_a_test_that_imports_a_module_by_its_name_in_a_string_is_selected_by_a_change_to_it(
    tmp_path,
):
    named = "import importlib\n\n\ndef test_it():\n    importlib.import_module('gamma.g')\n"
    repo = Repo(tmp_path, files={**FILES, "testing/tests/test_named.py": named})
    head = repo.change(["src/gamma/g.py"])

    assert "testing/tests/test_named.py" in repo.selected(head)


def test_an_import_only_a_type_checker_reads_selects_nothing(tmp_path):
    repo = Repo(tmp_path, files={**FILES, **LOADER})
    head = repo.change(["src/reg/plug.py"])

    assert "testing/tests/test_typed.py" not in repo.selected(head)


FOLDERS = {
    "testing/tests/test_gamma_dir.py": (
        "from pathlib import Path\n\nimport alpha.util\n\n"
        "CONFIG = Path.home() / '.config' / 'gamma'\n"
    ),
    "testing/tests/test_gamma_bin.py": (
        "import sys\nfrom pathlib import Path\n\nimport alpha.util\n\n"
        "RUN = Path(sys.executable).parent / 'gamma'\nLOCAL = Path.home() / 'bin' / 'gamma'\n"
    ),
}


def test_a_package_named_as_a_folder_of_a_path_is_not_run(tmp_path):
    """`~/.config/gamma` names a folder, so the test does not run `gamma`. A path that ends in
    `gamma` after `bin`, or after a folder no string names, may be the command, and the test that
    spells it still runs."""
    repo = Repo(tmp_path, files={**FILES, **FOLDERS})
    head = repo.change(["src/gamma/g.py"])

    selected = repo.selected(head)

    assert "testing/tests/test_gamma_bin.py" in selected
    assert "testing/tests/test_gamma_dir.py" not in selected


def test_a_test_that_runs_a_package_in_a_process_of_its_own_is_selected_by_a_change_to_it(repo):
    head = repo.change(["src/gamma/g.py"])

    assert repo.selected(head) == ["testing/tests/test_runs_gamma.py", "testing/tests/test_tree.py"]


PAGED = {
    "src/verbs/__init__.py": "",
    "src/verbs/needs.py": "HELP = 'what waits on you'\n",
    "src/verbs/pages.py": "import verbs\n\nPATHS = verbs.__path__\n",
    "testing/tests/test_pages.py": "from verbs import pages\n",
    "testing/tests/test_package.py": "import verbs\n",
}


def test_a_module_that_reads_its_package_by_its_path_selects_its_tests_on_a_change_to_any_module(
    tmp_path,
):
    """`verbs.pages` builds a page from the source of each module under `verbs.__path__`, and
    imports none of them, as `jbus.pages` builds the-verbs.md from each verb's help. A change to
    a verb's help selects the tests of the page, and not a test that imports the package alone."""
    repo = Repo(tmp_path, files={**FILES, **PAGED})

    assert repo.selected(repo.change(["src/verbs/needs.py"])) == [
        "testing/tests/test_pages.py",
        "testing/tests/test_tree.py",
    ]


def test_a_changed_test_module_selects_the_tests_that_spell_its_path(repo):
    head = repo.change(["testing/tests/helper_data.py"])

    assert "testing/tests/test_reads_helper.py" in repo.selected(head)


def test_a_file_in_a_package_that_is_no_module_selects_the_tests_of_the_modules_beside_it(repo):
    head = repo.change(["src/alpha/notes.txt"])

    assert repo.selected(head) == [
        "testing/tests/test_alpha.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
    ]


def test_a_doc_selects_the_tests_that_name_it_and_the_tests_its_feature_lists(repo):
    head = repo.change(["docs/alpha.md"])

    assert repo.selected(head) == [
        "testing/tests/test_doc.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_tree.py",
    ]


def test_a_skill_selects_the_tests_that_name_its_directory_and_not_the_other_skills(repo):
    assert repo.selected(repo.change(["skills/one/SKILL.md"])) == [
        "testing/tests/test_one.py",
        "testing/tests/test_tree.py",
    ]
    repo.base = repo.commit_head()
    assert repo.selected(repo.change(["skills/two/SKILL.md"])) == [
        "testing/tests/test_tree.py",
        "testing/tests/test_two.py",
    ]


INCLUDED = {
    "skills/three/SKILL.md": "First read `$T/../skills/three/part.md` now.\n",
    "skills/three/part.md": "Then read `$T/../skills/three/deep.md` now.\n",
    "skills/three/deep.md": "deep\n",
    "skills/three/alone.md": "alone\n",
    "testing/tests/test_three.py": "S = Path('skills') / 'three' / 'SKILL.md'\n",
}


@pytest.mark.parametrize("path", ["skills/three/part.md", "skills/three/deep.md"])
def test_a_file_a_skill_includes_selects_the_tests_that_read_the_skill_however_deep(tmp_path, path):
    repo = Repo(tmp_path, files={**FILES, **INCLUDED})

    assert repo.selected(repo.change([path])) == [
        "testing/tests/test_three.py",
        "testing/tests/test_tree.py",
    ]


def test_a_file_beside_a_skill_that_no_line_includes_selects_as_before(tmp_path):
    repo = Repo(tmp_path, files={**FILES, **INCLUDED})

    assert repo.selected(repo.change(["skills/three/alone.md"])) == ["testing/tests/test_tree.py"]


BLOCKS = {
    "skills/three/SKILL.md": "First read `$T/../skills/three/part.md` now.\n",
    "skills/three/part.md": "part\n",
    "testing/tests/reader.py": (
        "from testing.paths import skills\n\n\n"
        "def block(skill):\n    return (skills()[skill] / 'SKILL.md').read_text()\n"
    ),
    "testing/tests/test_block.py": "from reader import block\n\nB = block('three')\n",
    "testing/tests/test_names_three.py": "from alpha import a\n\nWORD = 'three'\n",
}


@pytest.mark.parametrize("path", ["skills/three/SKILL.md", "skills/three/part.md"])
def test_a_skill_selects_the_tests_that_read_it_by_its_name_through_the_index_of_skills(
    tmp_path, path
):
    """`test_block.py` spells no path of the skill: it names the skill, and the module it imports
    reads the skill's `SKILL.md` through `testing.paths.skills()`. `test_names_three.py` names the
    skill too, but reads no skill, so it is not selected: its import of `alpha` keeps it out of
    the catch-all."""
    repo = Repo(tmp_path, files={**FILES, **BLOCKS})

    assert repo.selected(repo.change([path])) == [
        "testing/tests/test_block.py",
        "testing/tests/test_tree.py",
    ]


HELPERS = {
    **BLOCKS,
    "testing/tests/reader.py": (
        "from testing.paths import skills\n\nREADERS = ['three']\n\n\n"
        "def block(skill):\n    return (skills()[skill] / 'SKILL.md').read_text()\n\n\n"
        "def readers():\n    return [block(one) for one in READERS]\n\n\n"
        "def plain():\n    return 1\n"
    ),
    "testing/tests/test_block.py": "from reader import block\n\nB = block('four')\n",
    "testing/tests/test_readers.py": "import reader\n\nR = reader.readers()\n",
    "testing/tests/test_plain.py": "from alpha import a\nfrom reader import plain\n",
}


def test_a_skill_selects_a_test_by_the_skills_it_reaches_and_not_by_the_names_beside_them(
    tmp_path,
):
    """`reader.py` names the skill `three` in `READERS`, which only `readers()` reads.
    `test_readers.py` calls `readers()`, so it reads the skill. `test_block.py` reads the skill
    `four` through the same module, and `test_plain.py` calls a helper of it that reads no skill:
    neither reaches `three`, so a change to it selects neither."""
    repo = Repo(tmp_path, files={**FILES, **HELPERS})

    assert repo.selected(repo.change(["skills/three/SKILL.md"])) == [
        "testing/tests/test_readers.py",
        "testing/tests/test_tree.py",
    ]


def test_a_file_no_feature_owns_and_no_test_names_selects_the_cross_cutting_alone(repo):
    head = repo.change(["README.md"])

    assert repo.selected(head) == ["testing/tests/test_tree.py"]


LONE = {"testing/tests/test_lone.py": "def test_lone():\n    assert True\n"}


def test_a_test_no_rule_selects_runs_on_a_change_that_selects_only_the_cross_cutting(tmp_path):
    """`test_lone.py` imports nothing, spells no path and is on no list, so a change to any other
    path selects it by no rule. The catch-all runs it on every change, as it runs the
    cross-cutting tests."""
    repo = Repo(tmp_path, files={**FILES, **LONE})

    assert repo.selected(repo.change(["README.md"])) == [
        "testing/tests/test_lone.py",
        "testing/tests/test_tree.py",
    ]


def test_a_test_no_rule_selects_runs_beside_what_a_change_selects(tmp_path):
    repo = Repo(tmp_path, files={**FILES, **LONE})

    assert repo.selected(repo.change(["src/beta/plug.py"])) == [
        "testing/tests/test_beta.py",
        "testing/tests/test_lone.py",
        "testing/tests/test_tree.py",
    ]


@pytest.mark.parametrize(
    ("changed", "guards", "rest"),
    [
        (["src/beta/plug.py"], ["test_lone.py", "test_tree.py"], ["test_beta.py"]),
        (
            ["src/beta/plug.py", "testing/tests/test_beta.py"],
            ["test_beta.py", "test_lone.py", "test_tree.py"],
            [],
        ),
    ],
    ids=["a module", "a module and its test"],
)
def test_the_guards_are_the_cross_cutting_the_catch_all_and_the_changed_tests(
    tmp_path, changed, guards, rest
):
    """`--part guards` and `--part rest` split the selection, and the guards are the
    cross-cutting tests, the catch-all and the changed test files, never a file the change
    reaches by an import alone."""
    repo = Repo(tmp_path, files={**FILES, **LONE})
    head = repo.change(changed)
    parts = [repo.run("--part", part, repo.base, head) for part in ("guards", "rest")]

    assert [ran.returncode for ran in parts] == [0, 0], [ran.stderr for ran in parts]
    said = [ran.stdout.split() for ran in parts]
    assert said == [[f"testing/tests/{one}" for one in names] for names in (guards, rest)]
    assert sorted(said[0] + said[1]) == repo.selected(head)


@pytest.mark.parametrize(
    ("changed", "guards"),
    [
        (["pyproject.toml"], ["test_lone.py", "test_tree.py"]),
        (
            ["pyproject.toml", "testing/tests/test_beta.py"],
            ["test_beta.py", "test_lone.py", "test_tree.py"],
        ),
    ],
    ids=["a shared file", "a shared file and a test"],
)
def test_the_guards_of_a_selection_of_every_test_are_still_the_guards(tmp_path, changed, guards):
    """A change that selects every test, as a deleted fixture or a change to select_tests.py
    does, still gives the cross-cutting tests, the catch-all and the changed test files as its
    guards, never `all`: the whole suite ran 9 to 10 min on jmerge's merged trees, past the
    guards' 600 s, and held the merge line on 2026-11-05 (#1103, #1118). The rest is `all`."""
    repo = Repo(tmp_path, files={**FILES, **LONE})
    head = repo.change(changed)

    assert repo.selected(head) == ["all"]
    said = [repo.run("--part", part, repo.base, head).stdout.split() for part in ("guards", "rest")]
    assert said == [[f"testing/tests/{one}" for one in guards], ["all"]]


FAR = "features/far/tests/test_far.py"


@pytest.mark.parametrize(
    "changed",
    [["src/beta/plug.py", "testing/tests/test_beta.py"], ["pyproject.toml"]],
    ids=["a module and its test", "a shared file"],
)
def test_the_cross_part_is_the_cross_cutting_tests_of_the_selection(tmp_path, changed):
    """`--part cross` prints the cross-cutting tests the selection names, wherever their files
    live, and neither the catch-all (`test_lone.py`) nor a test the change reaches or edits
    (`test_beta.py`): the desk runs each of them alone, and CI runs the rest. A selection of
    every test gives them all the same, never `all`."""
    features = {
        "README.md": f"{README}- `{FAR}`\n",
        "alpha.md": ALPHA,
        "beta.md": BETA,
    }
    repo = Repo(
        tmp_path, features=features, files={**FILES, **LONE, FAR: "def test_far():\n    pass\n"}
    )
    head = repo.change(changed)
    ran = repo.run("--part", "cross", repo.base, head)

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.split() == [FAR, "testing/tests/test_tree.py"]


READER = "features/jbus/tests/test_status_line_readers.py"


def test_the_names_part_of_an_edit_of_a_skill_file_prints_the_test_that_reads_it(tmp_path):
    """#1691 edited features/crew/no-pr-end.md, and its pull request's check failed twice on
    test_status_line_readers.py, which reads that file and which neither `--part touched` nor
    `--part cross` printed, so the desk never ran it. `--part names` prints it: the desk's check
    runs each test the pull request's check selects because it names a file the change edits."""
    files = {
        **FILES,
        "features/crew/no-pr-end.md": (REPO / "features/crew/no-pr-end.md").read_text(),
        READER: (REPO / READER).read_text(),
    }
    repo = Repo(tmp_path, files=files)
    head = repo.change(["features/crew/no-pr-end.md"])
    ran = repo.run("--part", "names", repo.base, head)

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.split() == [READER]
    assert READER in repo.run("--pull-request", repo.base, head).stdout.split()


@pytest.mark.parametrize(
    ("took", "steps"),
    [
        ({}, ["testing/tests/test_doc.py testing/tests/test_one.py"]),
        (
            {"testing/tests/test_doc.py::test_doc": 50, "testing/tests/test_one.py::test_one": 50},
            ["testing/tests/test_doc.py", "testing/tests/test_one.py"],
        ),
    ],
    ids=["quick files share a step", "files that fill a step each take one"],
)
def test_the_names_part_prints_the_tests_that_name_a_changed_file_less_the_desks_others(
    tmp_path, took, steps
):
    """`--part names` prints, of the pull request's selection, the test files a change selects
    because they name or read a file it edits, less the ones `--part touched` and `--part cross`
    print: each file is one step of the desk's check. Not the tests a feature lists
    (`test_glob.py`) or that import a changed module (`test_alpha.py`): CI runs them. It packs
    the files, in order, into steps of `STEP` seconds of test time at most, one step a line, by
    the file table, so a step fits the short lane and pays pytest's start once."""
    files = {
        **FILES,
        "testing/split.py": (REPO / "testing" / "split.py").read_text(),
        "testing/shard-file-times.tsv": timed(took),
    }
    repo = Repo(tmp_path, files=files)
    head = repo.change(
        ["docs/alpha.md", "skills/one/SKILL.md", "src/alpha/util.py", "testing/tests/test_two.py"]
    )
    ran = repo.run("--part", "names", repo.base, head)

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines() == steps
    printed = {
        one for part in ("touched", "cross", "names")
        for one in repo.run("--part", part, repo.base, head).stdout.split()
    }
    named = {"testing/tests/test_doc.py", "testing/tests/test_one.py", "testing/tests/test_two.py"}
    assert named <= printed
    assert not printed & {"testing/tests/test_glob.py", "testing/tests/test_alpha.py"}


TEE = """\
# Tee

What tee does.

Paths:
- `a/`
Tests:
- `testing/tests/test_t.py`
"""
GLOBBED = {
    "conftest.py": "",
    "a/x.py": "X = 1\n",
    "b/x.md": "fine\n",
    "c/y.md": "fine\n",
    "testing/tests/test_t.py": (
        "from pathlib import Path\n\nREAD_SET = ('b/*.md',)\n\n\n"
        "def test_t():\n"
        "    assert all('broken' not in one.read_text() for one in Path('b').glob('*.md'))\n"
    ),
    "testing/tests/globbing.py": (
        "from pathlib import Path\n\nREAD_SET = ('c/',)\n\n\n"
        "def texts():\n    return [one.read_text() for one in Path('c').rglob('*.md')]\n"
    ),
    "testing/tests/test_u.py": "from globbing import texts\n",
}


@pytest.fixture
def globbed(tmp_path):
    return Repo(tmp_path, features={"README.md": README, "tee.md": TEE}, files=GLOBBED)


def test_a_test_owned_for_another_path_runs_when_a_file_its_glob_reads_changes(globbed):
    """A rule owns `test_t.py` for `a/`, so the catch-all leaves it out, and it spells no path
    of `b/`. It reads `b/*.md` through a glob and declares so in its `READ_SET`, and a change to
    `b/x.md` that breaks it selects it."""
    head = globbed.change(["b/x.md"], text="broken\n")
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "testing/tests/test_t.py"],
        cwd=globbed.root,
        capture_output=True,
        text=True,
    )

    assert ran.returncode == 1, ran.stdout
    assert globbed.selected(head) == ["testing/tests/test_t.py"]


def test_a_read_set_of_a_module_of_the_tests_selects_the_tests_that_import_it(globbed):
    head = globbed.change(["c/y.md"])

    assert globbed.selected(head) == ["testing/tests/test_u.py"]


def test_a_star_stays_within_one_part_of_the_path(repo):
    head = repo.change(["docs/other/alpha.md"])

    assert repo.selected(head) == ["testing/tests/test_tree.py"]


def test_an_edit_to_a_feature_file_selects_that_features_tests_and_not_all(repo):
    head = repo.change([f"{select.MAP}/alpha.md"])

    assert repo.selected(head) == [
        "testing/tests/test_alpha.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
    ]


@pytest.fixture
def paged(tmp_path):
    """The repo with alpha's page moved into its feature's folder, as `verify.md`."""
    features = {"README.md": README, "beta.md": BETA}
    return Repo(tmp_path, features, files={**FILES, "features/alpha/verify.md": ALPHA})


def test_a_page_in_its_features_folder_selects_its_tests_for_a_path_it_owns(paged):
    head = paged.change(["docs/alpha.md"])

    assert paged.selected(head) == [
        "testing/tests/test_doc.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_tree.py",
    ]


def test_an_edit_to_a_page_in_its_features_folder_selects_that_features_tests(paged):
    head = paged.change(["features/alpha/verify.md"])

    assert paged.selected(head) == [
        "testing/tests/test_alpha.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
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

    assert repo.selected(head) == ["testing/tests/test_tree.py"]


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock", "conftest.py"])
def test_a_path_every_test_rests_on_selects_all(repo, path):
    head = repo.change([path], text="# changed\n")

    assert repo.selected(head) == ["all"]


BUILD = {
    "Makefile": "test:\n",
    ".github/workflows/check.yml": "on: pull_request\n",
    "testing/tests/test_build.py": (
        "from pathlib import Path\n\n"
        "MAKE = Path('Makefile')\n"
        "CHECK = Path('.github') / 'workflows' / 'check.yml'\n"
        "SELECTOR = Path('scripts') / 'select_tests.py'\n"
    ),
}


@pytest.mark.parametrize(
    "path", ["scripts/select_tests.py", "Makefile", ".github/workflows/check.yml"]
)
def test_a_change_to_what_picks_and_runs_the_tests_selects_the_tests_that_name_it(repo, path):
    """A pull request's check runs the whole suite only where a dependency or the root
    conftest.py changed: the whole suite runs on main, nightly and before a release."""
    write(repo.root, BUILD)
    repo.base = repo.commit()

    head = repo.change([path], text="# changed\n")

    assert repo.selected(head) == ["testing/tests/test_build.py", "testing/tests/test_tree.py"]


def test_a_plugin_of_testing_selects_the_tests_that_ask_for_its_fixtures_and_not_all(repo):
    """A change to what the plugin runs for every test, at its top level or in an autouse
    fixture, runs on main's full run."""
    head = repo.change(["testing/fixtures.py"], text="# changed\n")

    assert repo.selected(head) == ["testing/tests/test_tree.py", "testing/tests/test_uses_kit.py"]


def test_a_test_module_only_a_fixture_uses_selects_the_tests_that_ask_for_the_fixture(repo):
    head = repo.change(["testing/tests/test_kit.py"], text="# changed\n")

    assert repo.selected(head) == [
        "testing/tests/test_kit.py",
        "testing/tests/test_tree.py",
        "testing/tests/test_uses_kit.py",
    ]


FEATURE = {
    "features/x/tests/test_feature.py": (
        "from alpha import a\nfrom helper import HELP\n\n\ndef test_it(shared):\n    pass\n"
    ),
}


@pytest.mark.parametrize(
    "path",
    ["src/alpha/util.py", "testing/tests/helper.py", "testing/tests/test_shared.py", *FEATURE],
)
def test_a_test_in_a_features_own_folder_is_selected_like_one_of_tests(repo, path):
    write(repo.root, FEATURE)
    repo.base = repo.commit()

    assert "features/x/tests/test_feature.py" in repo.selected(repo.change([path]))


def test_a_test_module_named_as_a_plugin_selects_the_tests_that_ask_for_its_fixture(repo):
    """A test that has its own fixture of the same name does not ask for the plugin's fixture."""
    write(repo.root, FEATURE)
    repo.base = repo.commit()

    assert repo.selected(repo.change(["testing/tests/test_shared.py"])) == [
        "features/x/tests/test_feature.py",
        "testing/tests/test_shared.py",
        "testing/tests/test_tree.py",
    ]


def test_a_fixture_selects_the_tests_that_name_it(repo):
    head = repo.change(["testing/tests/fixtures/shapes/a.json"])

    assert repo.selected(head) == ["testing/tests/test_shapes.py", "testing/tests/test_tree.py"]


def test_a_fixture_no_test_names_selects_all(repo):
    head = repo.change(["testing/tests/fixtures/orphan/x.json"])

    assert repo.selected(head) == ["all"]


def test_a_changed_test_selects_itself_and_each_test_that_imports_it_however_deep(repo):
    head = repo.change(["testing/tests/test_helper.py"])

    assert repo.selected(head) == [
        "testing/tests/test_helper.py",
        "testing/tests/test_tree.py",
        "testing/tests/test_user.py",
        "testing/tests/test_user_of_user.py",
    ]


def test_a_change_of_the_tests_alone_selects_as_the_same_change_with_code_does(tmp_path):
    """A test file and a helper of the tests changed, alone or beside a path outside the tests:
    both run the changed files, the tests that import the helper, the cross-cutting tests and
    the catch-all, since no rule narrows a change of the tests alone."""
    repo = Repo(tmp_path, files={**FILES, **LONE})
    tests = ["testing/tests/test_helper.py", "testing/tests/helper.py"]
    reached = [
        "testing/tests/test_helped.py",
        "testing/tests/test_helper.py",
        "testing/tests/test_lone.py",
        "testing/tests/test_tree.py",
        "testing/tests/test_user.py",
        "testing/tests/test_user_of_user.py",
    ]

    assert repo.selected(repo.change(tests)) == reached
    assert repo.selected(repo.change([*tests, "README.md"])) == reached


def test_a_comment_added_to_a_test_file_alone_selects_the_guard_that_reads_every_file(tmp_path):
    """`test_no_comments.py` reads every tracked file for a plain comment, and the map lists it
    as cross-cutting. A comment added to a test file, and nothing else, selects it."""
    guard = "testing/tests/test_no_comments.py"
    features = {
        "README.md": README.replace("- `testing/tests/test_tree.py`", f"- `{guard}`"),
        "alpha.md": ALPHA,
        "beta.md": BETA,
    }
    files = {**FILES, guard: "def test_no_plain_comment():\n    pass\n"}
    files.pop("testing/tests/test_tree.py")
    repo = Repo(tmp_path, features=features, files=files)

    head = repo.change(["testing/tests/test_glob.py"], text="# a plain comment\n")

    assert repo.selected(head) == ["testing/tests/test_glob.py", guard]


NESTED = {
    "testing/tests/area/__init__.py": "",
    "testing/tests/area/scene.py": "import alpha.util\n",
    "testing/tests/area/conftest.py": "import pytest\n\n\n@pytest.fixture\ndef spot():\n    pass\n",
    "testing/tests/area/test_area_one.py": "from area.scene import S\n",
    "testing/tests/area/test_area_two.py": "def test_two(spot):\n    pass\n",
}


@pytest.mark.parametrize(
    ("path", "chosen"),
    [
        ("src/alpha/util.py", {"testing/tests/area/test_area_one.py"}),
        ("testing/tests/area/scene.py", {"testing/tests/area/test_area_one.py"}),
        (
            "testing/tests/area/conftest.py",
            {"testing/tests/area/test_area_one.py", "testing/tests/area/test_area_two.py"},
        ),
        ("testing/tests/area/test_area_two.py", {"testing/tests/area/test_area_two.py"}),
    ],
)
def test_a_test_file_in_a_folder_of_tests_is_selected_by_its_imports_and_its_folders_conftest(
    repo, path, chosen
):
    write(repo.root, NESTED)
    repo.base = repo.commit()

    selected = repo.selected(repo.change([path]))

    assert {one for one in selected if one.startswith("testing/tests/area/")} == chosen


def test_the_summary_counts_a_test_file_in_a_folder_of_tests(repo, tmp_path):
    write(repo.root, NESTED)
    repo.base = repo.commit()
    head = repo.change(["pyproject.toml"])
    flat = len(list((repo.root / "testing" / "tests").glob("test_*.py")))

    _, lines = summary(repo, head, tmp_path)

    assert int(SUMMARY.fullmatch(lines[0])["of"]) == flat + 2


def test_a_deleted_test_is_not_named(repo):
    head = repo.change(["src/alpha/util.py"], gone=["testing/tests/test_alpha.py"])

    assert repo.selected(head) == [
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
    ]


def test_a_moved_module_selects_the_tests_that_imported_it_from_where_it_was(repo):
    head = repo.change(moved=[("src/alpha/a.py", "lib/a.py")])

    assert repo.selected(head) == [
        "testing/tests/test_alpha.py",
        "testing/tests/test_glob.py",
        "testing/tests/test_helped.py",
        "testing/tests/test_tree.py",
    ]


def test_the_same_commits_give_the_same_lines(repo):
    head = repo.change(["src/alpha/a.py", "testing/tests/test_helper.py", "src/beta/b.py"])

    assert repo.run(repo.base, head).stdout == repo.run(repo.base, head).stdout


@pytest.mark.parametrize(
    "path",
    ["src/alpha/a.py", "src/jbriefs/skills.py", "testing/tests/test_helper.py", "docs/alpha.md"],
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


SCRIPTS = {
    "scripts/kit/__init__.py": "",
    "scripts/kit/walk.py": "def walk():\n    pass\n",
    "testing/tests/test_walk.py": (
        "import sys\n\nsys.path.insert(0, 'scripts')\nfrom kit.walk import walk\n\n\n"
        "def test_walk():\n    walk()\n"
    ),
}


def test_a_change_to_a_package_of_scripts_selects_the_tests_that_put_it_on_the_path(tmp_path):
    repo = Repo(tmp_path, files={**FILES, **SCRIPTS})

    assert "testing/tests/test_walk.py" not in repo.selected(repo.change(["src/gamma/g.py"]))
    assert "testing/tests/test_walk.py" in repo.selected(repo.change(["scripts/kit/walk.py"]))


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
    return ran.stdout.splitlines(), lead(file).splitlines()


def lead(file):
    """The summary's lines above its list of the selection."""
    return file.read_text().split("\n\n")[0].strip()


def test_the_selection_is_added_to_the_job_summary_as_a_line_a_collector_can_read(repo, tmp_path):
    head = repo.change(["src/alpha/util.py", "docs/alpha.md"])
    total = len(list((repo.root / "testing" / "tests").glob("test_*.py")))

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
    total = len(list((repo.root / "testing" / "tests").glob("test_*.py")))

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    found = SUMMARY.fullmatch(lines[0])
    assert found, lines[0]
    assert (found["selection"], int(found["files"]), int(found["of"])) == ("all", total, total)
    assert found["forced"] == "pyproject.toml"


def test_a_changed_python_file_in_no_module_set_is_named_under_the_summary_line(repo, tmp_path):
    head = repo.change(["tools/loose.py", "src/alpha/util.py"])

    _, lines = summary(repo, head, tmp_path)

    assert SUMMARY.fullmatch(lines[0])
    assert lines[1:] == [
        "warning: tools/loose.py is in no module set, so no import of it selects a test"
    ]


def test_a_changed_path_every_test_rests_on_gets_no_warning(repo, tmp_path):
    head = repo.change(["conftest.py"])

    printed, lines = summary(repo, head, tmp_path)

    assert printed == ["all"]
    assert lines == [lines[0]]


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


BROWSER_MODULE = "import pytest\n\npytestmark = [pytest.mark.timeout(9), pytest.mark.browser]\n"
BROWSER_TEST = (
    "import beta.b\nimport pytest\n\n\n@pytest.mark.browser\ndef test_beta():\n    pass\n"
)


def test_a_test_module_marked_browser_is_not_selected_by_a_change_that_reaches_it(repo):
    write(repo.root, {"testing/tests/test_alpha.py": BROWSER_MODULE + "from alpha import a\n"})
    repo.base = repo.commit()

    head = repo.change(["src/alpha/a.py"])
    assert "testing/tests/test_alpha.py" not in repo.selected(head)
    repo.base = repo.commit_head()
    assert "testing/tests/test_alpha.py" not in repo.selected(
        repo.change(["testing/tests/test_alpha.py"])
    )


def test_a_test_module_that_imports_a_browser_module_is_still_selected(repo):
    write(repo.root, {"testing/tests/test_helper.py": BROWSER_MODULE + "HELP = 1\n"})
    repo.base = repo.commit()

    selected = repo.selected(repo.change(["testing/tests/test_helper.py"]))
    assert "testing/tests/test_helper.py" not in selected
    assert "testing/tests/test_user.py" in selected


def test_a_module_with_one_test_marked_is_selected_whole_and_make_leaves_that_test_out(repo):
    write(repo.root, {"testing/tests/test_beta.py": BROWSER_TEST})
    repo.base = repo.commit()

    assert "testing/tests/test_beta.py" in repo.selected(repo.change(["src/beta/b.py"]))


SMALL = {
    "conftest.py": "",
    "src/small/__init__.py": "",
    "testing/tests/test_tree.py": "def test_tree():\n    pass\n",
    **{f"testing/tests/test_{name}.py": "import small\n" for name in "abcd"},
}


def outputs(repo, head, tmp_path):
    """What the selection printed, its summary line, and what it gave the step's outputs. The
    file `$SELECTED` names, the list the check keeps as an artifact, holds a line for each file
    it printed."""
    file, output, kept = tmp_path / "summary.md", tmp_path / "output", tmp_path / "selected.txt"
    env = {"PATH": "/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(file), "GITHUB_OUTPUT": str(output)}
    ran = repo.run(repo.base, head, env=env | {"SELECTED": str(kept)})
    assert ran.returncode == 0, ran.stderr
    assert [line.split(" ")[0] for line in kept.read_text().splitlines()] == ran.stdout.split()
    given = dict(line.split("=", 1) for line in output.read_text().splitlines())
    return ran.stdout.splitlines(), SUMMARY.fullmatch(lead(file)), given


def test_a_selection_of_every_test_file_runs_what_it_selected_and_not_all(tmp_path):
    """Of five test files, the four changed ones and the cross-cutting one make all five: the
    selection names them, and only a path every test rests on makes it `all`."""
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change([f"testing/tests/test_{name}.py" for name in "abcd"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert printed == [
        "testing/tests/test_a.py",
        "testing/tests/test_b.py",
        "testing/tests/test_c.py",
        "testing/tests/test_d.py",
        "testing/tests/test_tree.py",
    ]
    assert (line["selection"], line["files"], line["of"], line["forced"]) == ("some", "5", "5", "-")
    assert given == {"selection": "some", "files": "5", "forced_by": ""}


def test_a_selection_of_some_test_files_runs_only_what_it_selected(tmp_path):
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["testing/tests/test_a.py", "testing/tests/test_b.py"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert printed == [
        "testing/tests/test_a.py",
        "testing/tests/test_b.py",
        "testing/tests/test_tree.py",
    ]
    assert (line["selection"], line["files"], line["forced"]) == ("some", "3", "-")
    assert given == {"selection": "some", "files": "3", "forced_by": ""}


@pytest.mark.parametrize("path", ["pyproject.toml", "conftest.py"])
def test_a_path_every_test_rests_on_still_runs_all_however_few_tests_there_are(tmp_path, path):
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change([path], text="# changed\n")

    printed, line, given = outputs(repo, head, tmp_path)

    assert (printed, line["forced"]) == (["all"], path)
    assert given == {"selection": "all", "files": "all", "forced_by": path}


def test_a_path_that_forces_all_says_all_to_the_steps_outputs(repo, tmp_path):
    head = repo.change(["pyproject.toml"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert (printed, line["forced"]) == (["all"], "pyproject.toml")
    assert given == {"selection": "all", "files": "all", "forced_by": "pyproject.toml"}


def timed(seconds, table="file_table"):
    """A table, the file table unless named, as `testing/split.py` writes and reads it, of these
    tests' seconds by node id."""
    from testing import split

    return getattr(split, table)(seconds)


TOOK = {
    "testing/tests/test_slow.py::test_slow": 10,
    "testing/tests/test_two.py::test_one": 3,
    "testing/tests/test_two.py::test_two": 3,
}


PARTED = {
    "conftest.py": "",
    "testing/__init__.py": "",
    "testing/split.py": (REPO / "testing" / "split.py").read_text(),
    "testing/shard-times.tsv": timed(TOOK, table="table"),
    "testing/shard-file-times.tsv": timed(TOOK),
    "testing/tests/test_tree.py": "def test_tree():\n    pass\n",
    "testing/tests/test_slow.py": "def test_slow():\n    pass\n",
    "testing/tests/test_two.py": "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
}


def parted(tmp_path, count, files=PARTED, changed=("slow", "two")):
    """`--parts <count>` over a change to these test files, run as the job `reuse` runs it, with
    no pytest at hand: what it printed, its summary, and what it gave the step's outputs."""
    repo = Repo(tmp_path / "repo", files=dict(files))
    head = repo.change([f"testing/tests/test_{name}.py" for name in changed])
    summary, output = tmp_path / "summary.md", tmp_path / "output"
    ran = subprocess.run(
        [sys.executable, "-S", repo.root / "scripts" / "select_tests.py", "--parts", str(count)]
        + [repo.base, head],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_OUTPUT": str(output),
            "SELECTED": str(tmp_path / "selection.txt"),
        },
    )
    given = (
        dict(line.split("=", 1) for line in output.read_text().splitlines())
        if output.exists()
        else {}
    )
    return ran, summary.read_text() if summary.exists() else "", given


def test_parts_get_test_files_dealt_by_time_once_for_all_parts_and_one_past_a_share_by_test(
    tmp_path,
):
    """The selection's files are dealt out by the tables, with no collection, slowest first, to
    the part with the least time so far, so a part collects only its own files. A file the table
    does not hold counts `FLOOR` for each test it defines. A file whose tests sum past a part's
    share (6 s of 16.1 s over 4 parts) is dealt by test: each part that holds some of its tests
    gets the file and a word that picks them, the one with the tests the table does not hold
    `--shard-skip` of the other's. A single test of 10 s cannot be split, and has a part of its
    own."""
    from testing import split

    ran, summary, given = parted(tmp_path, 4)

    assert ran.returncode == 0, ran.stderr
    one, two = sorted(split.key(f"testing/tests/test_two.py::test_{n}") for n in ("one", "two"))
    assert given == {
        "selection": "some",
        "files": "3",
        "forced_by": "",
        "part1": "testing/tests/test_slow.py",
        "part2": f"testing/tests/test_two.py --shard-skip=testing/tests/test_two.py:{two}",
        "part3": f"testing/tests/test_two.py --shard-tests=testing/tests/test_two.py:{two}",
        "part4": "testing/tests/test_tree.py",
    }
    assert "parts: 4 of 3 files, 0 3 3 10 s of test time each" in summary
    assert ran.stdout.splitlines()[-4:] == [
        "part 1: testing/tests/test_slow.py",
        f"part 2: testing/tests/test_two.py --shard-skip=testing/tests/test_two.py:{two}",
        f"part 3: testing/tests/test_two.py --shard-tests=testing/tests/test_two.py:{two}",
        "part 4: testing/tests/test_tree.py",
    ]
    kept = (tmp_path / "selection.txt").read_text().splitlines()
    assert "testing/tests/test_two.py imports,catch-all part=2,3" in kept


def test_a_part_the_selection_leaves_empty_gets_none(tmp_path):
    """Four tests over eight parts leave four empty, and the check's part passes on `none`."""
    ran, _, given = parted(tmp_path, 8)

    assert ran.returncode == 0, ran.stderr
    assert [given[f"part{n}"] for n in range(1, 9)].count("none") == 4


def test_every_selected_file_is_in_exactly_one_part(tmp_path):
    ran, _, given = parted(tmp_path, 2)

    assert ran.returncode == 0, ran.stderr
    assert given == {
        "selection": "some",
        "files": "3",
        "forced_by": "",
        "part1": "testing/tests/test_slow.py",
        "part2": "testing/tests/test_tree.py testing/tests/test_two.py",
    }


def test_the_selections_list_names_the_part_that_runs_each_file(tmp_path):
    """The job `reuse` keeps each part's selection: every file with why and its part."""
    ran, summary, _ = parted(tmp_path, 2)

    assert ran.returncode == 0, ran.stderr
    kept = (tmp_path / "selection.txt").read_text().splitlines()
    assert kept == [
        "testing/tests/test_slow.py imports,catch-all part=1",
        "testing/tests/test_tree.py cross-cutting part=2",
        "testing/tests/test_two.py imports,catch-all part=2",
    ]
    assert summary.rstrip().endswith("\n".join(kept) + "\n```\n</details>")


def test_an_all_dealt_to_parts_lists_every_file_with_its_part():
    parts = [["testing/tests/test_b.py"], ["testing/tests/test_a.py"]]

    assert select.reasons(["all"], {"forced-by": "uv.lock"}, parts) == [
        "all forced-by=uv.lock",
        "testing/tests/test_a.py all part=2",
        "testing/tests/test_b.py all part=1",
    ]


def test_the_deal_of_no_test_file_fails():
    with pytest.raises(SystemExit, match="holds no test"):
        select.dealt([], {}, {}, 8)


def test_a_file_past_a_part_s_share_is_cut_into_the_fewest_pieces_that_fit_a_share():
    """A file of 40 tests of 10 s beside 200 files of 1 s, over 4 parts: its 400 s are past a
    share of 150 s, so it is cut into 3 pieces, each in a part of its own, and not spread over
    every part, since each part a piece lands in builds the file's caches again. Each test of it
    the table holds is run by exactly one part, and one more it does not hold by the part that
    skips the others' tests."""
    from testing import split

    big = [f"a/test_big.py::test_{n}" for n in range(40)]
    rest = [f"a/test_{n}.py::test_one" for n in range(200)]
    took = dict.fromkeys(big, 10) | dict.fromkeys(rest, 1)
    tests = {"a/test_big.py": {split.key(test): 10 for test in big}}
    files = split.by_file(took)
    parts, seconds = select.dealt(sorted(files), files, tests, 4)
    holding = [part for part in parts if "a/test_big.py" in part]
    assert len(holding) == 3
    new = "a/test_big.py::test_new"
    ran = Counter(test for part in holding for test in picked(part, [*big, new]))
    assert sorted(ran) == sorted([*big, new]) and set(ran.values()) == {1}
    assert max(seconds) - min(seconds) <= 10


def picked(words, nodeids):
    """The node ids of `nodeids` a part with these words runs, as `testing/shard.py` picks them."""
    from testing import shard

    files = {word for word in words if not word.startswith("-")}
    only = shard.scoped(
        [word.partition("=")[2] for word in words if word.startswith("--shard-tests=")]
    )
    skip = shard.scoped(
        [word.partition("=")[2] for word in words if word.startswith("--shard-skip=")]
    )
    mine = [test for test in nodeids if test.partition("::")[0] in files]
    return shard.picked(mine, only, skip)


def test_a_file_whose_slowest_test_outlasts_a_part_is_dealt_alone_and_one_of_quick_tests_is_not():
    """Files are dealt whole, and a part never ends before the slowest test of its files: a file
    of one 60 s test gets a part to itself, and a file of 60 tests of 1 s, as long in all, shares
    one, since its tests spread over the part's workers."""
    from testing import split

    serial = ["a/test_serial.py::test_long"]
    spread = [f"a/test_spread.py::test_{n}" for n in range(60)]
    rest = [f"a/test_{n}.py::test_one" for n in range(200)]
    took = {serial[0]: 60} | dict.fromkeys(spread + rest, 1)
    files = split.by_file(took)
    parts, _ = select.dealt(sorted(files), files, {}, 4)
    assert ["a/test_serial.py"] in parts
    (spreads,) = [part for part in parts if "a/test_spread.py" in part]
    assert len(spreads) > 1


@pytest.mark.parametrize(
    "argv",
    [["--parts", "0", "a", "b"], ["--parts", "x", "a", "b"], ["--part", "desk", "a", "b"]],
    ids=["no parts", "a count that is no number", "the desk part, which is gone"],
)
def test_parts_takes_a_count_of_one_or_more_and_part_only_its_named_parts(argv):
    with pytest.raises(SystemExit, match="usage"):
        select.main(argv)


def listed_selection(repo, head, tmp_path, failed=None):
    """What the selection printed, the list it wrote to `$SELECTED`, and the list in the
    summary's folded block."""
    file, kept = tmp_path / "summary.md", tmp_path / "selection.txt"
    env = {
        "PATH": "/usr/bin:/bin",
        "GITHUB_STEP_SUMMARY": str(file),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "SELECTED": str(kept),
    }
    if failed is not None:
        env["FAILED_ON_MAIN"] = failed
    ran = repo.run(repo.base, head, env=env)
    assert ran.returncode == 0, ran.stderr
    block = file.read_text().split("<details>", 1)[1]
    assert block.startswith("<summary>selected: ")
    shown = block.split("```\n", 1)[1].split("\n```", 1)[0]
    return ran.stdout.splitlines(), kept.read_text().splitlines(), shown.splitlines()


def test_the_selection_lists_each_test_file_with_why_in_the_summary_and_the_file(tmp_path):
    """A part keeps what it selected: each test file and each cause that selected it, so a
    test a pull request did not run can be traced to the selection."""
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["testing/tests/test_a.py", "src/small/__init__.py"])

    printed, kept, shown = listed_selection(repo, head, tmp_path)

    assert kept == shown
    assert [line.split(" ")[0] for line in kept] == printed
    assert kept == [
        "testing/tests/test_a.py imports",
        "testing/tests/test_b.py imports",
        "testing/tests/test_c.py imports",
        "testing/tests/test_d.py imports",
        "testing/tests/test_tree.py cross-cutting",
    ]


def test_the_list_names_a_test_that_failed_on_main_as_failed_on_main(tmp_path):
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["testing/tests/test_tree.py"])

    printed, kept, _ = listed_selection(repo, head, tmp_path, failed="testing/tests/test_b.py")

    assert "testing/tests/test_b.py failed-on-main" in kept
    assert len(kept) == len(printed)


def test_a_change_of_the_tests_alone_still_runs_each_test_that_failed_on_main(tmp_path):
    """A push to main runs a selection, not the whole suite, and the lookup counts its green run as
    one that passed every test still red on main. So a test that failed on main runs on a change
    of the tests alone too: else it drops out red, as test_children.py did after #1377."""
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["testing/tests/test_tree.py"])

    printed, kept, _ = listed_selection(repo, head, tmp_path, failed="testing/tests/test_b.py")

    assert "testing/tests/test_b.py failed-on-main" in kept
    assert "testing/tests/test_b.py" in printed


@pytest.mark.parametrize("code", [403, 429])
def test_a_spent_allowance_runs_the_whole_suite_and_says_so_in_one_line(tmp_path, code):
    """GitHub answers 403 or 429 once the installation's hourly allowance is spent. The lookup
    of the tests that failed on main cannot then say which they are, so it passes and asks for
    the whole suite, and the selection runs it: on 2026-11-09 such a lookup ended red."""
    import http.server
    import threading

    class Spent(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(code)
            self.send_header("x-ratelimit-remaining", "0")
            self.end_headers()
            self.wfile.write(b'{"message": "API rate limit exceeded for installation."}')

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Spent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    repo = Repo(tmp_path / "repo", files=SMALL)
    try:
        looked = repo.run(
            "--failed-on-main",
            "30",
            str(tmp_path / "failed-on-main.json"),
            env={
                "PATH": "/usr/bin:/bin",
                "GITHUB_API_URL": f"http://127.0.0.1:{server.server_port}",
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_TOKEN": "t0ken",
            },
        )
    finally:
        server.shutdown()

    assert (looked.returncode, looked.stdout) == (0, "all\n"), looked.stderr
    said = looked.stderr.splitlines()
    assert len(said) == 1 and f"GitHub answered {code}" in said[0] and "whole suite" in said[0]
    head = repo.change(["testing/tests/test_tree.py"])
    printed, kept, _ = listed_selection(repo, head, tmp_path, failed=looked.stdout.strip())
    assert (printed, kept) == (["all"], ["all forced-by=failed-on-main"])


def test_an_all_lists_the_path_that_forced_it(tmp_path):
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(["pyproject.toml"], text="# changed\n")

    printed, kept, shown = listed_selection(repo, head, tmp_path)

    assert (printed, kept, shown) == (["all"], ["all forced-by=pyproject.toml"], kept)


def test_an_empty_selection_lists_no_test_file():
    assert select.listing(select.reasons([], {})).startswith("<details><summary>selected: 0 test")


MAC_LIST = "testing/macos-quick.txt"


CLI = "features/jmerge/src/jmerge/cli.py"
STOPS = "features/jmerge/src/jmerge/stops.py"
ON_A_MAC = {
    "conftest.py": "",
    MAC_LIST: "testing/tests/test_cli_on_a_mac.py\ntesting/tests/test_stops_on_a_mac.py\n",
    "testing/tests/test_cli_on_a_mac.py": "from jmerge import cli\n",
    STOPS: (
        "import os\n\n\ndef stop(group):\n"
        '    """Kill the group: a group gone gives ESRCH on Linux, and EPERM on Darwin."""\n'
        "    os.killpg(group, 9)\n"
    ),
    "testing/tests/test_stops_on_a_mac.py": "from jmerge import stops\n",
}


@pytest.fixture
def mac_repo(tmp_path):
    return Repo(tmp_path, files=ON_A_MAC)


def edit_line(repo, path, line):
    """Commit an edit of the first line of `path` that holds `line`, as a change's diff would
    make it, and return the new head."""
    file = repo.root / path
    lines = file.read_text().splitlines(keepends=True)
    at = next(at for at, one in enumerate(lines) if line in one)
    lines[at] = lines[at].replace(line, line + " ", 1)
    file.write_text("".join(lines))
    return repo.commit()


def on_a_mac(repo, head, *strict):
    ran = repo.run("--within", MAC_LIST, *strict, repo.base, head)
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.split()


@pytest.mark.parametrize(
    ("path", "line", "reached"),
    [
        (STOPS, "EPERM on Darwin", []),
        (CLI, "def _cwds_from_lsof", []),
        (CLI, "on_a_mac = sys.platform", ["testing/tests/test_cli_on_a_mac.py"]),
        (
            CLI,
            "when no list of every process could be read",
            ["testing/tests/test_cli_on_a_mac.py"],
        ),
    ],
    ids=[
        "a docstring that names Darwin",
        "a function away from the Darwin branch",
        "the line that branches on darwin",
        "the docstring of the function that branches on darwin",
    ],
)
def test_strict_darwin_counts_a_change_only_inside_code_that_branches_on_darwin(
    mac_repo, path, line, reached
):
    """A pull request's macos job runs a change to a module on a Mac only when the change edits a
    function that asks for Darwin in code. The run on each merge commit still runs every test of
    the list the module reaches whose text names Darwin, wherever the change is."""
    head = edit_line(mac_repo, path, line)

    assert on_a_mac(mac_repo, head, "--strict") == reached
    own = "cli" if path == CLI else "stops"
    assert f"testing/tests/test_{own}_on_a_mac.py" in on_a_mac(mac_repo, head)


def test_strict_darwin_counts_a_deleted_darwin_branch(mac_repo):
    """A change that drops the line that asks for Darwin leaves no Darwin code in its head, and
    still runs on a Mac: the base's side of the diff counts as well."""
    file = mac_repo.root / CLI
    file.write_text(
        file.read_text().replace(
            'on_a_mac = sys.platform == "darwin" and Path("/proc") == PROC', "on_a_mac = False"
        )
    )
    head = mac_repo.commit()

    assert on_a_mac(mac_repo, head, "--strict") == ["testing/tests/test_cli_on_a_mac.py"]
