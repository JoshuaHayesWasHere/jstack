"""The node-vite adapter, run as new repos made from the skeleton with a node stack.

`client_repo` makes a repo as `features/repo-standard/docs/skeleton.md` says for a node stack: it
copies the skeleton and the adapter's scripts, and its `.repo-standard.yml` declares one stack,
`client`, of the adapter `node-vite` over the folder `client/`. Two shapes of client are planted
there. `SVELTE` is shaped like Winnifred's: SvelteKit, `$lib`, `.svelte.ts` stores, a barrel, a
`vi.mock`, an `import.meta.glob`, a template `import()`, a test that reads a file, and a Vitest
setup file in the Vite config. `REACT` is shaped like LittleRamPantries': React, a
`vitest.config.ts` whose `include` leaves Playwright's `*.spec.ts` out, a setup file that
imports another, a tsconfig `paths` alias and a `.js` import of a `.ts` module.

Each package's `check` and `test` scripts are small node scripts that print what they were asked,
so the cases need node and npm and no install. A case of `hello_repo` runs the adapter's example
client for real, with Vitest and TypeScript installed by `npm ci` from its lockfile. The module
skips where npm does not run.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

import test_skeleton_python as skeleton
from repo_standard import TAG, VERSION
from repo_standard.adapters import COMMANDS
from repo_standard.config import Config, Stack, parse
from repo_standard.rules import Advice, Repo, make_targets
from test_skeleton_python import INHERITED, SKELETON, STANDARD, git, make, write
from testing.paths import REPO

ADAPTER = STANDARD / "adapters" / "node-vite"
WORKFLOW = REPO / ".github" / "workflows" / "repo-standard-check.yml"
upstream = skeleton.upstream


def npm_runs() -> bool:
    try:
        return subprocess.run(["npm", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not npm_runs(), reason="npm is not installed, or does not run")

STACK = """stacks:
  client:
    adapter: node-vite
    roots: [{root}]
"""
RUNNER = """import { existsSync } from 'node:fs';

