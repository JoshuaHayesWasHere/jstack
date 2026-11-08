# The skeleton and its adapters

A repo starts on [the repo standard](standard.md) from two folders of this feature.
`features/repo-standard/skeleton/` holds what every repo has, whatever its stack.
An adapter, `features/repo-standard/adapters/python-uv/` or `features/repo-standard/adapters/go/`, holds what one stack adds: the commands under the make targets, its selection of tests, and an example feature.
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
The config waives five, each with its reason, and `repo-standard conform` prints each waiver on every run:

- Four rules need a file of the repo's own to enforce them: a command's page, its prose lint, its shell scripts and a guard over its tests.
  When the repo adds the file, it names it under `enforced-by` and drops the waiver.
- `a-pull-request-runs-the-selection-the-lint-and-the-selected-tests` is met by the shared check, which conform does not read yet.

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

A test whose imports do not show what it runs, such as one that runs a module in a subprocess, is not selected.
Main's full run after each merge runs it, as the standard's rule [Main runs the whole suite after each merge](standard.md#main-runs-the-whole-suite-after-each-merge) says.

### go

The go adapter runs Go modules wherever they sit in the tree, with no go.work, through one script, `features/repo-standard/adapters/go/scripts/go.py`, which runs in `python3` alone:

| Command | What it runs |
|---|---|
| `go.py lint` | `gofmt -l` and `go vet ./...` in each module, and fails when gofmt names a file. |
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

`reads`, a key of the core manifest schema, lists the files a feature's tests read that its imports do not show, such as a page another feature owns, which a test opens.
Each entry is a glob from the repo's root, in which `*` crosses folders, and `repo-standard conform` fails a glob that matches no file.
A file a test reads that no `reads` names is still caught by main's full run after each merge.
