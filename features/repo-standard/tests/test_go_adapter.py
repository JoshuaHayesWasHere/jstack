"""The skeleton a repo starts from, with the go adapter, run as a new repo of several Go modules.

`go_repo` makes a repo as `features/repo-standard/docs/skeleton.md` says, with the adapter
`features/repo-standard/adapters/go/`, and adds three features: `alpha`, a module with two
packages; `beta`, a module that takes alpha by a `replace` onto its folder, as a repo with no
go.work does, and whose test reads a page of `catalog`, which beta's manifest names in `reads`;
and `catalog`, which has no module. Each case runs the repo's own make targets. A case that runs
go skips, saying why, where go does not run.
"""

import json
import os
import shutil
import subprocess

import pytest

import test_skeleton_python as skeleton
from repo_standard.config import parse
from test_skeleton_python import INHERITED, SKELETON, STANDARD, git, make, write

ADAPTER = STANDARD / "adapters" / "go"
upstream = skeleton.upstream
ALPHA = ["features/alpha/core", "features/alpha/extra"]
BETA = ["features/beta/pricing", "features/beta/use"]
PLANTED = {
    "features/alpha/feature.json": '{"name": "alpha", "description": "Alpha."}\n',
    "features/alpha/go.mod": "module example.com/alpha\n\ngo 1.24\n",
    "features/alpha/core/core.go": "package core\n\nconst Value = 1\n",
    "features/alpha/core/alpha_core_test.go": (
        'package core\n\nimport "testing"\n\nfunc TestValue(t *testing.T) {\n'
        '\tif Value != 1 {\n\t\tt.Fatal("Value is not 1")\n\t}\n}\n'
    ),
    "features/alpha/extra/extra.go": "package extra\n\nconst Other = 2\n",
    "features/alpha/extra/alpha_extra_test.go": (
        'package extra\n\nimport "testing"\n\nfunc TestOther(t *testing.T) {\n'
        '\tif Other != 2 {\n\t\tt.Fatal("Other is not 2")\n\t}\n}\n'
    ),
    "features/beta/feature.json": json.dumps(
        {"name": "beta", "description": "Beta.", "reads": ["features/catalog/docs/prices.md"]}
    ),
    "features/beta/go.mod": (
        "module example.com/beta\n\ngo 1.24\n\nrequire example.com/alpha v0.0.0\n\n"
        "replace (\n\texample.com/alpha => ../alpha\n)\n"
    ),
    "features/beta/use/use.go": (
        'package use\n\nimport "example.com/alpha/core"\n\nconst Double = core.Value * 2\n'
    ),
    "features/beta/use/beta_use_test.go": (
        'package use\n\nimport "testing"\n\nfunc TestDouble(t *testing.T) {\n'
        '\tif Double != 2 {\n\t\tt.Fatal("Double is not 2")\n\t}\n}\n'
    ),
    "features/beta/pricing/beta_pricing_test.go": (
        'package pricing\n\nimport (\n\t"os"\n\t"strings"\n\t"testing"\n)\n\n'
        "func TestThePricesPageNamesAPrice(t *testing.T) {\n"
        '\tpage, err := os.ReadFile("../../catalog/docs/prices.md")\n'
        "\tif err != nil {\n\t\tt.Fatal(err)\n\t}\n"
        '\tif !strings.Contains(string(page), "$") {\n\t\tt.Fatal("the page names no price")\n\t}\n'
        "}\n"
    ),
    "features/catalog/feature.json": json.dumps(
        {"name": "catalog", "description": "Catalog.", "docs": ["docs/prices.md"]}
    ),
    "features/catalog/docs/prices.md": "# prices\n\nA box costs $3.\n",
}


