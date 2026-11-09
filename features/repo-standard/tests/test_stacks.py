"""`repo-standard stacks`, the driver of a repo of several stacks, run in this process.

`test_multi_stack.py` runs the driver as the skeleton's Makefile does, from a clone of the
standard. These cases call `repo_standard.cli.main` on the same repo, a Go stack `api` and a
python-uv stack `capture`, so the driver's own lines run here. They check what `make` cannot
reach: an id or a base the driver refuses, a stack whose select fails, a tool that is not
installed, and the config's refusal of each `stacks:` it cannot hold.
"""

import json
import os
import re
import shutil
import sys

import pytest

import test_multi_stack
from repo_standard import cli, stacks
from repo_standard.adapters import COMMANDS
from repo_standard.config import E2E, Config, Refused, Stack, Table, build, parse
from test_go_adapter import needs_go
from test_multi_stack import STACKS
from test_skeleton_python import STANDARD, git, write

stacked_repo = test_multi_stack.stacked_repo
upstream = test_multi_stack.upstream


def change(root, path, text="\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    with (root / path).open("a") as file:
        file.write(text)


@pytest.fixture
def here(stacked_repo, monkeypatch):
    """The repo of two stacks as the working directory, with a clean env for its tools."""
    root, _ = stacked_repo
    monkeypatch.chdir(root)
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "MAKEFLAGS"):
        monkeypatch.delenv(name, raising=False)
    return root


def selection(capsys, base="HEAD"):
    capsys.readouterr()
    assert cli.main(["stacks", "select", base]) == 0
    return capsys.readouterr().out.splitlines()


@needs_go
def test_the_driver_lints_tests_and_routes_each_stack(here, capfd):
    assert cli.main(["stacks", "lint"]) == 0
    assert cli.main(["stacks", "test"]) == 0
    capfd.readouterr()
    assert cli.main(["stacks", "test", "stack:capture", "./api/handlers"]) == 0
    out = capfd.readouterr().out
    assert "example.com/api/handlers" in out
    assert "example.com/api/store" not in out
    assert "2 passed" in out

    assert cli.main(["stacks", "test", "tools/capture/tests/test_main.py"]) == 0
    out = capfd.readouterr().out
    assert "1 passed" in out
    assert "example.com/api" not in out


@needs_go
@pytest.mark.parametrize(
    ("path", "selected"),
    [
        ("api/store/store.go", ["api/handlers", "api/store"]),
        ("tools/capture/uv.lock", ["stack:capture"]),
        ("Makefile", ["all"]),
        ("notes.txt", ["all"]),
        ("features/hello/docs/hello.md", []),
    ],
)
def test_the_driver_joins_each_stacks_selection(here, capsys, path, selected):
    change(here, path)
    assert selection(capsys) == selected


@needs_go
def test_the_driver_refuses_what_it_cannot_run_and_exits_2(here, capsys, monkeypatch, tmp_path):
    assert cli.main(["stacks", "test", "nowhere/at/all"]) == 2
    assert cli.main(["stacks", "test", "stack:nothing"]) == 2
    assert cli.main(["stacks", "select"]) == 2
    assert cli.main(["stacks", "select", "no-such-ref"]) == 2
    assert "git cannot read the change" in capsys.readouterr().err
    assert stacks.main(here, Config(), ["lint"]) == 2

    git(here, "rm", "-q", "scripts/go.py")
    git(here, "commit", "-qm", "the go adapter's script is gone")
    assert cli.main(["stacks", "select", "HEAD"]) == 2
    assert "the select of stack api failed" in capsys.readouterr().err

    tools = tmp_path / "bin"
    tools.mkdir()
    for name, found in (("git", shutil.which("git")), ("python3", sys.executable)):
        (tools / name).symlink_to(found)
    monkeypatch.setenv("PATH", str(tools))
    assert cli.main(["stacks", "lint"]) == 2
    assert "uv is not installed" in capsys.readouterr().err


def test_the_driver_outside_a_checkout_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert cli.main(["stacks", "lint"]) == 2
    assert "not in a git checkout" in capsys.readouterr().err


def test_the_config_reads_each_stack_with_its_roots():
    assert build(parse(STACKS)).stacks == {
        "api": Stack("go", ("api",)),
        "capture": Stack("python-uv", ("tools/capture",)),
    }


