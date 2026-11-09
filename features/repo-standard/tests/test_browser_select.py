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
import shutil
import subprocess

import pytest

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
    ),
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
    f"{E2E}/calendar.spec.ts": (
        "import { test } from '@playwright/test';\n\n"
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


@pytest.fixture
def browser_repo(tmp_path, upstream):
    repo = tmp_path / "repo"
    shutil.copytree(SKELETON, repo, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    shutil.copytree(ADAPTER / "scripts", repo / "scripts", dirs_exist_ok=True)
    write(repo, APP)
    config = (repo / ".repo-standard.yml").read_text()
    config = config.replace("layout: [", "layout: [client/, ")
    config = config.replace(
        "  STACK: [pyproject.toml, uv.lock, conftest.py]", '  STACK: []\n  CLIENT: ["client/**"]'
    )
    config = config.replace("[scripts/stack.mk]", "[scripts/node.py]")
    (repo / ".repo-standard.yml").write_text(config + STACK)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(repo, env, "generate")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start from the skeleton, with a client and its browser tests")
    return repo, env


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
        ("client/src/routes/+layout.svelte", [CALENDAR, OFFLINE, PETS, ABOUT, HELP]),
        ("client/src/tokens.css", [CALENDAR, OFFLINE, PETS, ABOUT, HELP]),
        ("client/src/routes/about/+page.svelte", [ABOUT]),
        (PETS, [PETS]),
        (f"{E2E}/screens.spec.ts", [f"{E2E}/screens.spec.ts"]),
        ("client/src/lib/offline.ts", [OFFLINE, "client/src/service-worker.test.ts"]),
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
