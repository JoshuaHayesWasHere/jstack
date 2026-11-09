"""`make test SHARD=<part>/<parts>`, the shared check's run of a part dealt the whole suite.

Each case makes a repo from the skeleton, as `features/repo-standard/docs/skeleton.md` says, whose
tests each write their id to the file `$SHARD_LOG`, so the log shows what ran. `new_repo`, from
test_skeleton_python, is a repo of one stack, python-uv, through `scripts/stack.mk`. `three_stacks`
is a repo with `shards: 2` and `stacks:`: a Go stack, a python-uv stack and a node-vite stack,
whose `npm test` is a small node script that logs the files it is given, so it needs node and npm
and no install. A part runs the ids the stacks list, dealt to the parts in turn, so across the
parts each test runs once.
"""

import json
import os
import shutil

import pytest

import test_skeleton_python as skeleton
from test_go_adapter import needs_go
from test_node_adapter import npm_runs
from test_skeleton_python import INHERITED, SKELETON, STANDARD, git, make, write

upstream = skeleton.upstream
new_repo = skeleton.new_repo
ADAPTERS = STANDARD / "adapters"
UV = ADAPTERS / "python-uv"
LOGGED = 'import os\n\n\ndef test_{name}():\n    with open(os.environ["SHARD_LOG"], "a") as log:\n'
LOGGED += '        log.write("{id}\\n")\n'


def logged_python(path):
    name = path.rsplit("/", 1)[-1].removesuffix(".py").removeprefix("test_")
    return {path: LOGGED.format(name=name, id=path)}


def logged_go(package):
    name = package.rsplit("/", 1)[-1]
    return {
        f"{package}/{name}.go": f"package {name}\n",
        f"{package}/{name}_test.go": (
            f'package {name}\n\nimport (\n\t"os"\n\t"testing"\n)\n\n'
            "func TestLog(t *testing.T) {\n"
            '\tlog, err := os.OpenFile(os.Getenv("SHARD_LOG"), os.O_APPEND|os.O_WRONLY, 0)\n'
            "\tif err != nil {\n\t\tt.Fatal(err)\n\t}\n\tdefer log.Close()\n"
            f'\tif _, err := log.WriteString("{package}\\n"); err != nil {{\n'
            "\t\tt.Fatal(err)\n\t}\n}\n"
        ),
    }


def ran(log):
    """Each id the log holds, in the order the tests ran, and empties the log."""
    lines = log.read_text().splitlines()
    log.write_text("")
    return lines


SUITE = [f"features/alpha/tests/test_{one}.py" for one in "abcd"]


@pytest.fixture
def one_stack(new_repo, tmp_path):
    root, env = new_repo
    (root / "features/hello/tests/test_hello.py").unlink()
    for path in SUITE:
        write(root, logged_python(path))
    log = tmp_path / "shard.log"
    log.write_text("")
    return root, {**env, "SHARD_LOG": str(log)}, log


def test_the_parts_of_one_stack_run_each_test_once(one_stack):
    root, env, log = one_stack
    make(root, env, "test", "SHARD=1/2")
    assert ran(log) == SUITE[0::2]
    make(root, env, "test", "SHARD=2/2")
    assert ran(log) == SUITE[1::2]

    make(root, env, "test")
    assert sorted(ran(log)) == SUITE


def test_a_part_dealt_no_id_runs_nothing_and_a_bad_shard_fails(one_stack):
    root, env, log = one_stack
    out = make(root, env, "test", "SHARD=5/5")
    assert "dealt no test" in out
    assert ran(log) == []
    for bad in ("0/2", "3/2", "1", "a/b"):
        make(root, env, "test", f"SHARD={bad}", ok=False)
    assert ran(log) == []


PROBE = """import json
import os
import subprocess


def test_probe():
    inner = subprocess.run(
        ["make", "-s", "-f", "-"],
        input="all:\\n\\t@echo 'SHARD=$(SHARD) TESTS=$(TESTS)'\\n",
        capture_output=True,
        text=True,
    )
    with open(os.environ["PROBE_LOG"], "w") as log:
        json.dump({"env": dict(os.environ), "inner": inner.stdout + inner.stderr}, log)
"""


@pytest.mark.parametrize(
    "line", [["SHARD=1/1"], ["TESTS=features/probe/tests/test_probe.py", "SHARD=1/2"]]
)
def test_a_test_and_a_make_it_runs_see_neither_shard_nor_tests(new_repo, tmp_path, line):
    root, env = new_repo
    write(root, {"features/probe/tests/test_probe.py": PROBE})
    probe = tmp_path / "probe.json"
    make(root, {**env, "PROBE_LOG": str(probe)}, "test", *line)
    seen = json.loads(probe.read_text())
    assert "SHARD" not in seen["env"]
    assert "TESTS" not in seen["env"]
    assert "SHARD" not in seen["env"].get("MAKEFLAGS", "")
    assert "TESTS" not in seen["env"].get("MAKEFLAGS", "")
    assert seen["inner"] == "SHARD= TESTS=\n"