def go_runs():
    try:
        return subprocess.run(["go", "version"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


needs_go = pytest.mark.skipif(not go_runs(), reason="go is not installed, or does not run here")


@pytest.fixture
def go_repo(tmp_path, upstream):
    """A repo made from the skeleton and the go adapter, with the three features, and its env."""
    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("__pycache__", ".cache")
    shutil.copytree(SKELETON, root, ignore=ignore)
    shutil.copytree(ADAPTER, root, ignore=ignore, dirs_exist_ok=True)
    write(root, PLANTED)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(root, env, "generate")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from the skeleton")
    return root, env


def selected(root, env, base="HEAD"):
    return make(root, env, "-s", "select", f"BASE={base}").splitlines()


def change(root, path, text="\n"):
    with (root / path).open("a") as file:
        file.write(text)


@needs_go
def test_the_new_repo_of_several_modules_passes_its_own_check(go_repo):
    root, env = go_repo
    out = make(root, env, "check")
    for package in ("hello", "alpha/core", "alpha/extra", "beta/pricing", "beta/use"):
        assert f"ok  \texample.com/{package}" in out, out
    assert "conform repo-standard-v1" in out
    assert "errors 0" in out


@needs_go
def test_a_change_in_a_module_selects_it_and_each_module_that_takes_it(go_repo):
    root, env = go_repo
    change(root, "features/alpha/core/core.go", "\nconst More = 3\n")
    assert selected(root, env) == ALPHA + BETA
    out = make(root, env, "check-fast", "BASE=HEAD")
    assert "example.com/beta/use" in out
    assert "example.com/hello" not in out

    git(root, "checkout", "--", ".")
    change(root, "features/beta/use/use.go", "\nconst Triple = core.Value * 3\n")
    assert selected(root, env) == BETA


@needs_go
def test_a_file_a_test_reads_selects_the_features_that_read_it(go_repo):
    root, env = go_repo
    change(root, "features/catalog/docs/prices.md", "A bag costs $1.\n")
    assert selected(root, env) == BETA
    out = make(root, env, "check-fast", "BASE=HEAD")
    assert "ok  \texample.com/beta/pricing" in out


@needs_go
def test_check_fast_on_no_change_runs_no_test(go_repo):
    root, env = go_repo
    assert selected(root, env) == []
    assert "selects no test" in make(root, env, "check-fast", "BASE=HEAD")


@needs_go
@pytest.mark.parametrize(
    ("path", "selection"),
    [
        ("Makefile", ["all"]),
        ("scripts/go.py", ["all"]),
        ("notes.txt", ["all"]),
        ("features/catalog/data.csv", ["all"]),
        ("README.md", []),
        ("features/catalog/docs/other.md", []),
        ("features/hello/docs/hello.md", ["features/hello"]),
        ("features/alpha/go.mod", ALPHA + BETA),
    ],
)
def test_a_shared_or_unplaced_path_selects_all_and_a_page_outside_a_module_nothing(
    go_repo, path, selection
):
    root, env = go_repo
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    change(root, path)
    assert selected(root, env) == selection


@needs_go
def test_an_unformatted_file_fails_the_lint(go_repo):
    root, env = go_repo
    make(root, env, "lint")
    write(root, {"features/alpha/core/core.go": "package core\nconst Value=1\n"})
    out = make(root, env, "lint", ok=False)
    assert "features/alpha/core/core.go" in out


@needs_go
def test_make_test_runs_the_packages_it_is_given_and_fails_on_one_that_fails(go_repo):
    root, env = go_repo
    out = make(root, env, "test", "TESTS=features/alpha/extra features/beta/use")
    assert "ok  \texample.com/alpha/extra" in out
    assert "example.com/alpha/core" not in out
    write(root, {"features/alpha/extra/extra.go": "package extra\n\nconst Other = 5\n"})
    make(root, env, "test", "TESTS=features/alpha/extra features/beta/use", ok=False)


def test_the_go_config_differs_from_the_skeletons_only_in_the_stacks_parts():
    """The adapter's .repo-standard.yml replaces the skeleton's: its root files, and the size and
    comment limits over Go files. Every other part stays the skeleton's."""
    skeleton = parse((SKELETON / ".repo-standard.yml").read_text())
    adapter = parse((ADAPTER / ".repo-standard.yml").read_text())
    for config in (skeleton, adapter):
        del config["size"], config["comments"], config["owners"]["STACK"]
    assert adapter == skeleton
