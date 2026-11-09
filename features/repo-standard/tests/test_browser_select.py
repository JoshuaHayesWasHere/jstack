"""The browser tests a change selects, run as a new repo made from the skeleton with a node stack.

`browser_repo` makes a repo as `features/repo-standard/docs/skeleton.md` says for a node stack
with `e2e:`: one stack, `client`, over `client/`, whose `test:e2e` script runs Playwright on
`playwright.config.ts`, with a `setup` project the `screens` project depends on. `APP` is shaped
like Winnifred's client. A root layout imports `Toast` from the barrel `$lib/components/ui` and
the global CSS, which `@import`s a second sheet. The pages `/pets` and `/calendar` each import one
component from the same barrel, and the pages `/about` and `/help` are opened by the rows of the
table spec `screens.spec.ts`, as Winnifred's `screenFlows` are. Each of `pets.spec.ts` and
`calendar.spec.ts` opens its page. `offline.spec.ts` allows the service worker, which the config
blocks for every other spec.

The cases run `make select` and read its ids, the way the shared check does. One case installs
Playwright from a lockfile and has it list what `--test-list` selects, so the ids are proven in
Playwright's own form. The module skips where npm does not run.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

from repo_standard import rules
from repo_standard.config import load
from test_node_adapter import ADAPTER, CHECK, RUNNER, change, npm_runs, skeleton_conform
from test_skeleton_python import INHERITED, SKELETON, git, make, write

pytestmark = pytest.mark.skipif(not npm_runs(), reason="npm is not installed, or does not run")
upstream = __import__("test_skeleton_python").upstream

STACK = """stacks:
  client:
    adapter: node-vite
    roots: [client]
    e2e:
      root: client
      script: test:e2e
      mock:
        path: client/e2e/mock-api.ts
        contract: "true"
      table:
        - file: client/e2e/screens.spec.ts
          export: screenFlows
          title: "screen: {name}"
