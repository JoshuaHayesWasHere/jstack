# The skeleton and its adapters

A repo starts on [the repo standard](standard.md) from two folders of this feature.
`features/repo-standard/skeleton/` holds what every repo has, whatever its stack.
An adapter, `features/repo-standard/adapters/python-uv/`, `features/repo-standard/adapters/go/` or `features/repo-standard/adapters/node-vite/`, holds what one stack adds: the commands under the make targets, its selection of tests, and an example feature.
Both folders mirror the new repo's root, and neither sits under a `templates/` folder, so no harness installs them.

## Start a repo

Copy the skeleton, then the stack's adapter over it, write the generated files, and commit:

```sh
cp -R features/repo-standard/skeleton/. ../new-repo/
cp -R features/repo-standard/adapters/python-uv/. ../new-repo/
make -C ../new-repo generate
cd ../new-repo
git init -b main
git add -A
git commit -m "start from the repo standard's skeleton"
```

The example feature, `hello`, shows where a feature's parts go: rename it for the repo's first feature, or delete its folder and run the target `generate` again.
`features/repo-standard/tests/test_skeleton_python.py` and `features/repo-standard/tests/test_go_adapter.py` each make a repo this way, outside jstack, and run its make targets.

## What the skeleton holds

Each file is a path from the new repo's root, where the copy puts it.

