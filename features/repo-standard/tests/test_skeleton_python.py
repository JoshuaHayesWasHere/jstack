"""The skeleton a repo starts from, with the python-uv adapter, run as a new repo outside jstack.

`new_repo` makes a repo as `features/repo-standard/docs/skeleton.md` says: it copies
`features/repo-standard/skeleton/` to a temporary dir, copies the adapter,
`features/repo-standard/adapters/python-uv/`, over it, runs `make generate` and commits. The
repo's make clones the standard's guards from an upstream: a git repo tagged `repo-standard-v1`
that holds jstack's `features/repo-standard/src`, as `.repo-standard.yml` pins it. Each case then
runs the repo's own make targets: `check`, `check-fast`, `select` and `lint`.
"""

import json
import os
import shutil
import subprocess

import pytest

from repo_standard.config import parse
from repo_standard.conform import TAG, VERSION
from testing.paths import REPO

STANDARD = REPO / "features" / "repo-standard"
SKELETON = STANDARD / "skeleton"
ADAPTER = STANDARD / "adapters" / "python-uv"
TEMPLATE = REPO / "features" / "home" / "templates" / "check.yml"
CORE = REPO / "schemas" / "feature.core.schema.json"
INHERITED = ("PYTHONPATH", "VIRTUAL_ENV", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "BASE", "TESTS")
PLANTED = {
    "features/alpha/feature.json": '{"name": "alpha", "description": "Alpha."}\n',
    "features/alpha/src/alpha/__init__.py": "",
    "features/alpha/src/alpha/core.py": "VALUE = 1\n",
    "features/alpha/src/alpha/extra.py": "OTHER = 2\n",
    "features/alpha/tests/test_core.py": (
        "from alpha.core import VALUE\n\n\ndef test_value():\n    assert VALUE == 1\n"
    ),
    "features/alpha/tests/test_extra.py": (
        "from alpha import extra\n\n\ndef test_other():\n    assert extra.OTHER == 2\n"
    ),
    "features/beta/feature.json": '{"name": "beta", "description": "Beta."}\n',
    "features/beta/src/beta/__init__.py": "",
    "features/beta/src/beta/use.py": "from alpha.core import VALUE\n\nDOUBLE = VALUE * 2\n",
    "features/beta/tests/test_use.py": (
        "from beta.use import DOUBLE\n\n\ndef test_double():\n    assert DOUBLE == 2\n"
    ),
}


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


@pytest.fixture(scope="module")
def upstream(tmp_path_factory):
    """jstack at the tag the skeleton pins, as far as the repo's make reads it."""
    root = tmp_path_factory.mktemp("upstream")
    shutil.copytree(
        STANDARD / "src",
        root / "features" / "repo-standard" / "src",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the standard")
    git(root, "tag", f"{TAG}{VERSION}")
    return root


@pytest.fixture
def new_repo(tmp_path, upstream):
    """A repo made from the skeleton and the adapter, and the env its make runs in."""
    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("__pycache__", ".venv", ".cache", ".ruff_cache")
    shutil.copytree(SKELETON, root, ignore=ignore)
    shutil.copytree(ADAPTER, root, ignore=ignore, dirs_exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(root, env, "generate")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from the skeleton")
    return root, env


def make(root, env, *args, ok=True):
    done = subprocess.run(
        ["make", "--no-print-directory", "-C", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = done.stdout + done.stderr
    assert (done.returncode == 0) == ok, f"make {' '.join(args)} exited {done.returncode}:\n{out}"
    return done.stdout


def selected(root, env, base):
    return make(root, env, "-s", "select", f"BASE={base}").splitlines()


def test_the_new_repo_passes_its_own_check(new_repo):
    root, env = new_repo
    out = make(root, env, "check")
    assert "1 passed" in out
    assert "conform repo-standard-v1" in out
    assert "errors 0" in out


def test_check_fast_runs_the_tests_its_change_selects(new_repo):
    root, env = new_repo
    hello = root / "features/hello/src/hello/__init__.py"
    hello.write_text(hello.read_text().replace('"hello, ', '"hello there, '))
    (root / "features/hello/tests/test_hello.py").write_text(
        "from hello import greet\n\n\ndef test_greet():\n"
        '    assert greet("repo") == "hello there, repo"\n'
    )
    git(root, "commit", "-qam", "a new greeting")

    assert selected(root, env, "HEAD~1") == ["features/hello/tests/test_hello.py"]
    assert "1 passed" in make(root, env, "check-fast", "BASE=HEAD~1")
    assert selected(root, env, "HEAD") == []
    assert "selects no test" in make(root, env, "check-fast", "BASE=HEAD")


def test_a_change_to_one_module_selects_only_its_importers(new_repo):
    root, env = new_repo
    write(root, PLANTED)
    make(root, env, "generate")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "two features")
    core = root / "features/alpha/src/alpha/core.py"
    core.write_text("VALUE = 1\nMORE = 3\n")

    importers = ["features/alpha/tests/test_core.py", "features/beta/tests/test_use.py"]
    assert selected(root, env, "HEAD") == importers
    assert "2 passed" in make(root, env, "check-fast", "BASE=HEAD")

    (root / "features/alpha/tests/conftest.py").write_text("")
    assert selected(root, env, "HEAD") == [
        *importers[:1],
        "features/alpha/tests/test_extra.py",
        importers[1],
    ]


@pytest.mark.parametrize(
    ("path", "text", "selection"),
    [
        ("pyproject.toml", "\n", ["all"]),
        ("scripts/select.py", "\n", ["all"]),
        ("notes.txt", "a stray file\n", ["all"]),
        ("features/hello/docs/hello.md", "More.\n", []),
    ],
)
def test_a_shared_path_selects_all_and_a_page_selects_nothing(new_repo, path, text, selection):
    root, env = new_repo
    with (root / path).open("a") as file:
        file.write(text)
    assert selected(root, env, "HEAD") == selection


def test_a_change_across_two_features_passes_the_lint_and_needs_its_label(new_repo):
    """The shared check runs `make lint BASE=HEAD^1` with no labels, and borders.yml reads them."""
    root, env = new_repo
    write(root, PLANTED)
    make(root, env, "generate")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "two features")

    make(root, env, "lint", "BASE=HEAD~1")
    out = make(root, env, "borders", "BASE=HEAD~1", ok=False)
    assert "cross-cutting" in out
    make(root, {**env, "LABELS": "cross-cutting"}, "borders", "BASE=HEAD~1")


def test_a_planted_unowned_file_fails_the_lint(new_repo):
    root, env = new_repo
    make(root, env, "lint")
    write(root, {"notes/stray.txt": "a file no owner claims\n"})
    git(root, "add", "-A")
    out = make(root, env, "lint", ok=False)
    assert "notes/stray.txt" in out


def test_select_needs_a_base(new_repo):
    root, env = new_repo
    make(root, env, "select", ok=False)
    make(root, env, "-s", "select", "BASE=no-such-ref", ok=False)


def test_the_skeleton_calls_the_shared_check_as_new_home_writes_it():
    """One template: the skeleton's caller is /new-home's, with `make check` as its command."""
    written = TEMPLATE.read_text().replace("<the check command>", "make check")
    assert parse((SKELETON / ".github/workflows/check.yml").read_text()) == parse(written)
    assert json.loads((SKELETON / "schemas/feature.core.schema.json").read_text()) == json.loads(
        CORE.read_text()
    )
