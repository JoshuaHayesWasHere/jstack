"""The skeleton with two stacks in one repo, in the shape of LittleRamPantries, run as a new repo.

`stacked_repo` makes a repo from the skeleton as `features/repo-standard/docs/skeleton.md` says
for a repo of several stacks: it copies the scripts of the go and python-uv adapters, and its
`.repo-standard.yml` sets `stacks:` with a Go stack `api` over `api/` and a python-uv stack
`capture` over `tools/capture/`, a uv project of its own with flat modules and a `tests/` folder.
Each case runs the repo's own make targets, which hand each stack to the standard's driver. The
module skips where go does not run.
"""

import os
import shutil

import pytest

import test_skeleton_python as skeleton
from test_go_adapter import needs_go
from test_skeleton_python import INHERITED, SKELETON, STANDARD, git, make, write

pytestmark = needs_go
upstream = skeleton.upstream
ADAPTERS = STANDARD / "adapters"
UV = ADAPTERS / "python-uv"
GO_IDS = ["api/handlers", "api/store"]
CAPTURE_IDS = ["tools/capture/tests/test_main.py", "tools/capture/tests/test_shadow.py"]
STACKS = """stacks:
  api:
    adapter: go
    roots: [api]
  capture:
    adapter: python-uv
    roots: [tools/capture]
"""
PYTEST = '\n[tool.pytest.ini_options]\npythonpath = ["."]\naddopts = "-q"\n'
PLANTED = {
    "api/go.mod": "module example.com/api\n\ngo 1.24\n",
    "api/store/store.go": "package store\n\nconst Boxes = 3\n",
    "api/store/store_test.go": (
        'package store\n\nimport "testing"\n\nfunc TestBoxes(t *testing.T) {\n'
        '\tif Boxes != 3 {\n\t\tt.Fatal("Boxes is not 3")\n\t}\n}\n'
    ),
    "api/handlers/handlers.go": 'package handlers\n\nconst Route = "/boxes"\n',
    "api/handlers/handlers_test.go": (
        'package handlers\n\nimport "testing"\n\nfunc TestRoute(t *testing.T) {\n'
        '\tif Route != "/boxes" {\n\t\tt.Fatal("Route is not /boxes")\n\t}\n}\n'
    ),
    "tools/capture/shadow.py": 'def report(count):\n    return {"count": count}\n',
    "tools/capture/main.py": "from shadow import report\n\n\ndef run():\n    return report(1)\n",
    "tools/capture/tests/test_shadow.py": (
        'from shadow import report\n\n\ndef test_report():\n    assert report(2) == {"count": 2}\n'
    ),
    "tools/capture/tests/test_main.py": (
        'from main import run\n\n\ndef test_run():\n    assert run() == {"count": 1}\n'
    ),
    "tools/capture/Dockerfile": "FROM python:3.12-slim\n",
}


@pytest.fixture
def stacked_repo(tmp_path, upstream):
    """A repo of the two stacks, made from the skeleton and both adapters' scripts, and its env."""
    root = tmp_path / "repo"
    shutil.copytree(SKELETON, root, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    shutil.copy(ADAPTERS / "go" / "scripts" / "go.py", root / "scripts" / "go.py")
    shutil.copy(UV / "scripts" / "select.py", root / "scripts" / "select.py")
    write(root, PLANTED)
    capture = root / "tools" / "capture"
    shutil.copy(UV / "uv.lock", capture / "uv.lock")
    project = (UV / "pyproject.toml").read_text()
    (capture / "pyproject.toml").write_text(project.split("[tool.pytest")[0] + PYTEST)
    config = (root / ".repo-standard.yml").read_text()
    config = config.replace("layout: [", "layout: [api/, tools/, ")
    config = config.replace(
        "  STACK: [pyproject.toml, uv.lock, conftest.py]",
        '  STACK: []\n  API: ["api/**"]\n  CAPTURE: ["tools/capture/**"]',
    )
    config = config.replace("[scripts/stack.mk]", "[scripts/go.py, scripts/select.py]")
    (root / ".repo-standard.yml").write_text(config + STACKS)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(root, env, "generate")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from the skeleton, with two stacks")
    return root, env


def selected(root, env):
    return make(root, env, "-s", "select", "BASE=HEAD").splitlines()


def change(root, path, text="\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    with (root / path).open("a") as file:
        file.write(text)


def test_the_repo_of_two_stacks_passes_its_lint_its_tests_and_an_empty_select(stacked_repo):
    root, env = stacked_repo
    out = make(root, env, "lint")
    assert "errors 0" in out
    out = make(root, env, "test")
    assert "ok  \texample.com/api/handlers" in out
    assert "ok  \texample.com/api/store" in out
    assert "2 passed" in out
    assert selected(root, env) == []


@pytest.mark.parametrize(
    ("path", "selection"),
    [
        ("api/store/store.go", GO_IDS),
        ("tools/capture/shadow.py", CAPTURE_IDS),
        ("tools/capture/tests/test_main.py", CAPTURE_IDS[:1]),
        ("tools/capture/uv.lock", ["stack:capture"]),
        ("tools/capture/Dockerfile", ["stack:capture"]),
        ("api/notes.txt", GO_IDS),
        ("Makefile", ["all"]),
        ("scripts/select.py", ["all"]),
        ("notes.txt", ["all"]),
        ("README.md", []),
        ("tools/capture/README.md", []),
    ],
)
def test_a_change_selects_in_the_stack_whose_roots_hold_it(stacked_repo, path, selection):
    root, env = stacked_repo
    change(root, path)
    assert selected(root, env) == selection


def test_a_change_in_both_stacks_selects_from_each(stacked_repo):
    root, env = stacked_repo
    change(root, "api/handlers/handlers.go")
    change(root, "tools/capture/main.py")
    assert selected(root, env) == ["api/handlers", "api/store", CAPTURE_IDS[0]]


def test_make_test_routes_each_id_to_its_stack(stacked_repo):
    root, env = stacked_repo
    out = make(root, env, "test", "TESTS=stack:capture api/handlers")
    assert "ok  \texample.com/api/handlers" in out
    assert "example.com/api/store" not in out
    assert "2 passed" in out

    out = make(root, env, "test", "TESTS=tools/capture/tests/test_main.py")
    assert "1 passed" in out
    assert "example.com/api" not in out

    write(root, {"tools/capture/shadow.py": "def report(count):\n    return {}\n"})
    make(root, env, "test", "TESTS=api/store tools/capture/tests/test_shadow.py", ok=False)
    make(root, env, "test", "TESTS=nowhere/at/all", ok=False)
    make(root, env, "test", "TESTS=stack:nothing", ok=False)


def test_a_lint_fault_in_one_stack_fails_the_lint(stacked_repo):
    root, env = stacked_repo
    write(root, {"api/store/store.go": "package store\nconst Boxes=3\n"})
    out = make(root, env, "lint", ok=False)
    assert "api/store/store.go" in out