| File | What it does |
|---|---|
| `.repo-standard.yml` | Pins the standard's version and sets the guards' parts, as [the guards' page](guards.md) says. |
| `Makefile` | The targets of the standard, the same in every stack. |
| `.github/workflows/check.yml` | Calls [the shared check workflow](check-workflow.md) at the pinned tag: /new-home's template, `features/home/templates/check.yml`, with `make check` as its command. |
| `.github/workflows/borders.yml` | Runs the target `borders` on each push of a pull request and each change of its labels. |
| `schemas/feature.core.schema.json` | The schema each `feature.json` holds to, a copy of jstack's. |
| `generate-index.py` in `scripts/` | Writes the list of features in `README.md` from the manifests. |
| `README.md` and `.gitignore` | The repo's front page, and the folders the tools write. |

The test holds the caller and the schema equal to jstack's, so a change to either changes both.

### The config's waivers

A new repo meets most rules from the start.
The config waives four, each with its reason, and `repo-standard conform` prints each waiver on every run.
Each needs a file of the repo's own to enforce it: a command's page, its prose lint, its shell scripts and a guard over its tests.
When the repo adds the file, it names it under `enforced-by` and drops the waiver.
A waiver may add `until: repo-standard-vN`, the version by which the repo means to meet its rule, and `repo-standard conform` warns of it once the repo pins that version.

## What a version owns

A copy of the skeleton is not the repo's to edit all through.
One rule, `RULES` in `features/repo-standard/src/repo_standard/owned.py`, sorts each file the skeleton and an adapter hold by its path:

| From | Owned by the version | Seeded once, then the repo's |
|---|---|---|
| The skeleton | `Makefile`, `.github/workflows/*.yml`, `schemas/**`, `scripts/**` | `.repo-standard.yml`, `.gitignore`, `README.md`, `.github/actions/setup/action.yml`, the example feature |
| An adapter | `scripts/**` | `.repo-standard.yml`, `.github/actions/setup/action.yml`, the example feature, its root files such as `pyproject.toml` |

A file the rule does not place fails `features/repo-standard/tests/test_upgrade.py`, so a file added to the skeleton or an adapter is placed when it is added.
A repo's adapters are those its `stacks:` name, or, with no `stacks:`, each adapter whose scripts the repo holds, such as `select.py` in `scripts/` for python-uv.
A repo of several stacks takes no `stack.mk`.

An owned file stays equal to its copy at the tag the repo pins, and `repo-standard conform` warns of one that differs or is missing.
In the caller, `.github/workflows/check.yml`, the runner's label in `runner:` is the repo's own and is not compared, and the job `check` runs on that label through the call's output `runner`.
The repo's own make targets, such as a deploy entry, go in `local.mk` at the root, which the Makefile includes when it is there, and which the config's `owners` names.
A repo that must keep an owned file of its own names it under `local:` in `.repo-standard.yml`, with the reason:

```yaml
local:
  Makefile: the deploy targets need the image's tag before the standard's targets
```

`conform` does not compare a `local:` file, and fails an entry with no reason.

### Move to a new version

`repo-standard upgrade --to N` moves the repo to version N.
It runs from the tool at version N, never the repo's current one, since only version N's tool reads version N's config:

```sh
uvx --from git+https://github.com/JoshuaHayesWasHere/jstack@repo-standard-v2 repo-standard upgrade --to 2
make lint
```

It writes the `standard:` line, `local.mk` beside the `Makefile` in `owners`, the caller's tag of the shared check and every owned file as version N's copy, keeping the caller's runner, and leaves the `local:` and seeded files, printing each it left.
A second run writes nothing.
[The command's page](repo-standard.md#upgrade) gives the rest.

## The make targets

Each target runs as `make <target>` in the new repo.

| Target | What it runs |
|---|---|
| `lint` | The stack's lint, then `repo-standard conform`. |
| `test` | The whole suite, only the ids `TESTS` names, or, with `SHARD=<part>/<parts>` and no `TESTS`, that part of the whole suite: the ids `STACK_LIST` prints, dealt to the parts in turn. |
| `check` | `lint` and `test`. |
| `select BASE=<ref>` | The test ids the change from `<ref>` reaches, one a line, or `all`, and nothing else. |
| `check-fast BASE=<ref>` | `lint`, then `test` with the ids `select` prints, the whole suite on `all`, and no test on an empty selection. |
| `e2e` | The browser tests of each stack whose config sets `e2e:`, or, given `E2E_LIST=<file>`, only the ids in the file, one a line. |
| `borders BASE=<ref>` | The borders of the change from `<ref>`, with the pull request's labels in `LABELS`: a change across two features passes only with the label `cross-cutting`. The shared check's lint reads no labels, so `lint` leaves this to `borders`. |
| `generate` | Each generator, which writes its files again from the manifests. |

The repo's own targets go in `local.mk`, as [What a version owns](#what-a-version-owns) says.

The standard's guards come from jstack at the tag `.repo-standard.yml` pins.
The Makefile clones that tag into `.cache/` the first time a target needs it, and runs the guards with `python3`, so a repo of any stack needs only git and python3 for them.
`REPO_STANDARD_UPSTREAM` names another place to clone from, as the test does.
Neither `TESTS` nor `SHARD` reaches a test: the Makefile keeps both out of the environment of what it runs, and out of the `MAKEFLAGS` a make that a test starts reads, so a test that runs make sees only what it passes.

## A deploy entry

The skeleton deploys nothing, so its config sets `deploy: []`.
A repo that deploys adds one target for it, lists it in the config as `deploy: [make deploy]`, and starts its recipe with `$(REPO_STANDARD) green`, which refuses a tree that is not green main:

```make
.PHONY: deploy
deploy: | $(REPO_STANDARD_HOME)
	$(REPO_STANDARD) green
	aws s3 sync dist s3://<bucket>
```

The clone is an order-only prerequisite, which `conform` lets run first, and the target has no other.

## An adapter

An adapter gives the Makefile four commands, in the file `stack.mk` of its `scripts/` folder, which the Makefile includes, as python-uv's `features/repo-standard/adapters/python-uv/scripts/stack.mk` does:

| Variable | What it runs |
|---|---|
| `STACK_LINT` | The stack's own lint. |
| `STACK_TEST` | The test runner, to which the target `test` appends the ids of `TESTS`. Given `REPO_STANDARD_FAILED=<file>`, it appends to the file the id of each test that failed, one a line. |
| `STACK_SELECT` | The selection, given the base as its one argument. |
| `STACK_LIST` | Every test id of the stack, one a line, sorted: the whole suite, which `SHARD` deals out. |

Its root files, such as a lock file, are owned in the config's `STACK` group of `owners`, and each adapter names its own there.

## Several stacks

A repo of more than one stack, such as a Go API beside a Python program, declares each in `.repo-standard.yml`, under `stacks:`, by name:

```yaml
stacks:
  api:
    adapter: go
    roots: [api]
  capture:
    adapter: python-uv
    roots: [tools/capture]
```

`adapter` is `go`, `python-uv` or `node-vite`, and `roots` lists the folders the stack owns, from the repo's root.
The config refuses an adapter it does not know, a stack with no root, and a root that sits in another root or holds one.
Such a repo copies each of its adapters' scripts into `scripts/`, and no `stack.mk`: the Makefile sees `stacks:` and hands `lint`, `test`, `select` and `e2e` to the standard's driver, `python3 -m repo_standard stacks`, at the tag the config pins.
The targets keep their names and what they print.

| Target | What the driver does |
|---|---|
| `lint` | Runs every stack's lint, then each stack's [mock contract](#the-mock-api-and-its-contract), and fails when any failed. |
| `test` | Runs every stack's suite, or, given ids in `TESTS`, each path in the stack whose root holds it, and `stack:<name>` as that stack's whole suite. With `SHARD=<part>/<parts>` and no `TESTS`, it lists each stack's ids, in the config's order of stacks, and runs that part of them. |
| `select BASE=<ref>` | Joins the stacks' selections, as below. |
| `e2e` | Runs the browser tests of each stack with `e2e:`, or, given `E2E_LIST`, each stack the ids reach, as [Browser tests](#browser-tests) says. |

A test id is a path from the repo's root, or `stack:<name>`, every test of one stack.
`all` is every test of the repo, so the shared check's plan never reads a stack's whole suite as the repo's.
The selection prints `all` for a shared path: the `Makefile`, `.repo-standard.yml`, and anything under `scripts/`, `.github/` or `schemas/`.
It prints `all` for a path outside every root too, unless it is a page of Markdown, a file in a feature's `docs/` or its `feature.json`, which select nothing.
Each stack's own selection places the paths under its roots and ignores the rest, and one that would print `all` prints `stack:<name>`.

A stack's roots own its root files: a lock file sits in the root, so a change to it selects that stack alone.
The `owners` of the config name each root, as any other path.
The adapters' scripts the driver runs may be named in `enforced-by`.
The repo keeps one setup action, `.github/actions/setup/action.yml`, which holds the steps of each of its adapters' actions.

### python-uv

The python-uv adapter runs the lint, `ruff check` and `ruff format --check`, and the tests, `pytest`, with `uv run --locked`.
Its root `conftest.py` puts each feature's `src/` on the path, so a test imports any feature's package by its name.
Its setup action, `.github/actions/setup/action.yml`, installs uv in each job of the shared check.

Its selection, `features/repo-standard/adapters/python-uv/scripts/select.py`, runs in `python3` alone, so the shared check's plan selects before any setup.
It reads the change from the base to the working tree, and each file git does not track yet:

- A shared path selects `all`: `pyproject.toml`, `uv.lock`, the root `conftest.py`, the `Makefile`, `.repo-standard.yml`, anything under `scripts/`, `.github/` or `schemas/`, and any path the rules below cannot place.
- A Markdown page, a feature's `docs/` and its `feature.json` select nothing.
- A test file selects itself.
- A module under a feature's `src/` selects each test that imports it, directly or through other modules.
- Any other file under a feature's `src/` or `tests/`, such as a `conftest.py` or a file of data, selects the feature's tests and each test that imports one of its modules.

In a stack of a repo with `stacks:`, each root is a uv project of its own, whose `pyproject.toml` and `uv.lock` sit in the root, and whose dev group holds `pytest` and `ruff`.
The driver runs `ruff` and `pytest` with `uv run --locked --project <root>`, and pytest with the root as its rootdir and the root's `pyproject.toml` as its config.
The selection, given `--roots`, holds each root to the rules above with the root in place of the repo, and a feature's `src/` and `tests/` in place of the root's:

- The root's `pyproject.toml`, `uv.lock` and `conftest.py`, and any file the rules cannot place, such as a `Dockerfile`, select the whole stack.
- A `.py` file outside a `tests/` folder is a module, named from the root, or from its `src/` when it sits there.
- Any other file under a `tests/` folder selects each test of the root.

A test whose imports do not show what it runs, such as one that runs a module in a subprocess, is not selected.
Main's full run after each merge runs it, as the standard's rule [Main runs the whole suite after each merge](standard.md#main-runs-the-whole-suite-after-each-merge) says.

### go

The go adapter runs Go modules wherever they sit in the tree, with no go.work, through one script, `features/repo-standard/adapters/go/scripts/go.py`, which runs in `python3` alone:

| Command | What it runs |
|---|---|
| `go.py lint` | `gofmt -l` on the `.go` files go builds, so none under `testdata/` or `vendor/`, and `go vet ./...`, in each module, and fails when gofmt names a file. |
| `go.py test [ids]` | `go test ./...` in each module, or `go test` on the packages it is given, a run per module. |
| `go.py select <base>` | The selection. |

A test id is the folder of a package that has a test, as a path from the repo's root.
Its example feature, `hello`, is a module of its own, `features/repo-standard/adapters/go/features/hello/go.mod`, with its test beside its code.
The adapter replaces the skeleton's `.repo-standard.yml` with its own, which owns no root file in `STACK` and sets the size and comment limits over `*.go` files, read as `script` with `//go:` lines allowed.
Its test holds every other part equal to the skeleton's.
A `_test.go` file's name is the repo's one, as for every test, so two packages give their tests names of their own.

Its setup action, `.github/actions/setup/action.yml`, installs Go and restores go's build and test cache from the newest run, so `go test` in CI runs again only a package whose inputs changed.
Only the job `test` saves the cache it leaves.
A test that opens a file reads it again after a fresh checkout, since go's cache keys on the file's time as well as its size.

Its selection adds up what each changed path selects, and prints the packages with a test, or `all`:

- A shared path selects `all`: the `Makefile`, `.repo-standard.yml`, and anything under `scripts/`, `.github/` or `schemas/`.
- A path a glob of a feature's `reads` matches selects the feature's packages.
- A path inside a module selects every package of the module, and of each module that takes it by a `replace` onto a local folder.
  go test's cache skips the packages whose inputs did not change.
- Outside a module, a Markdown page, a feature's `docs/` and its `feature.json` select nothing.
- Any other path selects `all`.

In a stack of a repo with `stacks:`, the script takes `--roots <root>` once a root, after its command, and works on the modules under those roots alone.
A root holds whole modules, each `go.mod` inside it.
The selection ignores a path outside the roots that no `reads` matches, and a path under them it cannot place selects the whole stack.

`reads`, a key of the core manifest schema, lists the files a feature's tests read that its imports do not show, such as a page another feature owns, which a test opens.
Each entry is a glob from the repo's root, in which `*` crosses folders, and `repo-standard conform` fails a glob that matches no file.
A file a test reads that no `reads` names is still caught by main's full run after each merge.

### node-vite

A node stack is a client built with Vite and tested with Vitest, as an npm package.
It runs only in a repo with `stacks:`, which declares it like any other stack:

```yaml
stacks:
  client:
    adapter: node-vite
    roots: [client]
```

Each root is an npm package of its own, with its `package.json` and its `package-lock.json` in the root.
The adapter runs the package's own scripts, so each repo keeps its own lint and test commands:

| Target | What the driver runs in each root |
|---|---|
| `lint` | `npm run check`, the package's `check` script. |
| `test` | `npm test`, the package's `test` script, or `npm test -- <files>` with the ids under that root, each a path from the root. |
| `select BASE=<ref>` | `node.py select --roots <root> <ref>`, from the repo's `scripts/`, with `--e2e <part>` for a stack that sets `e2e:`. |
| `e2e` | `node.py e2e --root <root> --script <name>`, which runs `npm run <name> -- --fail-on-flaky-tests` in the e2e root, with `--test-list <file>` given ids. |

`repo-standard conform` fails a root whose `package.json` has no `check` or no `test` script, under the rule [Each check has one make target](standard.md#each-check-has-one-make-target).
It warns of a root that pins no Node version, in an `.nvmrc` or in the `engines.node` of its `package.json`, since CI then runs the runner's Node.
The repo copies the adapter's four scripts, `features/repo-standard/adapters/node-vite/scripts/node.py`, `features/repo-standard/adapters/node-vite/scripts/node_graph.py`, `features/repo-standard/adapters/node-vite/scripts/node_browser.py` and `features/repo-standard/adapters/node-vite/scripts/node_table.py`, into its `scripts/`, and adds `node_modules/` to its `.gitignore`, as the skeleton's does.

Its setup action, `.github/actions/setup/action.yml`, finds each folder whose `package-lock.json` git tracks, installs Node with `actions/setup-node` at the version the first such root pins, with npm's cache, and runs `npm ci` in each.
The shared check's plan selects before it, in `python3` alone.

A unit test is a file the root's Vitest config includes: the globs of a literal `include` in the `test` block of `vite.config.*` or `vitest.config.*`, or, with none, a file named `*.test.<ext>`.
A Playwright `*.spec.ts` beside it is no unit test.
The selection reads the import graph of the root, as `node_graph.py` says, and holds each root to these rules:

- `package.json`, the lockfile, `.nvmrc`, `.npmrc`, a Vite, Vitest, Svelte, TypeScript, PostCSS or Tailwind config, each setup file the Vitest config names, each file the `test` script names, and every file those import select the whole stack.
- A page of Markdown selects nothing.
- A source file, or a file a source file reaches, selects each test that reaches it through imports: relative paths, `$lib`, the `paths` of a `tsconfig.json`, `vi.mock`, a literal or template `import()`, and `import.meta.glob`.
- A string in a test that names a file of the repo, such as one the test reads, counts as an import, so a change to that file selects the test, even in another stack.
- Any other path under the root, such as a file under `static/` or `index.html`, selects the whole stack.

#### Browser tests

A node stack declares its Playwright tests under `e2e:`, and conform warns of a node stack that declares none:

```yaml
stacks:
  client:
    adapter: node-vite
    roots: [client, e2e]
    e2e:
      root: e2e
      script: test:e2e
      every: [e2e/page-layout.spec.ts]
      routes:
        e2e/public.spec.ts: [/pantries, /about]
      mock:
        path: e2e/mock-api.ts
        contract: python3 -m repo_standard routes --producer "cd api && go run ./cmd/routes" --mock "node e2e/mock-routes.ts"
        producer: [api]
      table:
        - file: e2e/screens.spec.ts
          export: screenFlows
          title: "screen: {name}"
```

| Key | What it sets |
|---|---|
| `root` | The npm package whose script runs Playwright, inside one of the stack's roots. |
| `script` | The npm script that runs Playwright, such as `playwright test`, on the built app it serves with a mocked API, never on a live stage. |
| `every` | The specs any change of the app selects, such as one that reads every page's built CSS. |
| `routes` | The URLs a spec opens that its text does not name, such as ones it builds in a loop. |
| `table` | The specs that run one test a row of an array: the spec, the array's name, and the title of a row's test, in which `{name}` stands for the row's `name:`. |
| `mock` | The API the tests run on, its contract and the real API it mirrors, as [The mock API and its contract](#the-mock-api-and-its-contract) says. |

Each path is from the repo's root, and the config refuses a key it does not know and a path outside the stack's roots.
A spec is a `*.spec.<ext>` file under the `testDir` of the Playwright config the script runs.
The selection prints a browser test as Playwright's test-list form with the spec's path from the repo's root, `<spec>` or `<spec> > <title>`, and the target `e2e` hands the ids to Playwright as `--test-list`, each spec's path made relative to `testDir`.
Playwright still runs a setup project the selected tests depend on.
Given `REPO_STANDARD_FAILED=<file>`, the target `e2e` runs Playwright's list, HTML and JSON reporters in place of the config's, and appends to the file each test the JSON report says failed or passed only on a retry, as `<spec> > <title>`, with the title of each `describe` around it before the test's.
`features/repo-standard/adapters/node-vite/scripts/node_browser.py` holds the rules: a URL a spec opens maps to its route's files, a SvelteKit page with every layout above it or a React router table's row, and the change reaches each test whose route files, and the files they import, hold it.
`repo-standard conform` fails a spec or a row that no path reaches, and a URL that matches no route of the app, under the rule [A change selects its tests](standard.md#a-change-selects-its-tests).

##### The mock API and its contract

The browser tests run on a mock of the API, and `mock:` holds that mock to the real API, so a route the real API drops or renames fails the lint instead of passing every browser test.

| Key | What it sets |
|---|---|
| `path` | The mock's file, or a folder of its files, inside the stack's roots. |
| `contract` | The shell command that fails when the mock answers what the real API does not. The config refuses a `mock:` with none. |
| `producer` | The paths of the real API the mock mirrors, usually another stack's roots. A path that holds the mock or the e2e root is refused. |

`make lint` runs each stack's contract from the repo's root after every stack's lint, with the standard's `src` on `PYTHONPATH`, so `python3 -m repo_standard routes` is the version the config pins.
It fails when the contract fails.

The standard's reference contract is `repo-standard routes --producer <cmd> --mock <cmd>`.
Each command prints the routes of its side as a JSON list of `{"method": ..., "path": ...}`, with a path parameter written `{name}`.
The contract fails on each mock route the producer lacks, and names it.
The producer may serve routes the mock does not.
A producer parameter matches any one segment of a mock route, a mock parameter matches only a parameter, and the names of parameters do not count.
The contract refuses a route it cannot compare, such as one with no method or a `{name...}` segment: the command that prints it writes it the way the contract reads it.

Each side writes its own printer.
A Go API whose routes are `net/http` ServeMux patterns, such as `mux.HandleFunc("GET /pets/{id}", ...)`, can register them through a function that takes the mux, and a small command can pass that function a recorder that prints each pattern.
A repo whose router has no table, such as one that routes by a `switch` on the path inside each handler, writes its own producer command, for example one that probes the router through its handler tests.
A mock that keeps its routes in a list prints that list, and a mock that matches a URL by a regular expression keeps its routes as data the printer can read.

A change under `producer` selects no browser test: the tests run on the mock, and the contract holds the mock to the producer.
The producer's own stack still selects its tests, and a producer path under no stack's roots selects `all`, as any such path does.
A change to the mock forces every browser test of the stack, whatever the mock's file is named.
`repo-standard conform` fails a `mock.path` that holds no file and a browser test that reaches a producer file, and warns of a stack whose `e2e:` sets no `mock:`.
`features/repo-standard/tests/test_mock_contract.py` makes a repo of a Go API and a node client, and runs the contract alone and in `make lint`.

The shared check runs the browser tests in the Playwright image of the version the e2e root's `package-lock.json` pins.
A caller that sets the input `browser-channel`, such as `chrome`, runs them on the runner's own browser instead, and the job prints its version; the Playwright config reads the channel as `process.env.REPO_STANDARD_BROWSER_CHANNEL`.

Its example feature, `hello-client`, is an npm package, `features/repo-standard/adapters/node-vite/features/hello-client/package.json`, whose `check` script runs `tsc --noEmit` and whose `test` script runs `vitest run`.
Its stack's root is the feature's folder.
`features/repo-standard/tests/test_node_adapter.py` makes a repo of it, installs it with `npm ci` and runs its make targets, and runs the selection on a Svelte client and a React client.
`features/repo-standard/tests/test_browser_select.py` runs the browser selection on a SvelteKit client and a React client, and has Playwright list the tests a selection hands it.