GO_IDS = ["api/handlers", "api/store"]
CAPTURE_IDS = ["tools/capture/tests/test_a.py", "tools/capture/tests/test_b.py"]
CLIENT_IDS = ["client/src/a.test.ts", "client/src/b.test.ts"]
STACKS = """check:
  shards: 2
stacks:
  api:
    adapter: go
    roots: [api]
  capture:
    adapter: python-uv
    roots: [tools/capture]
  client:
    adapter: node-vite
    roots: [client]
"""
RUNNER = """import { appendFileSync, readdirSync } from 'node:fs';

const given = process.argv.slice(2);
const files = given.length ? given : readdirSync('src').map((name) => `src/${name}`);
for (const file of files.filter((name) => name.endsWith('.test.ts'))) {
  appendFileSync(process.env.SHARD_LOG, `client/${file}\\n`);
}
"""
CLIENT = {
    "client/package.json": json.dumps(
        {
            "name": "client",
            "private": True,
            "type": "module",
            "scripts": {"check": "node -e 0", "test": "node tools/vitest.mjs"},
        }
    ),
    "client/package-lock.json": '{"name": "client", "lockfileVersion": 3, "packages": {}}\n',
    "client/tools/vitest.mjs": RUNNER,
    "client/src/greet.ts": "export const greet = (name: string) => `hello, ${name}`;\n",
    "client/src/a.test.ts": "import { greet } from './greet';\n",
    "client/src/b.test.ts": "import { greet } from './greet';\n",
}
PYTEST = '\n[tool.pytest.ini_options]\naddopts = "-q"\n'


@pytest.fixture
def three_stacks(tmp_path, upstream):
    """A repo of a Go, a python-uv and a node-vite stack, its env, and the log its tests write."""
    root = tmp_path / "repo"
    shutil.copytree(SKELETON, root, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    for script in ("go/scripts/go.py", "python-uv/scripts/select.py"):
        shutil.copy(ADAPTERS / script, root / "scripts")
    shutil.copytree(ADAPTERS / "node-vite" / "scripts", root / "scripts", dirs_exist_ok=True)
    write(root, {"api/go.mod": "module example.com/api\n\ngo 1.24\n", **CLIENT})
    for package in GO_IDS:
        write(root, logged_go(package))
    for path in CAPTURE_IDS:
        write(root, logged_python(path))
    capture = root / "tools" / "capture"
    shutil.copy(UV / "uv.lock", capture / "uv.lock")
    project = (UV / "pyproject.toml").read_text()
    (capture / "pyproject.toml").write_text(project.split("[tool.pytest")[0] + PYTEST)
    (root / ".repo-standard.yml").write_text((root / ".repo-standard.yml").read_text() + STACKS)
    log = tmp_path / "shard.log"
    log.write_text("")
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env.update(REPO_STANDARD_UPSTREAM=str(upstream), SHARD_LOG=str(log), GOFLAGS="-count=1")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from the skeleton, with three stacks")
    return root, env, log


@needs_go
@pytest.mark.skipif(not npm_runs(), reason="npm is not installed, or does not run")
def test_the_parts_of_three_stacks_run_each_test_once(three_stacks):
    root, env, log = three_stacks
    suite = [*GO_IDS, *CAPTURE_IDS, *CLIENT_IDS]
    make(root, env, "test", "SHARD=1/2")
    first = ran(log)
    make(root, env, "test", "SHARD=2/2")
    second = ran(log)
    assert sorted(first) == sorted(suite[0::2])
    assert sorted(second) == sorted(suite[1::2])

    make(root, env, "test")
    assert sorted(ran(log)) == sorted(suite)


@needs_go
@pytest.mark.skipif(not npm_runs(), reason="npm is not installed, or does not run")
def test_each_stack_writes_the_ids_that_failed_from_the_repos_root(three_stacks, tmp_path):
    root, env, _ = three_stacks
    write(
        root,
        {
            "api/handlers/fail_test.go": (
                'package handlers\n\nimport "testing"\n\n'
                'func TestFail(t *testing.T) {\n\tt.Fatal("no")\n}\n'
            ),
            "tools/capture/tests/test_broken.py": "def test_broken():\n    assert False\n",
            "client/tools/vitest.mjs": "process.exit(1);\n",
        },
    )
    failed = tmp_path / "failed.txt"
    make(root, {**env, "REPO_STANDARD_FAILED": str(failed)}, "test", ok=False)
    assert sorted(failed.read_text().splitlines()) == [
        "api/handlers",
        *CLIENT_IDS,
        "tools/capture/tests/test_broken.py",
    ]