const files = process.argv.slice(2);
for (const file of files) {
  if (!existsSync(file)) {
    console.error(`no test file ${file}`);
    process.exit(1);
  }
}
console.log(`vitest ran ${files.length ? files.join(' ') : 'every test'}`);
"""
CHECK = "console.log('check ran');\n"


def package(**extra):
    scripts = {"check": "node tools/check.mjs", "test": "node tools/vitest.mjs"}
    return json.dumps({"name": "client", "private": True, "scripts": scripts, **extra}) + "\n"


LOCK = '{"name": "client", "lockfileVersion": 3, "requires": true, "packages": {}}\n'
COMMON = {
    "client/package-lock.json": LOCK,
    "client/tools/vitest.mjs": RUNNER,
    "client/tools/check.mjs": CHECK,
    "client/README.md": "# client\n",
}
SVELTE = {
    **COMMON,
    "client/package.json": package(type="module"),
    "client/.nvmrc": "24\n",
    "client/svelte.config.js": "export default { kit: {} };\n",
    "client/tsconfig.json": (
        '{\n  // made by svelte-kit sync\n  "extends": "./.svelte-kit/tsconfig.json",\n}\n'
    ),
    "client/postcss.config.js": "export default {};\n",
    "client/tailwind.config.ts": "export default {};\n",
    "client/vite.config.ts": (
        "import { sveltekit } from '@sveltejs/kit/vite';\n"
        "import { defineConfig } from 'vitest/config';\n\n"
        "export default defineConfig({\n  plugins: [sveltekit()],\n"
        "  optimizeDeps: { include: ['date-fns'] },\n"
        "  test: { environment: 'jsdom', setupFiles: ['vitest.setup.ts'] },\n});\n"
    ),
    "client/vitest.setup.ts": "import './src/lib/testing/dom';\n",
    "client/src/lib/testing/dom.ts": "export const dom = true;\n",
    "client/src/app.html": "<html></html>\n",
    "client/static/favicon.png": "png\n",
    "client/src/lib/stores/toastStore.svelte.ts": "export const toasts = $state([]);\n",
    "client/src/lib/components/ui/Toast.svelte": (
        "<script lang=\"ts\">\n  import { toasts } from '$lib/stores/toastStore.svelte';\n"
        "</script>\n<p>{toasts.length}</p>\n<style>\n  @import './toast.css';\n</style>\n"
    ),
    "client/src/lib/components/ui/toast.css": "p { color: red; }\n",
    "client/src/lib/components/ui/Button.svelte": "<button><slot /></button>\n",
    "client/src/lib/components/ui/index.ts": (
        "export { default as Toast } from './Toast.svelte';\n"
        "export { default as Button } from './Button.svelte';\n"
    ),
    "client/src/lib/components/ui/Toast.test.ts": "import Toast from './Toast.svelte';\n",
    "client/src/lib/components/ui/Button.test.ts": "import Button from './Button.svelte';\n",
    "client/src/routes/+page.svelte": (
        "<script>\n  import { Toast } from '$lib/components/ui';\n  import { goto } from"
        " '$app/navigation';\n</script>\n<Toast />\n"
    ),
    "client/src/routes/home.test.ts": "import Page from './+page.svelte?raw';\n",
    "client/src/lib/services/api.ts": "export const get = () => 1;\n",
    "client/src/lib/components/care/Care.svelte": "<p>care</p>\n",
    "client/src/lib/components/care/care.test.ts": (
        "import { vi } from 'vitest';\nimport Care from './Care.svelte';\n\n"
        "vi.mock('$lib/services/api', () => ({ get: () => 2 }));\n"
    ),
    "client/src/lib/icons/heart.svg": "<svg/>\n",
    "client/src/lib/icons.ts": (
        "export const icons = import.meta.glob(['./icons/*.svg', '!./icons/skip-*.svg'],"
        " { query: '?raw' });\n"
    ),
    "client/src/lib/icons.test.ts": "import { icons } from '$lib/icons';\n",
    "client/src/lib/pages/about.ts": "export default 'about';\n",
    "client/src/lib/lazy.ts": "export const load = (name) => import(`./pages/${name}.ts`);\n",
    "client/src/lib/lazy.test.ts": "import { load } from './lazy.js';\n",
    "client/src/service-worker.ts": "self.addEventListener('push', () => {});\n",
    "client/src/service-worker.test.ts": (
        "import { readFileSync } from 'node:fs';\nimport { resolve } from 'node:path';\n\n"
        "const text = readFileSync(resolve(process.cwd(), 'src/service-worker.ts'), 'utf8');\n"
    ),
    "client/src/lib/utils/insulin.ts": "export const units = 2;\n",
    "client/src/lib/utils/insulin.test.ts": "import { units } from '$lib/utils/insulin';\n",
}
REACT = {
    **COMMON,
    "client/package.json": package(type="module", engines={"node": ">=22"}),
    "client/index.html": '<script type="module" src="/src/main.tsx"></script>\n',
    "client/postcss.config.js": "export default {};\n",
    "client/tsconfig.json": (
        '{\n  "compilerOptions": {\n    "jsx": "react-jsx",\n'
        '    "paths": { "@/*": ["./src/*"] },\n  },\n  "include": ["src"]\n}\n'
    ),
    "client/vite.config.ts": "export default {};\n",
    "client/vitest.config.ts": (
        "import { defineConfig, mergeConfig } from 'vitest/config';\n"
        "import viteConfig from './vite.config.ts';\n\n"
        "export default mergeConfig(viteConfig, defineConfig({\n  test: {\n"
        "    include: ['src/**/*.test.{ts,tsx}'],\n    setupFiles: ['./src/test/setup.ts'],\n"
        "    coverage: { include: ['src/**'] },\n  },\n}));\n"
    ),
    "client/src/test/setup.ts": "import { server } from './server';\n",
    "client/src/test/server.ts": "export const server = {};\n",
    "client/src/main.tsx": "import App from './App';\nimport './index.css';\n",
    "client/src/App.tsx": "import { PantryList } from '@/components/PantryList';\n",
    "client/src/index.css": ":root { color: black; }\n",
    "client/src/components/PantryList.tsx": (
        "import { hours } from '@/utils/hours';\nexport const PantryList = () => hours;\n"
    ),
    "client/src/components/PantryList.test.tsx": "import { PantryList } from './PantryList';\n",
    "client/src/components/Chart.tsx": "import { look } from './chartLook';\n",
    "client/src/components/chartLook.tsx": "export const look = 1;\n",
    "client/src/components/Chart.test.tsx": "import { Chart } from './Chart';\n",
    "client/src/utils/format.ts": "export const format = (n) => `${n}`;\n",
    "client/src/utils/hours.ts": "import { format } from './format.js';\nexport const hours = 1;\n",
    "client/src/utils/hours.test.ts": "import { hours } from './hours';\n",
    "client/src/tokens/tokens.test.ts": (
        "import { readFileSync } from 'node:fs';\n\n"
        "const css = readFileSync('src/index.css', 'utf8');\n"
    ),
    "client/e2e/home.spec.ts": "import { test } from '@playwright/test';\nimport '../src/App';\n",
}
SHAPES = {"svelte": SVELTE, "react": REACT}


def new_repo(tmp_path, upstream, files, root="client"):
    """A repo of one node stack over `root`, made from the skeleton and the adapter's scripts."""
    repo = tmp_path / "repo"
    shutil.copytree(SKELETON, repo, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    shutil.copytree(ADAPTER / "scripts", repo / "scripts", dirs_exist_ok=True)
    write(repo, files)
    top = root.split("/")[0]
    config = (repo / ".repo-standard.yml").read_text()
    if top != "features":
        config = config.replace("layout: [", f"layout: [{top}/, ")
    config = config.replace(
        "  STACK: [pyproject.toml, uv.lock, conftest.py]", f'  STACK: []\n  CLIENT: ["{root}/**"]'
    )
    config = config.replace("[scripts/stack.mk]", "[scripts/node.py]")
    (repo / ".repo-standard.yml").write_text(config + STACK.format(root=root))
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(repo, env, "generate")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start from the skeleton, with a client")
    return repo, env


@pytest.fixture(params=sorted(SHAPES))
def client_repo(request, tmp_path, upstream):
    return new_repo(tmp_path, upstream, SHAPES[request.param])


@pytest.fixture
def svelte_repo(tmp_path, upstream):
    return new_repo(tmp_path, upstream, SVELTE)


@pytest.fixture
def react_repo(tmp_path, upstream):
    return new_repo(tmp_path, upstream, REACT)


def selected(root, env):
    return make(root, env, "-s", "select", "BASE=HEAD").splitlines()


def change(root, path, text="\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    with (root / path).open("a") as file:
        file.write(text)


def test_each_shape_passes_conformance_and_runs_its_own_scripts(client_repo):
    root, env = client_repo
    out = make(root, env, "lint")
    assert "check ran" in out
    assert "warn a-change-selects-its-tests: stack client: sets no `e2e:`" in out
    assert "errors 0, warnings 1" in out
    assert "vitest ran every test" in make(root, env, "test")
    assert selected(root, env) == []


UI = "client/src/lib/components/ui"


@pytest.mark.parametrize(
    ("path", "selection"),
    [
        (f"{UI}/Button.svelte", [f"{UI}/Button.test.ts", "client/src/routes/home.test.ts"]),
        (f"{UI}/toast.css", [f"{UI}/Toast.test.ts", "client/src/routes/home.test.ts"]),
        (
            "client/src/lib/stores/toastStore.svelte.ts",
            [f"{UI}/Toast.test.ts", "client/src/routes/home.test.ts"],
        ),
        ("client/src/lib/services/api.ts", ["client/src/lib/components/care/care.test.ts"]),
        ("client/src/lib/icons/heart.svg", ["client/src/lib/icons.test.ts"]),
        ("client/src/lib/icons/skip-new.svg", ["client/src/lib/icons.test.ts"]),
        ("client/src/lib/pages/about.ts", ["client/src/lib/lazy.test.ts"]),
        ("client/src/service-worker.ts", ["client/src/service-worker.test.ts"]),
        ("client/src/lib/utils/insulin.test.ts", ["client/src/lib/utils/insulin.test.ts"]),
        ("client/package.json", ["stack:client"]),
        ("client/package-lock.json", ["stack:client"]),
        ("client/.nvmrc", ["stack:client"]),
        ("client/vite.config.ts", ["stack:client"]),
        ("client/svelte.config.js", ["stack:client"]),
        ("client/tsconfig.json", ["stack:client"]),
        ("client/postcss.config.js", ["stack:client"]),
        ("client/tailwind.config.ts", ["stack:client"]),
        ("client/vitest.setup.ts", ["stack:client"]),
        ("client/src/lib/testing/dom.ts", ["stack:client"]),
        ("client/tools/vitest.mjs", ["stack:client"]),
        ("client/static/favicon.png", ["stack:client"]),
        ("client/src/app.html", ["stack:client"]),
        ("client/README.md", []),
        ("Makefile", ["all"]),
        ("scripts/node_graph.py", ["all"]),
    ],
)
def test_a_svelte_change_selects_the_tests_that_reach_it(svelte_repo, path, selection):
    root, env = svelte_repo
    change(root, path)
    assert selected(root, env) == selection


@pytest.mark.parametrize(
    ("path", "selection"),
    [
        ("client/src/components/PantryList.tsx", ["client/src/components/PantryList.test.tsx"]),
        ("client/src/components/chartLook.tsx", ["client/src/components/Chart.test.tsx"]),
        (
            "client/src/utils/format.ts",
            ["client/src/components/PantryList.test.tsx", "client/src/utils/hours.test.ts"],
        ),
        ("client/src/index.css", ["client/src/tokens/tokens.test.ts"]),
        ("client/src/App.tsx", []),
        ("client/e2e/home.spec.ts", []),
        ("client/src/test/server.ts", ["stack:client"]),
        ("client/vitest.config.ts", ["stack:client"]),
        ("client/index.html", ["stack:client"]),
    ],
)
def test_a_react_change_selects_the_tests_that_reach_it(react_repo, path, selection):
    root, env = react_repo
    change(root, path)
    assert selected(root, env) == selection


def test_a_deleted_module_selects_the_tests_that_imported_it(react_repo):
    root, env = react_repo
    (root / "client/src/components/chartLook.tsx").unlink()
    assert selected(root, env) == ["client/src/components/Chart.test.tsx"]
    (root / "client/src/components/Chart.test.tsx").unlink()
    assert selected(root, env) == []


def test_make_test_runs_the_selected_files_from_the_root(react_repo):
    root, env = react_repo
    ids = "client/src/utils/hours.test.ts client/src/components/Chart.test.tsx"
    out = make(root, env, "test", f"TESTS={ids}")
    assert "vitest ran src/utils/hours.test.ts src/components/Chart.test.tsx" in out
    assert "vitest ran every test" in make(root, env, "test", "TESTS=stack:client")
    make(root, env, "test", "TESTS=client/src/gone.test.ts", ok=False)


def test_the_driver_runs_each_roots_own_scripts_and_only_the_roots_the_ids_reach(tmp_path):
    node = COMMANDS["node-vite"]
    roots = ("client", "admin")
    assert node.lint(roots) == [
        ["npm", "--prefix", "client", "run", "check"],
        ["npm", "--prefix", "admin", "run", "check"],
    ]
    for root in roots:
        write(tmp_path, {f"{root}/{name.split('/', 1)[1]}": text for name, text in COMMON.items()})
        write(tmp_path, {f"{root}/package.json": package(), f"{root}/src/a.test.ts": ""})
    write(tmp_path, {"client/b.test.ts": ""})
    shutil.copytree(ADAPTER / "scripts", tmp_path / "scripts", dirs_exist_ok=True)

    def ran(ids):
        argv = [arg.replace("python3", sys.executable, 1) for arg in node.test(roots, ids)[0]]
        done = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        return [line for line in done.stdout.splitlines() if line.startswith("vitest ran")]

    assert ran([]) == ["vitest ran every test"] * 2
    assert ran(["client/src/a.test.ts", "client/b.test.ts"]) == [
        "vitest ran src/a.test.ts b.test.ts"
    ]
    assert ran(["admin/src/a.test.ts"]) == ["vitest ran src/a.test.ts"]
    assert node.select(roots, "HEAD", None) == [
        "python3",
        "scripts/node.py",
        "select",
        "--roots",
        "client",
        "--roots",
        "admin",
        "HEAD",
    ]


def test_conform_holds_each_node_root_to_its_scripts_and_its_node_version(tmp_path):
    files = {
        "Makefile": "lint:\n\ntest:\n\ncheck:\n",
        "pinned/package.json": package(engines={"node": "24"}),
        "nvm/package.json": package(),
        "nvm/.nvmrc": "24\n",
        "bare/package.json": json.dumps({"scripts": {"check": " "}}),
        "broken/package.json": "{",
    }
    write(tmp_path, files)
    roots = ("pinned", "nvm", "bare", "broken")
    config = Config(stacks={"web": Stack("node-vite", roots), "api": Stack("go", ("api",))})
    faults = make_targets(Repo(tmp_path, config, sorted(files)))
    assert faults == [
        "bare/package.json: has no `check` script, which `make lint` runs",
        "bare/package.json: has no `test` script, which `make test` runs",
        "bare: pins no Node version, in `.nvmrc` or package.json `engines.node`, so CI runs the"
        " runner's Node",
        "broken/package.json: is not there, or is not a JSON object, so the stack has no scripts",
    ]
    assert [isinstance(one, Advice) for one in faults] == [False, False, True, False]


def test_a_failing_check_script_fails_the_lint(svelte_repo):
    root, env = svelte_repo
    write(root, {"client/tools/check.mjs": "process.exit(1);\n"})
    make(root, env, "lint", ok=False)


@pytest.mark.parametrize("script", ["check", "test"])
def test_conform_fails_a_package_with_no_check_or_test_script(svelte_repo, script):
    root, env = svelte_repo
    package_json = json.loads((root / "client/package.json").read_text())
    package_json["scripts"][f"{script}:all"] = package_json["scripts"].pop(script)
    write(root, {"client/package.json": json.dumps(package_json)})
    git(root, "commit", "-qam", f"no {script} script")
    out = skeleton_conform(root, env, ok=False)
    assert f"error each-check-has-one-make-target: client/package.json: has no `{script}`" in out


def test_conform_warns_of_a_node_stack_that_pins_no_node_version(svelte_repo):
    root, env = svelte_repo
    git(root, "rm", "-q", "client/.nvmrc")
    git(root, "commit", "-qm", "no Node version")
    out = skeleton_conform(root, env)
    assert "warn each-check-has-one-make-target: client: pins no Node version" in out
    assert "errors 0, warnings 2" in out


def skeleton_conform(root, env, ok=True):
    make(root, env, "-s", f".cache/{TAG}{VERSION}")
    pythonpath = root / f".cache/{TAG}{VERSION}/features/repo-standard/src"
    done = subprocess.run(
        ["python3", "-m", "repo_standard", "conform"],
        cwd=root,
        env={**env, "PYTHONPATH": str(pythonpath)},
        capture_output=True,
        text=True,
    )
    assert (done.returncode == 0) == ok, done.stdout + done.stderr
    return done.stdout


@pytest.mark.parametrize(
    ("planted", "version_file"),
    [
        ({"client/.nvmrc": "24\n"}, "client/.nvmrc"),
        ({"client/package.json": package(engines={"node": "24"})}, "client/package.json"),
        ({"client/package.json": package()}, ""),
    ],
)
def test_setup_names_each_npm_root_and_the_node_version_file(tmp_path, planted, version_file):
    write(tmp_path, {"client/package.json": package(), **COMMON, **planted})
    write(tmp_path, {"e2e/package.json": package(), "e2e/package-lock.json": LOCK})
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    done = subprocess.run(
        ["python3", str(ADAPTER / "scripts" / "node.py"), "setup"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.splitlines() == ["roots=client e2e", f"version-file={version_file}"]


def test_the_setup_action_installs_node_from_the_version_file_and_each_root():
    steps = parse((ADAPTER / ".github/actions/setup/action.yml").read_text())["runs"]["steps"]
    found, node, install = steps
    assert found["run"] == 'python3 scripts/node.py setup >> "$GITHUB_OUTPUT"'
    assert node["uses"].startswith("actions/setup-node@")
    assert node["with"] == {
        "node-version-file": "${{ steps.node.outputs.version-file }}",
        "cache": "npm",
        "cache-dependency-path": "**/package-lock.json",
    }
    assert install["env"] == {"ROOTS": "${{ steps.node.outputs.roots }}"}
    assert "npm ci" in install["run"]


def test_the_shared_check_selects_before_any_setup():
    steps = parse(WORKFLOW.read_text())["jobs"]["plan"]["steps"]
    names = [step.get("name") for step in steps]
    assert "select" in names
    assert not any("setup" in step.get("uses", "") for step in steps)


@pytest.fixture
def hello_repo(tmp_path, upstream):
    """A repo of the skeleton and the adapter, its example client a node stack, installed."""
    root = tmp_path / "repo"
    shutil.copytree(SKELETON, root, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    shutil.copytree(ADAPTER, root, dirs_exist_ok=True)
    repo, env = root, {k: v for k, v in os.environ.items() if k not in INHERITED}
    config = (root / ".repo-standard.yml").read_text()
    config = config.replace("  STACK: [pyproject.toml, uv.lock, conftest.py]", "  STACK: []")
    config = config.replace("[scripts/stack.mk]", "[scripts/node.py]")
    (root / ".repo-standard.yml").write_text(config + STACK.format(root="features/hello-client"))
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(repo, env, "generate")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start from the skeleton, with its example client")
    subprocess.run(
        ["npm", "ci", "--no-audit", "--no-fund"],
        cwd=root / "features/hello-client",
        check=True,
        capture_output=True,
        timeout=300,
    )
    return repo, env


def test_the_example_client_passes_its_check_and_selects_its_test(hello_repo):
    root, env = hello_repo
    out = make(root, env, "check")
    assert "errors 0" in out
    assert "1 passed" in out
    change(root, "features/hello-client/src/greet.ts", "export const loud = true;\n")
    assert selected(root, env) == ["features/hello-client/src/greet.test.ts"]
    out = make(root, env, "test", "TESTS=features/hello-client/src/greet.test.ts")
    assert "1 passed" in out


def test_vitests_report_names_the_failed_test_file_from_the_repos_root(hello_repo, tmp_path):
    root, env = hello_repo
    broken = "features/hello-client/src/broken.test.ts"
    write(root, {broken: "import { expect, test } from 'vitest';\n\ntest('breaks', () => {\n"})
    with (root / broken).open("a") as file:
        file.write("  expect(1).toBe(2);\n});\n")
    failed = tmp_path / "failed.txt"
    out = make(root, {**env, "REPO_STANDARD_FAILED": str(failed)}, "test", ok=False)
    assert "1 failed" in out
    assert "1 passed" in out
    assert failed.read_text().splitlines() == [broken]