"""
PLAYWRIGHT = "1.64.1"
LOCK = {
    "name": "client",
    "lockfileVersion": 3,
    "requires": True,
    "packages": {
        "": {"name": "client", "devDependencies": {"@playwright/test": PLAYWRIGHT}},
        "node_modules/@playwright/test": {
            "version": PLAYWRIGHT,
            "resolved": f"https://registry.npmjs.org/@playwright/test/-/test-{PLAYWRIGHT}.tgz",
            "integrity": "sha512-IaYGml/nSOiZWROfPtuIL7neuu9qDOZ3TNvNljUIrhDMxiGTgPjzj/g9p9Rx"
            "pS2tSepPDRY+UwAaEeiKtUvIAg==",
            "dev": True,
            "dependencies": {"playwright": PLAYWRIGHT},
            "bin": {"playwright": "cli.js"},
        },
        "node_modules/playwright": {
            "version": PLAYWRIGHT,
            "resolved": f"https://registry.npmjs.org/playwright/-/playwright-{PLAYWRIGHT}.tgz",
            "integrity": "sha512-HCrVhHr5QQuwYoswEUGTb7gGp522yflbv/ST8nF4sFWGuLjQCt17Q/EubpGG"
            "SNKYn1tsTCPZxqHhHCfVURu7UA==",
            "dev": True,
            "dependencies": {"playwright-core": PLAYWRIGHT},
            "bin": {"playwright": "cli.js"},
        },
        "node_modules/playwright-core": {
            "version": PLAYWRIGHT,
            "resolved": f"https://registry.npmjs.org/playwright-core/-/playwright-core-{PLAYWRIGHT}.tgz",
            "integrity": "sha512-BC4s8y6SEVA6Q1rSxZTto8hI1KUI3xXlHGZgvGqP4IqPdI/a6FX9H29IDNz7"
            "vKo9l21b6LfYosScPL6M3xxyDQ==",
            "dev": True,
            "bin": {"playwright-core": "cli.js"},
        },
    },
}
PACKAGE = {
    "name": "client",
    "private": True,
    "type": "module",
    "scripts": {
        "check": "node tools/check.mjs",
        "test": "node tools/vitest.mjs",
        "test:e2e": "playwright test",
    },
    "devDependencies": {"@playwright/test": PLAYWRIGHT},
}
UI = "client/src/lib/components/ui"
E2E = "client/e2e"
APP = {
    "client/package.json": json.dumps(PACKAGE, indent=2) + "\n",
    "client/package-lock.json": json.dumps(LOCK, indent=2) + "\n",
    "client/.nvmrc": "24\n",
    "client/tools/vitest.mjs": RUNNER,
    "client/tools/check.mjs": CHECK,
    "client/svelte.config.js": "export default { kit: {} };\n",
    "client/vite.config.ts": "export default { test: { environment: 'jsdom' } };\n",
    "client/src/app.html": "<html></html>\n",
    "client/src/app.css": "@import './tokens.css';\n",
    "client/src/tokens.css": ":root { --ink: black; }\n",
    "client/static/favicon.png": "png\n",
    "client/src/service-worker.ts": "import { saved } from './lib/offline';\nsaved();\n",
    "client/src/lib/offline.ts": "export const saved = () => 1;\n",
    "client/src/service-worker.test.ts": "import './service-worker';\n",
    f"{UI}/index.ts": (
        "// The components every screen shares.\n"
        "export { default as Toast } from './Toast.svelte';\n"
        "export { default as PetCard } from './PetCard.svelte';\n"
        "export { default as CalendarGrid } from './CalendarGrid.svelte';\n"
        "export { default as Badge } from './Badge.svelte';\n"
        "export { default as Tooltip } from './Tooltip.svelte';\n"
    ),
    f"{UI}/Tooltip.svelte": "<span>tip</span>\n",
    f"{UI}/Toast.svelte": "<p>toast</p>\n",
    f"{UI}/PetCard.svelte": '<p class="rounded p-2">pet</p>\n',
    f"{UI}/CalendarGrid.svelte": "<p>grid</p>\n",
    f"{UI}/Badge.svelte": "<span>badge</span>\n",
    f"{UI}/PetCard.test.ts": "import PetCard from './PetCard.svelte';\n",
    "client/src/routes/+layout.svelte": (
        "<script lang=\"ts\">\n  import '../app.css';\n"
        "  import { Toast } from '$lib/components/ui';\n</script>\n<Toast />\n<slot />\n"
    ),
    "client/src/routes/(app)/pets/+page.svelte": (
        "<script lang=\"ts\">\n  import { PetCard } from '$lib/components/ui';\n</script>\n"
        "<PetCard />\n"
    ),
    "client/src/routes/(app)/calendar/+page.svelte": (
        "<script lang=\"ts\">\n  import { CalendarGrid } from '$lib/components/ui';\n</script>\n"
        "<CalendarGrid />\n"
    ),
    "client/src/routes/about/+page.svelte": "<p>about</p>\n",
    "client/src/routes/help/+page.svelte": (
        "<script lang=\"ts\">\n  import { Badge } from '$lib/components/ui';\n</script>\n"
        "<Badge />\n"
    ),
    "client/playwright.config.ts": (
        "import { defineConfig } from '@playwright/test';\n"
        "import { port } from './e2e/mock-api';\n\n"
        "export default defineConfig({\n  testDir: './e2e',\n"
        "  use: { baseURL: `http://127.0.0.1:${port}`, serviceWorkers: 'block' },\n"
        "  projects: [\n    { name: 'setup', testMatch: /.*\\.setup\\.ts/ },\n"
        "    { name: 'screens', testMatch: /.*\\.spec\\.ts/, dependencies: ['setup'] },\n  ],\n"
        "  webServer: { command: 'node e2e/serve.mjs', port },\n});\n"
    ),
    f"{E2E}/mock-api.ts": "export const port = 4317;\n",
    f"{E2E}/serve.mjs": "console.log('serving the build');\n",
    f"{E2E}/sign-in.setup.ts": (
        "import { test } from '@playwright/test';\n\ntest('sign in', async () => {});\n"
    ),
    f"{E2E}/pets.spec.ts": (
        "import { test } from '@playwright/test';\n\n"
        "test('pets lists each pet', async ({ page }) => {\n  await page.goto('/pets');\n});\n"
    ),
    f"{E2E}/walk.ts": "export const month = 'May';\n",
    f"{E2E}/calendar.spec.ts": (
        "import { test } from '@playwright/test';\nimport { month } from './walk';\n\n"
        "test('calendar shows a month', async ({ page }) => {\n"
        "  await page.goto('/calendar');\n});\n"
    ),
    f"{E2E}/offline.spec.ts": (
        "import { test } from '@playwright/test';\n\ntest.use({ serviceWorkers: 'allow' });\n\n"
        "test('the app opens offline', async ({ page }) => {\n  await page.goto('/');\n});\n"
    ),
    "client/src/routes/+page.svelte": "<p>home</p>\n",
    f"{E2E}/flows.ts": (
        "export interface ScreenFlow {\n  name: string;\n  path: () => string;\n}\n\n"
        "export const heading = (text: string) => `h1:${text}`;\n\n"
        "export const screenFlows: ScreenFlow[] = [\n"
        "  {\n    name: 'about',\n    path: () => '/about',\n  },\n"
        "  // Help names the heading helper.\n"
        "  {\n    name: 'help',\n    path: () => '/help',\n    title: heading('Help'),\n  },\n"
        "];\n"
    ),
    f"{E2E}/screens.spec.ts": (
        "import { test } from '@playwright/test';\nimport { screenFlows } from './flows';\n\n"
        "test.describe(() => {\n  for (const flow of screenFlows) {\n"
        "    test(`screen: ${flow.name}`, async ({ page }) => {\n"
        "      await page.goto(flow.path());\n    });\n  }\n});\n"
    ),
}
PETS = f"{E2E}/pets.spec.ts"
CALENDAR = f"{E2E}/calendar.spec.ts"
OFFLINE = f"{E2E}/offline.spec.ts"
ABOUT = f"{E2E}/screens.spec.ts > screen: about"
HELP = f"{E2E}/screens.spec.ts > screen: help"


def new_repo(tmp_path, upstream, files, stack):
    repo = tmp_path / "repo"
    shutil.copytree(SKELETON, repo, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    shutil.copytree(ADAPTER / "scripts", repo / "scripts", dirs_exist_ok=True)
    write(repo, files)
    config = (repo / ".repo-standard.yml").read_text()
    config = config.replace("layout: [", "layout: [client/, ")
    config = config.replace(
        "  STACK: [pyproject.toml, uv.lock, conftest.py]", '  STACK: []\n  CLIENT: ["client/**"]'
    )
    config = config.replace("[scripts/stack.mk]", "[scripts/node.py]")
    (repo / ".repo-standard.yml").write_text(config + stack)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(repo, env, "generate")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start from the skeleton, with a client and its browser tests")
    return repo, env


@pytest.fixture
def browser_repo(tmp_path, upstream):
    return new_repo(tmp_path, upstream, APP, STACK)


def selected(root, env):
    return make(root, env, "-s", "select", "BASE=HEAD").splitlines()


def edit(root, path, old, new):
    text = (root / path).read_text()
    assert old in text
    (root / path).write_text(text.replace(old, new))


@pytest.mark.parametrize(
    ("path", "selection"),
    [
        ("client/src/routes/(app)/pets/+page.svelte", [PETS]),
        (f"{UI}/PetCard.svelte", [PETS, f"{UI}/PetCard.test.ts"]),
        (f"{UI}/Badge.svelte", [HELP]),
        (f"{UI}/Tooltip.svelte", []),
        (f"{E2E}/walk.ts", [CALENDAR]),
        (f"{E2E}/support.ts", ["stack:client"]),
        ("client/src/routes/+layout.svelte", [CALENDAR, OFFLINE, PETS, ABOUT, HELP]),
        ("client/src/tokens.css", [CALENDAR, OFFLINE, PETS, ABOUT, HELP]),
        ("client/src/routes/about/+page.svelte", [ABOUT]),
        (PETS, [PETS]),
        (f"{E2E}/screens.spec.ts", [f"{E2E}/screens.spec.ts"]),
        ("client/src/lib/offline.ts", [OFFLINE, "client/src/service-worker.test.ts"]),
        ("client/src/service-worker.ts", [OFFLINE, "client/src/service-worker.test.ts"]),
        (f"{E2E}/mock-api.ts", ["stack:client"]),
        (f"{E2E}/serve.mjs", ["stack:client"]),
        ("client/playwright.config.ts", ["stack:client"]),
        ("client/src/app.html", ["stack:client"]),
        ("client/static/favicon.png", ["stack:client"]),
        ("client/index.html", ["stack:client"]),
        ("client/README.md", []),
    ],
)
def test_a_change_selects_the_browser_tests_whose_routes_reach_it(browser_repo, path, selection):
    root, env = browser_repo
    change(root, path)
    assert selected(root, env) == sorted(selection)


def test_a_barrel_follows_only_the_names_a_page_imports(browser_repo):
    root, env = browser_repo
    change(root, f"{UI}/CalendarGrid.svelte")
    assert selected(root, env) == [CALENDAR]


def test_a_tailwind_class_selects_only_through_its_file(browser_repo):
    root, env = browser_repo
    edit(root, f"{UI}/PetCard.svelte", "rounded p-2", "rounded-lg p-4")
    assert selected(root, env) == [PETS, f"{UI}/PetCard.test.ts"]


def test_a_change_inside_one_row_selects_that_row_alone(browser_repo):
    root, env = browser_repo
    edit(root, f"{E2E}/flows.ts", "path: () => '/about',", "path: () => '/about?tab=1',")
    assert selected(root, env) == [ABOUT]


def test_a_change_to_a_helper_selects_the_rows_that_name_it(browser_repo):
    root, env = browser_repo
    edit(root, f"{E2E}/flows.ts", "`h1:${text}`", "`h2:${text}`")
    assert selected(root, env) == [HELP]


def test_a_comment_between_rows_selects_nothing(browser_repo):
    root, env = browser_repo
    edit(root, f"{E2E}/flows.ts", "Help names", "The help row names")
    assert selected(root, env) == []


def test_the_selected_ids_are_the_tests_playwright_lists(browser_repo, tmp_path):
    """Playwright reads the ids, as `make e2e` hands them on, as exactly the selected tests and
    the setup project they depend on. The script lists the tests instead of running them, so no
    browser is needed."""
    root, env = browser_repo
    subprocess.run(
        ["npm", "ci", "--no-audit", "--no-fund"],
        cwd=root / "client",
        check=True,
        capture_output=True,
        timeout=300,
    )
    change(root, f"{UI}/Badge.svelte")
    change(root, f"{UI}/CalendarGrid.svelte")
    ids = selected(root, env)
    assert ids == [CALENDAR, HELP]
    listed = tmp_path / "ids.txt"
    listed.write_text("".join(f"{one}\n" for one in ids))
    edit(root, "client/package.json", '"playwright test"', '"playwright test --list"')
    out = make(root, env, "e2e", f"E2E_LIST={listed}")
    tests = sorted(line.strip() for line in out.splitlines() if line.strip().startswith("["))
    assert [test.rsplit(" › ", 1)[-1] for test in tests] == [
        "calendar shows a month",
        "screen: help",
        "sign in",
    ]
    assert "--fail-on-flaky-tests" in out


def test_a_failed_browser_test_is_written_as_the_id_that_runs_it_alone(browser_repo, tmp_path):
    """Given `REPO_STANDARD_FAILED`, `make e2e` reads Playwright's JSON report and writes the test
    that failed as the id `make select` would print for it, and that id, handed back as a list,
    runs that test alone. Its tests open no page, so no browser is needed."""
    root, env = browser_repo
    subprocess.run(
        ["npm", "ci", "--no-audit", "--no-fund"],
        cwd=root / "client",
        check=True,
        capture_output=True,
        timeout=300,
    )
    edit(
        root,
        "client/playwright.config.ts",
        "  webServer: { command: 'node e2e/serve.mjs', port },\n",
        "",
    )
    write(
        root,
        {
            f"{E2E}/cart.spec.ts": (
                "import { expect, test } from '@playwright/test';\n\n"
                "test('holds', () => {});\n\n"
                "test.describe('cart', () => {\n"
                "  test('adds an item', () => {\n    expect(1).toBe(2);\n  });\n});\n"
            )
        },
    )
    listed, failed, again = (tmp_path / name for name in ("ids.txt", "failed.txt", "again.txt"))
    listed.write_text(f"{E2E}/cart.spec.ts\n")
    out = make(
        root, {**env, "REPO_STANDARD_FAILED": str(failed)}, "e2e", f"E2E_LIST={listed}", ok=False
    )
    assert "1 failed" in out
    assert "holds" in out
    assert failed.read_text().splitlines() == [f"{E2E}/cart.spec.ts > cart > adds an item"]

    out = make(
        root, {**env, "REPO_STANDARD_FAILED": str(again)}, "e2e", f"E2E_LIST={failed}", ok=False
    )
    assert "1 failed" in out
    assert "holds" not in out
    assert again.read_text() == failed.read_text()


def reach_faults(root):
    """The faults of the rule a browser test no path reaches breaks, as conform reads them."""
    paths = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return rules.selects(rules.Repo(root, load(root), paths))


def commit_all(root, message):
    git(root, "add", "-A")
    git(root, "commit", "--allow-empty", "-qm", message)


@pytest.mark.parametrize(
    ("planted", "fault"),
    [
        ({}, None),
        (
            {f"{E2E}/lost.spec.ts": "import { test } from '@playwright/test';\n"},
            f"{E2E}/lost.spec.ts: no path reaches it: it opens no route, imports no local file",
        ),
        (
            {f"{E2E}/kennel.spec.ts": "test('k', ({ page }) => page.goto('/kennel/1'));\n"},
            f"{E2E}/kennel.spec.ts: opens /kennel/1, which matches no route of the app",
        ),
        (
            {f"{E2E}/flows.ts": APP[f"{E2E}/flows.ts"].replace("path: () => '/help',\n", "")},
            f"{E2E}/screens.spec.ts > screen: help: its row names no path",
        ),
        (
            {f"{E2E}/flows.ts": APP[f"{E2E}/flows.ts"].replace("screenFlows", "flows")},
            f"{E2E}/screens.spec.ts: e2e.table names screenFlows, an array it never declares",
        ),
    ],
)
def test_the_reach_rule_fails_a_browser_test_no_path_reaches(browser_repo, planted, fault):
    root, _ = browser_repo
    write(root, planted)
    commit_all(root, "a browser test")
    found = reach_faults(root)
    assert found == [] if fault is None else len(found) == 1 and found[0].startswith(fault), found


def test_the_reach_rule_names_a_spec_the_config_names_that_is_gone(browser_repo):
    root, _ = browser_repo
    git(root, "rm", "-q", f"{E2E}/screens.spec.ts")
    commit_all(root, "the table spec is gone")
    assert reach_faults(root) == [
        f"{E2E}/screens.spec.ts: e2e names it, and it is no spec under client/e2e"
    ]


def test_the_reach_rule_needs_the_repos_browser_selection(browser_repo):
    root, _ = browser_repo
    git(root, "rm", "-q", "scripts/node_browser.py")
    commit_all(root, "no browser selection")
    assert reach_faults(root) == [
        "scripts/node_browser.py: is not there, so no change selects a browser test"
    ]


def test_a_node_stack_with_no_browser_tests_is_warned_of_and_another_stack_is_not(browser_repo):
    root, _ = browser_repo
    config = (root / ".repo-standard.yml").read_text().split("    e2e:")[0]
    go = "  api:\n    adapter: go\n    roots: [api]\n"
    (root / ".repo-standard.yml").write_text(config + go)
    commit_all(root, "no e2e part, and a Go stack beside the client")
    found = reach_faults(root)
    assert found == ["stack client: sets no `e2e:`, so no browser test runs on a pull request"]
    assert isinstance(found[0], rules.Advice)


MOCK = "      mock:\n        path: client/e2e/mock-api.ts\n"


def declare(root, mock, every=""):
    """The config's `mock:` part replaced by `mock`, and `every` set, committed."""
    config = (root / ".repo-standard.yml").read_text()
    assert MOCK in config
    config = config.replace(MOCK, mock).replace(
        "      script: test:e2e\n", f"      script: test:e2e\n{every}"
    )
    (root / ".repo-standard.yml").write_text(config)


