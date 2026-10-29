"""`scripts/select_tests.py <base> <head>` names the test files a diff needs, from what the
tests import and name, and from the map in verify-jstack's `features/`.

The test runs the script as CI runs it, with `python3 -I -S`, so it imports nothing installed.
It runs it in a temporary git repo that holds a copy of the script, a copy of `src/` as it is,
and a few modules, docs and tests of its own. The map's own tests read the repo's map and the
files git tracks. They also run the tests' imports once, to see that the script found every
import the tests made."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_home_thread import named
from testing.paths import REPO, sources

SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)
OWNED = "scripts/".split()
ALSO = ("install.sh",)

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


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


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


def test_the_selector_follows_the_includes_the_tests_fold_in():
    """`as_read` folds in each file beside a skill that a line of it says to read now. The
    selector must find the same files, or a change to one runs none of the tests that read it."""
    folded = {
        (path, found.relative_to(REPO).as_posix())
        for path in select.tracked()
        if path.endswith(".md") and (REPO / path).is_file()
        for found in named(REPO / path)
    }
    found = {(includer, path) for path, by in select.included().items() for includer in by}

    assert folded
    assert found == folded


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


@pytest.mark.parametrize(
    ("changed", "reader"),
    [
        (
            "features/lessons/skills/reflect/references/synthesizer.md",
            "features/lessons/tests/test_lessons.py",
        ),
        ("features/crew/playbooks/bug-fix.md", "features/tdd/tests/test_tdd_skill.py"),
    ],
    ids=["a skill's own file", "a playbook a skill names"],
)
def test_a_change_to_a_file_a_test_of_this_repo_globs_selects_that_test(changed, reader):
    """`test_lessons.py` reads every file of the lessons skills through `rglob`, and an em dash
    in one of them fails it. `test_tdd_skill.py` checks each playbook the tdd skill names, through
    `skill_blocks`. Neither feature lists the test, and no test spells the file."""
    tests, _ = select.selection([changed])

    assert reader in tests


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


@pytest.mark.parametrize(
    "path", ["pyproject.toml", "uv.lock", "conftest.py", "testing/fixtures.py"]
)
def test_a_path_every_test_rests_on_selects_all(repo, path):
    head = repo.change([path], text="# changed\n")

    assert repo.selected(head) == ["all"]


def test_a_test_module_a_plugin_loads_for_every_test_selects_all(repo):
    head = repo.change(["testing/tests/daemons.py"], text="# changed\n")

    assert repo.selected(head) == ["all"]


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


def test_a_change_to_the_view_selects_its_tests_but_not_the_browser_drive_of_its_page():
    selected, _ = select.selection(["features/jbus/src/jbus/view/page.html"])

    assert "features/jbus/tests/view/test_view_server.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]
    assert set(select.cross_cutting()) <= set(selected)
    assert "features/jroles/tests/test_jroles_mirror.py" not in selected


@pytest.mark.parametrize("panel", ["bus", "checks", "words", "you"])
def test_a_change_to_a_panel_selects_the_tests_of_the_view_under_tests_view(panel):
    selected, _ = select.selection([f"features/jbus/src/jbus/view/panels/{panel}/panel.py"])

    assert f"features/jbus/tests/view/test_view_{panel}.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]



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


def test_a_change_to_the_crawl_of_jtrees_selects_the_tests_that_import_it():
    selected, why = select.selection(["scripts/jtrees/crawl.py"])

    assert {
        "testing/tests/test_jtrees.py",
        "testing/tests/test_jtrees_one_feature.py",
        "features/jinstall/tests/test_docs_hooks.py",
    } <= set(selected)
    assert why["imports"] > 0


MERGED = {
    "#330": (
        [
            "features/jbus/docs/jbus/the-sign-in.md",
            "features/jbus/docs/jbus/when-jbus-fails.md",
            "features/jbus/src/jbus/alert.py",
            "features/jbus/src/jbus/signin.py",
            "features/jbus/src/jbus/wake.py",
            "features/jbus/tests/test_jbus_wake_home.py",
        ],
        "features/repo-guards/tests/test_module_size.py",
    ),
    "#337": (
        [
            "features/jbus/tests/fixtures/jbus-view/probe.js",
            "features/jbus/tests/view/page/browser.py",
            "features/jbus/tests/view/page/test_view_page_budgets.py",
        ],
        "features/jbus/tests/view/test_view_sources.py",
    ),
}


@pytest.mark.parametrize(("changed", "broken"), MERGED.values(), ids=MERGED.keys())
def test_a_pull_request_selects_the_test_that_reads_the_whole_tree_its_change_broke(
    changed, broken
):
    """The paths each pull request changed. Its check ran neither test, and main went red after
    the merge: #330 pushed `jbus/wake.py` over the cap of lines, #337 put a URL in a view test."""
    tests, _ = select.selection(changed)

    assert broken in tests


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
    """Whoever moves the last file out of a root folder must also drop the folder here.
    Otherwise the ownership test reads a folder that is gone and names it as covered."""
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
    """The tests of a feature come from what they import and what they name. A `Tests:` entry names
    a test that reads a feature's files without naming them in a string, such as with a glob over a
    tree of files. If an import or a name already selects that test, the entry is redundant."""
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


