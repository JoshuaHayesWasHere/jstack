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

## The make targets

Each target runs as `make <target>` in the new repo.

| Target | What it runs |
|---|---|
| `lint` | The stack's lint, then `repo-standard conform`. |
| `test` | The whole suite, or only the ids `TESTS` names. |
| `check` | `lint` and `test`. |
| `select BASE=<ref>` | The test ids the change from `<ref>` reaches, one a line, or `all`, and nothing else. |
| `check-fast BASE=<ref>` | `lint`, then `test` with the ids `select` prints, the whole suite on `all`, and no test on an empty selection. |
| `borders BASE=<ref>` | The borders of the change from `<ref>`, with the pull request's labels in `LABELS`: a change across two features passes only with the label `cross-cutting`. The shared check's lint reads no labels, so `lint` leaves this to `borders`. |
| `generate` | Each generator, which writes its files again from the manifests. |

The standard's guards come from jstack at the tag `.repo-standard.yml` pins.
The Makefile clones that tag into `.cache/` the first time a target needs it, and runs the guards with `python3`, so a repo of any stack needs only git and python3 for them.
`REPO_STANDARD_UPSTREAM` names another place to clone from, as the test does.

## An adapter

An adapter gives the Makefile three commands, in the file `stack.mk` of its `scripts/` folder, which the Makefile includes, as python-uv's `features/repo-standard/adapters/python-uv/scripts/stack.mk` does:

| Variable | What it runs |
|---|---|
| `STACK_LINT` | The stack's own lint. |
| `STACK_TEST` | The test runner, to which the target `test` appends the ids of `TESTS`. |
| `STACK_SELECT` | The selection, given the base as its one argument. |

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
Such a repo copies each of its adapters' scripts into `scripts/`, and no `stack.mk`: the Makefile sees `stacks:` and hands `lint`, `test` and `select` to the standard's driver, `python3 -m repo_standard stacks`, at the tag the config pins.
The targets keep their names and what they print.

| Target | What the driver does |
|---|---|
| `lint` | Runs every stack's lint, and fails when any failed. |
| `test` | Runs every stack's suite, or, given ids in `TESTS`, each path in the stack whose root holds it, and `stack:<name>` as that stack's whole suite. |
| `select BASE=<ref>` | Joins the stacks' selections, as below. |

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
| `select BASE=<ref>` | `node.py select --roots <root> <ref>`, from the repo's `scripts/`. |

`repo-standard conform` fails a root whose `package.json` has no `check` or no `test` script, under the rule [Each check has one make target](standard.md#each-check-has-one-make-target).
It warns of a root that pins no Node version, in an `.nvmrc` or in the `engines.node` of its `package.json`, since CI then runs the runner's Node.
The repo copies the adapter's two scripts, `features/repo-standard/adapters/node-vite/scripts/node.py` and `features/repo-standard/adapters/node-vite/scripts/node_graph.py`, into its `scripts/`, and adds `node_modules/` to its `.gitignore`, as the skeleton's does.

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

Its example feature, `hello-client`, is an npm package, `features/repo-standard/adapters/node-vite/features/hello-client/package.json`, whose `check` script runs `tsc --noEmit` and whose `test` script runs `vitest run`.
Its stack's root is the feature's folder.
`features/repo-standard/tests/test_node_adapter.py` makes a repo of it, installs it with `npm ci` and runs its make targets, and runs the selection on a Svelte client and a React client.