def test_a_change_to_the_real_api_selects_no_browser_test_and_its_unit_tests_still_run(
    browser_repo,
):
    root, env = browser_repo
    declare(
        root,
        MOCK + "        producer: [client/server]\n",
        every=f"      every: [{CALENDAR}]\n",
    )
    write(
        root,
        {
            "client/server/pets.ts": "export const pets = [];\n",
            "client/server/pets.test.ts": "import { pets } from './pets';\n",
        },
    )
    commit_all(root, "a server beside the app, and a spec every change of the app selects")
    change(root, "client/server/pets.ts")
    assert selected(root, env) == ["client/server/pets.test.ts"]
    git(root, "checkout", "-q", "--", ".")
    change(root, "client/src/lib/offline.ts")
    assert CALENDAR in selected(root, env)


def test_a_declared_mock_forces_the_stack_whatever_its_name(browser_repo):
    root, env = browser_repo
    declare(root, "      mock:\n        path: client/e2e/handlers\n")
    write(root, {f"{E2E}/handlers/pets.ts": "export const handlers = [];\n"})
    commit_all(root, "the mock is a folder of handlers")
    change(root, f"{E2E}/handlers/pets.ts")
    assert selected(root, env) == ["stack:client"]


@pytest.mark.parametrize(
    ("mock", "fault"),
    [
        (
            "      mock:\n        path: client/e2e/msw\n",
            "client/e2e/msw: e2e.mock names it, and it holds no file",
        ),
        (
            MOCK + f"        producer: [{UI}/PetCard.svelte]\n",
            f"{PETS}: reaches {UI}/PetCard.svelte, which e2e.mock.producer says no browser test",
        ),
    ],
)
def test_the_reach_rule_fails_a_mock_it_cannot_hold(browser_repo, mock, fault):
    root, _ = browser_repo
    declare(root, mock)
    commit_all(root, "a mock the rule cannot hold")
    found = reach_faults(root)
    assert len(found) == 1 and found[0].startswith(fault), found