def test_every_test_file_is_run_by_a_change_to_another_path():
    """A changed test file selects itself, so that change does not count. A test that no change
    to any other path selects is owned by no rule, and a change that breaks it would merge with
    it unrun. The selector's catch-all runs each such test on every change, so none is left."""
    run = set()
    for path in sorted(select.tracked()):
        tests, _ = select.selection([path])
        if tests != ["all"]:
            run |= set(tests) - {path}
    left = [
        test
        for test in tracked("testing/tests/", "features/")
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
files = {
    name: module.__file__
    for name, module in sorted(sys.modules.items())
    if getattr(module, "__file__", None)
}
print(json.dumps({"seen": sorted(seen), "failed": failed, "files": files}))
"""


def test_the_import_graph_has_every_import_that_importing_the_tests_makes():
    ran = subprocess.run(
        [
            sys.executable,
            "-c",
            ORACLE,
            str(REPO / "testing" / "tests"),
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
    scripts = REPO / "scripts"
    imported = {name for _, name in found["seen"]}
    unread = [
        f"{name} from {Path(file).relative_to(REPO)}"
        for name, file in found["files"].items()
        if name in imported and Path(file).is_relative_to(scripts)
        and select.modules().get(name) != Path(file).relative_to(REPO).as_posix()
    ]
    assert (missing, found["failed"], unread) == ([], [], [])


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
    """What the selection printed, its summary line, and what it gave the step's outputs."""
    file, output = tmp_path / "summary.md", tmp_path / "output"
    env = {"PATH": "/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(file), "GITHUB_OUTPUT": str(output)}
    ran = repo.run(repo.base, head, env=env)
    assert ran.returncode == 0, ran.stderr
    given = dict(line.split("=", 1) for line in output.read_text().splitlines())
    return ran.stdout.splitlines(), SUMMARY.fullmatch(file.read_text().strip()), given


def test_a_selection_of_four_fifths_of_the_test_files_or_more_is_the_whole_suite(tmp_path):
    """Of five test files, the three changed ones and the cross-cutting one make four, which is
    80%."""
    repo = Repo(tmp_path / "repo", files=SMALL)
    head = repo.change(
        ["testing/tests/test_a.py", "testing/tests/test_b.py", "testing/tests/test_c.py"]
    )

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
    head = repo.change(["testing/tests/test_a.py", "testing/tests/test_b.py"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert printed == [
        "testing/tests/test_a.py",
        "testing/tests/test_b.py",
        "testing/tests/test_tree.py",
    ]
    assert (line["selection"], line["files"], line["forced"]) == ("some", "3", "-")
    assert given == {"selection": "some"}


def test_a_path_that_forces_all_says_all_to_the_steps_outputs(repo, tmp_path):
    head = repo.change(["pyproject.toml"])

    printed, line, given = outputs(repo, head, tmp_path)

    assert (printed, line["forced"], given) == (["all"], "pyproject.toml", {"selection": "all"})