@pytest.mark.parametrize(
    ("stacks_part", "said"),
    [
        ("stacks: [api]", "is not a map"),
        ("stacks:\n  a b:\n    adapter: go\n    roots: [a]", "is not a name"),
        ("stacks:\n  a:\n    adapter: node\n    roots: [a]", "not one of go, python-uv"),
        ("stacks:\n  a:\n    adapter: go\n    roots: []", "names no folder"),
        ("stacks:\n  a:\n    adapter: go", "names no folder"),
        ("stacks:\n  a:\n    adapter: go\n    roots: [../a]", "not a folder of the repo"),
        ("stacks:\n  a:\n    adapter: go\n    roots: [/a]", "not a folder of the repo"),
        (
            "stacks:\n  a:\n    adapter: go\n    roots: [api]\n"
            "  b:\n    adapter: go\n    roots: [api/x]",
            "inside or around api of a",
        ),
        (
            "stacks:\n  a:\n    adapter: go\n    roots: [x/y]\n"
            "  b:\n    adapter: go\n    roots: [x]",
            "inside or around x/y of a",
        ),
        (
            "stacks:\n  a:\n    adapter: go\n    roots: [.]\n"
            "  b:\n    adapter: python-uv\n    roots: [tools]",
            "inside or around . of a",
        ),
    ],
)
def test_the_config_refuses_a_stacks_part_it_cannot_hold(stacks_part, said):
    with pytest.raises(Refused, match=said.replace(".", r"\.")):
        build(parse(stacks_part))


NODE = "stacks:\n  web:\n    adapter: node-vite\n    roots: [web, e2e]\n    e2e:\n"


def test_the_config_reads_a_node_stacks_browser_tests():
    e2e = (
        build(
            parse(
                NODE + "      root: e2e/\n      script: test:e2e\n"
                "      every: [e2e/layout.spec.ts]\n"
                "      routes:\n        e2e/a.spec.ts: [/pets, /pets/1]\n"
                "      table:\n        - file: e2e/screens.spec.ts\n          export: screenFlows\n"
                '          title: "screen: {name}"\n'
            )
        )
        .stacks["web"]
        .e2e
    )
    assert e2e == E2E(
        "e2e",
        "test:e2e",
        ("e2e/layout.spec.ts",),
        {"e2e/a.spec.ts": ("/pets", "/pets/1")},
        (Table("e2e/screens.spec.ts", "screenFlows", "screen: {name}"),),
    )


@pytest.mark.parametrize(
    ("e2e", "said"),
    [
        ("      root: other\n      script: e2e", "e2e.root is other, outside the stack's roots"),
        ("      root: ../e2e\n      script: e2e", "outside the stack's roots"),
        ("      root: e2e\n      script: e2e\n      grep: x", "has grep, which the standard"),
        ("      root: e2e", "names no npm script"),
        ("      root: e2e\n      script: e2e\n      every: [x.spec.ts]", "outside the stack's"),
        ("      root: [e2e]\n      script: e2e", "e2e.root is not a path"),
        ("      root: e2e\n      script: e2e\n      table: x", "is not a list of `file`"),
        (
            "      root: e2e\n      script: e2e\n      table:\n        - file: e2e/a.spec.ts\n"
            "          export: 1flows\n          title: '{name}'",
            "export is not the name of an array",
        ),
        ("      root: e2e\n      script: e2e\n      routes:\n        e2e/a.ts: [pets]", "not a"),
        (
            "      root: e2e\n      script: e2e\n      table:\n        - file: e2e/a.spec.ts\n"
            "          export: flows\n          title: screen",
            "has no {name}",
        ),
        (
            "      root: e2e\n      script: e2e\n      table:\n        - file: e2e/a.spec.ts\n"
            "          export: flows\n          title: '{name}'\n          path: x",
            "has path, which the standard",
        ),
    ],
)
def test_the_config_refuses_an_e2e_part_it_cannot_hold(e2e, said):
    with pytest.raises(Refused, match=re.escape(said)):
        build(parse(NODE + e2e + "\n"))


def test_only_a_node_stack_runs_browser_tests():
    with pytest.raises(Refused, match="only a node-vite stack runs one"):
        build(parse("stacks:\n  a:\n    adapter: go\n    roots: [a]\n    e2e:\n      root: a\n"))