def test_a_browser_stack_with_no_mock_is_warned_of(browser_repo):
    root, _ = browser_repo
    config = (root / ".repo-standard.yml").read_text()
    (root / ".repo-standard.yml").write_text(re.sub(r"      mock:\n(        .*\n)+", "", config))
    commit_all(root, "no mock")
    found = reach_faults(root)
    assert found == [
        "stack client: its e2e sets no `mock:`, so no contract holds the API its browser tests"
        " run on to the real one"
    ]
    assert isinstance(found[0], rules.Advice)


def test_conform_fails_a_spec_whose_url_has_no_route(browser_repo):
    root, env = browser_repo
    assert "errors 0, warnings 0" in skeleton_conform(root, env)
    write(
        root,
        {
            f"{E2E}/gone.spec.ts": (
                "import { test } from '@playwright/test';\n\n"
                "test('gone', async ({ page }) => {\n  await page.goto('/kennel');\n});\n"
            )
        },
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a spec of a page the app does not have")
    out = skeleton_conform(root, env, ok=False)
    assert f"{E2E}/gone.spec.ts: opens /kennel, which matches no route of the app" in out


def spec(url):
    return (
        "import { test } from '@playwright/test';\n\n"
        f"test('opens {url}', async ({{ page }}) => {{\n  await page.goto(`{url}`);\n}});\n"
    )


REACT = {
    **{path: text for path, text in APP.items() if not path.startswith(("client/src", E2E))},
    "client/index.html": '<script type="module" src="/src/main.tsx"></script>\n',
    "client/src/main.tsx": (
        "import { createBrowserRouter, Outlet } from 'react-router-dom';\n"
        "import { PublicPage } from './components/PublicPage';\n"
        "import LandingPage from './pages/LandingPage';\n"
        "import { PantriesPage, PantryPage } from './pages';\n"
        "import AdminDashboard from './admin/AdminDashboard';\n\n"
        "const routes = [\n  // The public pages share one frame.\n  {\n    element: (\n"
        "      <PublicPage>\n        <Outlet />\n      </PublicPage>\n    ),\n"
        "    children: [\n      { path: '/', element: <LandingPage /> },\n"
        "      { path: '/pantries', element: <PantriesPage /> },\n"
        "      { path: '/pantries/:id', element: <PantryPage /> },\n    ],\n  },\n"
        "  { path: '/admin/*', element: <AdminDashboard /> },\n];\n\n"
        "routes.push({\n  path: '/system',\n"
        "  lazy: async () => ({ Component: (await import('./pages/SystemPage.tsx')).default }),\n"
        "});\n\nexport const router = createBrowserRouter(routes);\n"
    ),
    "client/src/components/PublicPage.tsx": (
        "export const PublicPage = () => <nav>Don't go</nav>;\n"
    ),
    "client/src/pages/index.ts": (
        "export { PantriesPage } from './PantriesPage';\n"
        "export { PantryPage } from './PantryPage';\n"
    ),
    "client/src/pages/PantriesPage.tsx": "export const PantriesPage = () => <ul />;\n",
    "client/src/pages/PantryPage.tsx": "export const PantryPage = () => <p />;\n",
    "client/src/pages/LandingPage.tsx": "export default () => <h1 />;\n",
    "client/src/pages/SystemPage.tsx": "export default () => <main />;\n",
    "client/src/admin/AdminDashboard.tsx": "export default () => <aside />;\n",
    f"{E2E}/sign-in.setup.ts": APP[f"{E2E}/sign-in.setup.ts"],
    f"{E2E}/mock-api.ts": APP[f"{E2E}/mock-api.ts"],
    f"{E2E}/serve.mjs": APP[f"{E2E}/serve.mjs"],
    f"{E2E}/landing.spec.ts": spec("/"),
    f"{E2E}/pantries.spec.ts": spec("/pantries"),
    f"{E2E}/pantry.spec.ts": spec("/pantries/${pantry.id}"),
    f"{E2E}/admin.spec.ts": spec("/admin/reports"),
    f"{E2E}/system.spec.ts": spec("/system"),
}
REACT_STACK = STACK.split("      table:")[0]


@pytest.fixture
def react_repo(tmp_path, upstream):
    return new_repo(tmp_path, upstream, REACT, REACT_STACK)


@pytest.mark.parametrize(
    ("path", "selection"),
    [
        ("client/src/pages/PantryPage.tsx", ["pantry"]),
        ("client/src/pages/PantriesPage.tsx", ["pantries"]),
        ("client/src/components/PublicPage.tsx", ["landing", "pantries", "pantry"]),
        ("client/src/admin/AdminDashboard.tsx", ["admin"]),
        ("client/src/pages/SystemPage.tsx", ["system"]),
        ("client/src/main.tsx", None),
        ("client/index.html", None),
    ],
)
def test_a_react_change_selects_the_specs_whose_router_rows_reach_it(react_repo, path, selection):
    root, env = react_repo
    change(root, path)
    expected = (
        ["stack:client"] if selection is None else [f"{E2E}/{one}.spec.ts" for one in selection]
    )
    assert selected(root, env) == sorted(expected)


def test_a_react_app_passes_the_reach_check(react_repo):
    root, env = react_repo
    assert "errors 0, warnings 0" in skeleton_conform(root, env)