def test_a_v1_config_has_no_stack():
    assert build(parse("standard: 1\n")).stacks == {}


def test_each_script_an_adapter_runs_ships_in_that_adapters_folder():
    """A repo copies an adapter's folder, so a script the registry runs that the folder lacks
    would leave the driver running nothing there."""
    for name, commands in COMMANDS.items():
        for script in commands.scripts:
            assert (STANDARD / "adapters" / name / script).is_file(), f"{name}: {script}"


NPM = """#!/bin/sh
echo "npm $*"
while [ $# -gt 0 ]; do
  if [ "$1" = --test-list ]; then cat "$2"; fi
  shift
done
[ -z "$NPM_FAILS" ]
"""
WEB = {
    ".repo-standard.yml": (
        "standard: 1\nstacks:\n  web:\n    adapter: node-vite\n    roots: [web]\n"
        "    e2e:\n      root: web\n      script: test:e2e\n"
    ),
    "web/package.json": json.dumps(
        {"name": "web", "scripts": {"check": "x", "test": "x", "test:e2e": "playwright test"}}
    ),
    "web/package-lock.json": "{}\n",
    "web/playwright.config.ts": "export default { testDir: './e2e' };\n",
    "web/src/routes/+page.svelte": "<p>home</p>\n",
    "web/src/routes/pets/+page.svelte": "<p>pets</p>\n",
    "web/e2e/home.spec.ts": "test('home', async ({ page }) => page.goto('/'));\n",
    "web/e2e/pets.spec.ts": "test('pets', async ({ page }) => page.goto('/pets'));\n",
}


@pytest.fixture
def web(tmp_path, monkeypatch):
    """A repo of one node stack, `web`, with browser tests, as the working directory, and an `npm`
    that prints what it was asked and the test list it was given."""
    root = tmp_path / "repo"
    write(root, WEB)
    shutil.copytree(STANDARD / "adapters/node-vite/scripts", root / "scripts")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a node stack with browser tests")
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "npm").write_text(NPM)
    (tools / "npm").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    monkeypatch.delenv("NPM_FAILS", raising=False)
    monkeypatch.chdir(root)
    return root


def test_the_driver_selects_a_node_stacks_browser_tests(web, capsys):
    change(web, "web/src/routes/pets/+page.svelte")
    assert selection(capsys) == ["web/e2e/pets.spec.ts"]


def test_the_driver_runs_every_browser_test_or_the_listed_ones(web, capfd, tmp_path):
    assert cli.main(["stacks", "e2e"]) == 0
    assert "npm --prefix web run test:e2e -- --fail-on-flaky-tests\n" in capfd.readouterr().out
    listed = tmp_path / "ids.txt"
    listed.write_text("web/e2e/pets.spec.ts > pets\nweb/e2e/home.spec.ts\n")
    assert cli.main(["stacks", "e2e", str(listed)]) == 0
    out = capfd.readouterr().out
    assert "--fail-on-flaky-tests --test-list" in out
    assert out.endswith("pets.spec.ts > pets\nhome.spec.ts\n")
    listed.write_text("stack:web\n")
    assert cli.main(["stacks", "e2e", str(listed)]) == 0
    assert "--test-list" not in capfd.readouterr().out


def test_a_failing_browser_test_fails_the_driver(web, monkeypatch):
    monkeypatch.setenv("NPM_FAILS", "1")
    assert cli.main(["stacks", "e2e"]) == 1


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["e2e", "nowhere.txt"], "cannot read nowhere.txt"),
        (["e2e", "ids.txt"], "is under no stack's roots"),
        (["e2e", "a", "b"], "usage:"),
    ],
)
def test_the_driver_refuses_a_browser_run_it_cannot_make(web, capsys, argv, said):
    (web / "ids.txt").write_text("api/e2e/a.spec.ts\n")
    assert cli.main(["stacks", *argv]) == 2
    assert said in capsys.readouterr().err


def test_a_config_with_no_browser_tests_has_none_to_run(web, capsys):
    config = build(parse("stacks:\n  web:\n    adapter: node-vite\n    roots: [web]\n"))
    assert stacks.main(web, config, ["e2e"]) == 2
    assert "no stack of the config sets `e2e:`" in capsys.readouterr().err
