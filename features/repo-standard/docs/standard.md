# The repo standard

This page is the standard a repo holds to: where its files go, how it maps its features, what its docs must keep true, and how it checks, tests and ships a change.
jstack is the repo the standard is taken from, and every rule here is one that jstack's checks enforce today.
Other repos adopt the standard by its contracts, and a stack adapter fills in the commands for their language.

## How to read a rule

Each rule is a `###` heading under one of the parts below.
Its first lines state the contract, which holds in any repo.
The lines under **In jstack** say how jstack meets it.
Its `Enforced by:` line names each file that fails a check when the rule breaks, as a path from the repo root.
A rule names at least one such file under `scripts/`, `.github/`, `features/` or `testing/`, and `features/repo-standard/tests/test_standard_cites.py` fails on a rule that names none.
The rules of the part Versions are the one exception: no check of the tag exists before the tag does, so they name no such file, and the test holds that part to its two rules and the tag's name instead.

## Layout

### Every file has a place

A tracked file sits under one of the layout's folders, or is one of the root's own files, listed by name.
A file anywhere else fails the check.

**In jstack** the layout is `features/`, `schemas/`, `scripts/`, `testing/` and `.github/`.
The root's own files are the rows of `REPO_OWNERS` in `scripts/jtrees/crawl.py` that sit outside those folders, such as `Makefile`, `pyproject.toml`, `install.sh` and `README.md`.
`scripts/lint-borders.py` warns on each file outside both, and CI runs it with `--hard`, which fails on any warning.

Enforced by: `scripts/lint-borders.py`, `.github/workflows/borders.yml`

### Every path has one owner

Each tracked path has exactly one owner: a feature, or the repo itself.
A path with no owner, or with two, fails the check.

**In jstack** a feature owns its folder, `features/<name>/`, and every path under it.
The repo owns the paths of `REPO_OWNERS` in `scripts/jtrees/crawl.py`: its build, CI, generator, lints, shared test tooling and entry points (`INFRA`), and the shared files the generator writes (`SHARED-DELETE`).
A repo row that claims a path under a feature's folder makes a second owner.

Enforced by: `scripts/jtrees/crawl.py`, `scripts/lint-borders.py`, `.github/workflows/borders.yml`

### A feature owns its folder and nothing else

A feature's files live in its own folder, and a feature claims no path outside it.

**In jstack** the manifest has no key that claims a path, and the manifest schema is closed, so a manifest that tries to add one fails to validate.
Where a file must sit outside every feature, as an entry point a harness looks for at the root, the repo owns it in `REPO_OWNERS`.

Enforced by: `scripts/jtrees/crawl.py`, `scripts/jtrees/schema.py`, `features/repo-guards/tests/test_lint_borders.py`

### A change touches one feature

A pull request changes the files of one feature, together with the repo's own files.
A change across two features or more carries the `cross-cutting` label, which a maintainer adds.

**In jstack** `scripts/lint-borders.py` reads the diff from the base and the pull request's labels.
`.github/workflows/borders.yml` runs it again whenever a label is added or taken off, and `borders` is a check that a pull request into `main` needs to pass (`features/repo-guards/main-ruleset.json`).

Enforced by: `scripts/lint-borders.py`, `.github/workflows/borders.yml`, `features/repo-guards/main-ruleset.json`

### A feature's parts sit in named folders

Inside a feature's folder, each kind of part has one folder of its own, so a tool finds a part by its kind and name without a list kept by hand.

**In jstack** the kinds are these:

| Part | Where |
|---|---|
| The manifest | `feature.json` at the folder's top |
| A skill | `SKILL.md` at the top, or `skills/<skill>/SKILL.md` |
| A playbook | `playbooks/<name>.md`, or under a skill's folder |
| A template | anything under `templates/` |
| A Python package | `src/<package>/` |
| A hook | `hooks/<name>.sh` |
| A systemd unit | `units/<name>.service` or `.timer` |
| A page of docs | `docs/<name>.md` |
| A test | `tests/test_<name>.py` |

The crawl finds skills, playbooks and templates only at the spots its `SPOTS` table names, and the manifest schema holds each declared path to its folder's pattern.

Enforced by: `scripts/jtrees/crawl.py`, `scripts/jtrees/schema.py`

## Feature map

### Every feature has a manifest

Each feature's folder holds a manifest that names the feature and says in one sentence what it does.
The manifest validates against the repo's feature schema, and its name is its folder's name.

**In jstack** the manifest is `features/<name>/feature.json`, and its schema is `schemas/feature.schema.json`.
Its `$schema`, `name` and `description` are required, and the schema is closed: it refuses any key it does not list.
A folder of `features/` with a `SKILL.md` and no manifest takes its name and description from the skill's front matter, and a folder with neither fails.

Enforced by: `scripts/jtrees/crawl.py`, `scripts/jtrees/schema.py`, `scripts/generate-jstack-trees.py`

### A manifest declares only what exists

Each path a manifest declares is a file in the feature's folder.
A declared path that does not exist fails the check.
A glob of the core's `reads`, which names files across the repo that the feature's tests read, matches at least one file.

**In jstack** the crawl checks each package, page, hook, status line, git hook and project skill a manifest declares.
A skill a manifest marks `hidden`, or a playbook it marks `nameable`, must be one the feature owns.

Enforced by: `scripts/jtrees/crawl.py`

### Each item has one feature and one name

Each skill, playbook and template belongs to exactly one feature, and no two items of one kind share a name.
A skill's front matter names the skill its folder names.

**In jstack** the crawl assigns each item it finds to the feature whose folder holds it, and fails an item with no feature owner, a second owner or a name another item of its kind has.

Enforced by: `scripts/jtrees/crawl.py`

### The indexes are generated from the manifests

Every list of features, and every list of what a feature ships, is written by a generator from the manifests and the feature folders.
Nobody edits a generated list by hand: a change edits the manifest or the folder, then runs the generator.

**In jstack** `make trees` runs `scripts/generate-jstack-trees.py`, which writes `skills.json`, the regions of `README.md` and `CATALOG.md` between `<!-- generated: <part> -->` and `<!-- generated: end -->`, the regions of `pyproject.toml` between `# generated: <part>` and `# end generated`, and the `pages` region of a page of docs.
`pyproject.toml`'s regions hold the commands, the wheel's packages, and the paths pytest and ruff read, so a new feature's tests run once the generator has run.

Enforced by: `scripts/generate-jstack-trees.py`, `scripts/jtrees/outputs/docs.py`, `scripts/jtrees/outputs/pyproject.py`, `scripts/jtrees/outputs/jstack.py`

### A stale index fails the lint

The lint runs the generator in a mode that writes nothing and fails when an output differs from the file on disk.
So a change to a manifest that leaves an index behind cannot merge.

**In jstack** `make lint` runs `scripts/generate-jstack-trees.py --check`, which names each stale or missing output.
CI's `lint` job in `.github/workflows/check.yml` runs `make lint` on every pull request.

Enforced by: `scripts/generate-jstack-trees.py`, `scripts/jtrees/check.py`, `.github/workflows/check.yml`

## Docs

### A feature's pages live in its folder

The pages about a feature live in its own folder, so a change to the feature and to its pages stays one feature's change.
The manifest lists the feature's main page first, and each page it lists is in the feature's folder.

**In jstack** the pages are under `features/<name>/docs/`, and the manifest's `docs` key lists them.
The `commands` region of `README.md` links each command to the first page of its feature.

Enforced by: `scripts/jtrees/outputs/docs.py`, `scripts/jtrees/crawl.py`, `scripts/lint-borders.py`

### Pages that span every feature belong to no feature

An index that lists every feature lives on a page that no feature owns.
A feature's own page holds no such index, so a new feature changes its own folder and the generated root pages alone.

**In jstack** the parts `commands`, `catalog` and `hooks` live only in `README.md` and `CATALOG.md`, which the repo owns.
The generator refuses a page a feature owns that holds one of those regions, and a root page that has lost the region it must hold.
A page with a folder of the same name beside it, such as `features/jbus/docs/jbus.md` beside `features/jbus/docs/jbus/`, carries a generated `pages` region that lists the pages in that folder.

Enforced by: `scripts/jtrees/outputs/docs.py`, `scripts/generate-jstack-trees.py`

### The docs say what the tree has

A page names only paths, links and anchors that exist, and only skills and commands the repo has.
A count a page gives matches the tree.

**In jstack** `scripts/check-jstack-docs.py` reads `README.md`, `CATALOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, every page under `features/<name>/docs/` and every skill, and fails on a path that does not exist, a broken link or anchor, an unknown slash command, a wrong count and a model id the role table does not list.
`make lint` runs it.
`features/repo-guards/tests/test_names_resolve.py` holds a module, symbol or path named in backticks to one that exists.

Enforced by: `scripts/check-jstack-docs.py`, `features/repo-guards/tests/test_docs_tree.py`, `features/repo-guards/tests/test_names_resolve.py`

### A command's page matches its help

The page of a command names each verb and flag the command's help names, and no verb or flag the command lacks.

**In jstack** the test asks each command that `pyproject.toml` lists for its `--help`, and each verb's help down the tree, then reads each page against it, and reads the code in each page as a shell would.

Enforced by: `features/repo-guards/tests/test_docs_true.py`

### New prose has one sentence per line

Each line of Markdown that a change adds holds at most one sentence, so a review comments on one sentence and a diff shows one.
Old lines stay as they are until a change touches them.

**In jstack** `features/writing/scripts/prose_lint.py` reads the lines a diff adds to the Markdown of `features/` and the other docs folders.
`make check-fast` runs it, and so does CI's `lint` job.

Enforced by: `features/writing/scripts/prose_lint.py`, `.github/workflows/check.yml`

## Scripts

### Each check has one make target

A repo's checks run through a few make targets that every repo names the same, and CI runs its lint of the tree and its tests through those targets.
`make lint` runs every lint of the tree, `make test` runs the tests, or only the files `TESTS` names, and `make check` runs both.
A lint that reads only the lines a change adds needs the change's base, so it runs by name beside `make lint` and is no part of the tree's lint.
A stack adapter fills in the commands under each target.

**In jstack** the targets are in the `Makefile`.
`make test` runs pytest on several workers, counted from the processors the run may use, and `testing/tests/test_check_command.py` holds that count.
`.github/workflows/check.yml` runs the lint of the tree and the tests through `make lint`, `make test` and `make check`.
The prose lint, `features/writing/scripts/prose_lint.py`, reads the lines a diff adds, so the `lint` job runs it by name with the base, and so does `make check-fast`.

Enforced by: `.github/workflows/check.yml`, `testing/tests/test_check_command.py`, `testing/tests/test_workflows.py`

### The repo's own scripts live in scripts/

A script that serves the whole repo, such as the generator, a lint across features, the test selection or the green-tree lookup, lives under `scripts/`, and the repo owns it.
A script that serves one feature lives in that feature's folder.

**In jstack** `scripts/` holds, among others, `generate-jstack-trees.py`, `check-jstack-docs.py`, `lint-borders.py`, `select_tests.py`, `green_tree.py` and `no_ai_trailers.py`.
The writing feature's lints, `prose_lint.py` and `comment_lint.py`, live under `features/writing/scripts/`.

Enforced by: `scripts/jtrees/crawl.py`, `scripts/lint-borders.py`

### A script CI runs before setup needs only the runner's python

A script that CI runs before it installs the project's dependencies imports only the standard library and the repo's own modules, so a selection or a lookup never waits on an install.

**In jstack** `check.yml`'s `reuse` job runs `scripts/select_tests.py`, `jmerge.reuse` and `scripts/no_ai_trailers.py` in the runner's `python3`, before any `uv sync`.
`scripts/green_tree.py` runs the same way at the start of each part of main's full run.

Enforced by: `.github/workflows/check.yml`, `testing/tests/test_workflows.py`

## Guards

The guards are the checks that keep the tree in its shape, beside the tests of what the code does.
The layout borders, the stale-index check and the docs checks are the rules of the parts above.

### A cap on size only shrinks

A module, and a test file, has a cap on its lines.
A file over the cap when the cap was set sits on a list with its length, and a change that brings it under the cap takes it off the list, so the list only shrinks and no file joins it.

**In jstack** the caps and their lists are in the two tests.

Enforced by: `features/repo-guards/tests/test_module_size.py`, `features/repo-guards/tests/test_test_size.py`

### Code holds no plain comment

Code says what it does through its names and its docstrings, so a plain comment fails the check.
A comment a tool reads as an instruction, such as a shebang or a type pragma, is not a plain comment.

**In jstack** the test reads Python with `tokenize` and shell character by character.
`make lint` also runs `features/writing/scripts/comment_lint.py` on the files a change touches, which names each comment and fails nothing.

Enforced by: `features/repo-guards/tests/test_no_comments.py`

### Shell runs on macOS as well as on Linux

Every shell script, and every shell block of the docs, parses under the bash and runs on the tools that macOS ships.

**In jstack** one guard fails on a GNU-only command or flag and names the form that works on both, and the other parses each script under bash 3.2.

Enforced by: `features/repo-guards/tests/test_portable_shell.py`, `features/repo-guards/tests/test_bash32.py`

### A test runs the code

A test that reads a file's words and runs nothing passes on any behaviour and fails on a rewording, so it fails the check.

**In jstack** the guard reads each test module with `ast` and follows what each test calls until it reaches code that runs.

Enforced by: `features/repo-guards/tests/test_run_not_read.py`

## Testing

### A feature's tests live in its folder

A feature's tests sit under its own folder, and the test tooling every feature shares sits in one folder the repo owns.
No two test files share a name.

**In jstack** the tests are `features/<name>/tests/test_<name>.py`, and the shared fixtures and helpers are under `testing/`.
The generator writes the paths pytest reads into `pyproject.toml`, so a new feature's tests run once the generator has run.

Enforced by: `scripts/jtrees/outputs/pyproject.py`, `features/repo-guards/tests/test_test_size.py`

### A change selects its tests

`make select BASE=<ref>` prints the test ids that the change from `<ref>` to `HEAD` reaches, one a line, or the single word `all` when the change reaches every test.
A selection names the tests and never stands in for the suite: what it misses, the safety net below catches.

A repo can hold several stacks, such as a Go API and a Python program, each over its own roots, as the config's `stacks:` declares them.
A test id is then a path from the repo's root, which the stack whose root holds it runs, or `stack:<name>`, which means every test of that one stack.
`all` still means every test of the repo, so a change that reaches a whole stack prints `stack:<name>` and never `all`.
A stack's roots hold its own root files, such as its lock file, so a change to one reaches that stack and no other.

Browser tests are selected from the change like any other test, down to the one test of a spec that the change reaches, and never from a hand-kept list of specs.
A browser test's id is Playwright's test-list form, `<spec>` or `<spec> > <title>`, and the shared check runs those ids in its browser job and no others.
A test is reached by the URLs it opens and by its spec's own imports.
A URL maps to the files of its route: a SvelteKit page with every layout above it, or the row of a React router table with the components it names.
The change reaches each test whose route files, or the files they import, hold a changed file, where an import of names from a barrel follows only those names.
A spec that runs a table of screens is selected by row: a change inside one row selects that row, and a change to a helper selects the rows that name it.
A spec that no path reaches, or that opens a URL that matches no route, fails conformance, unless the config names it as one that every change of the app selects.
The browser tests run on a mock of the API, and a contract the lint runs holds each route the mock answers to the real API, so a change to the real API selects no browser test and the lint fails on a mock route the real API lost.

**In jstack** `make select BASE=<ref>` runs `python3 scripts/select_tests.py <ref> HEAD`, which prints test files, and `make check-fast BASE=<ref>` runs the lint and the files it prints.
The script follows imports, fixtures, the names a test reads and the files a test includes, and its rules are in the script's docstring.

Enforced by: `scripts/select_tests.py`, `testing/tests/test_select_tests.py`, `testing/tests/test_select_tests_rules.py`

### A shared path forces the whole suite

A change to a path that every test rests on selects `all`, whatever else it touches.
In a repo of several stacks, so does a path outside every stack's roots, unless it is a page of Markdown, a file in a feature's `docs/` or its `feature.json`.
A change to the selection itself, or to the files that run it, selects the tests that read it: a pull request's check selects its tests by its own new version of them, and main's run of the whole suite after each merge catches what that version missed.

A browser test rests on more than its imports, so these force every browser test of a stack, by kind:

- The app's shell and layouts: `app.html`, `index.html`, a React entry and its router file force every test, a root layout reaches every test through the graph, and a nested layout reaches the routes under it.
- Global CSS: the root layout or the entry imports it, and the graph follows each `@import`, so a change to it reaches every test.
- Tailwind: a class in markup reaches only the tests that reach its file, and the Tailwind, PostCSS, Vite and Svelte configs force every test.
- The service worker and the files it imports reach each spec that runs with service workers allowed.
- Static assets: a file under `static/` or `public/` is reached by URL, not by import, so it forces every test, and an asset imported from the source is reached through the graph.
- i18n catalogs: a catalog the code imports is reached through the graph, and one loaded by URL sits in `static/` or `public/` and forces.
- The test harness: the Playwright configs, the e2e package and its lockfile, the mock API, whatever its files are named, the server the tests run against and the shared fixture.

**In jstack** the paths are `EVERY_RUN` in `scripts/select_tests.py`: `pyproject.toml`, `uv.lock` and the root `conftest.py`.
The script itself, the `Makefile`, `.github/workflows/check.yml` and the plugins of `testing/` select the tests that import or name them instead, and the whole suite runs on main, nightly and before a release.

Enforced by: `scripts/select_tests.py`, `testing/tests/test_select_tests_rules.py`

### Main runs the whole suite after each merge

Each push to main runs every test, so a test a selection missed fails on main within one merge.
A test that failed on main joins the selection of every pull request until it passes again.

The shared check keeps this record as data, not as a log.
Each part's `make test`, and the browser job's target `e2e`, writes the id of each test that failed to `$REPO_STANDARD_FAILED`, in the form `make select` prints, which each adapter reads from its test runner's own report.
On a push to main a failed part or browser job runs those ids once more, and the run's `passed` job writes one ledger row per failed id to the artifact `miss-ledger-<run id>`, kept 90 days.
A row holds the id, the merged pull request, whether `make select BASE=HEAD^1` on the main commit selects it, and a class: `flaky` where it passed when run again, `miss` where the selection did not reach it, `race` where it did but no passed check of the pull request left the marker of the two trees that merged, and `env` otherwise.
A pull request's plan then adds each id a ledger of main's runs of the last 30 days names, unless it was `flaky`, a later green run of main passed it, or its path is gone.
Runs are ordered by run id, and a lookup that cannot ask GitHub warns and adds nothing.
`repo-standard misses --days 30` prints the miss rate, rows of class `miss` per merged pull request, and the rows.

**In jstack** `check.yml`'s `full-shard` job runs `make check` in four parts on each push to main, and its `full` job passes only when all four did.
A pull request's `reuse` job runs `select_tests.py --failed-on-main 30`, which reads the logs of main's red runs of the last 30 days and adds each test file they name that no later green run of main has passed.

Enforced by: `.github/workflows/check.yml`, `testing/tests/test_workflows.py`, `.github/workflows/repo-standard-check.yml`, `features/repo-standard/tests/test_misses.py`

## CI

### A pull request runs the selection, the lint and the selected tests

A pull request's check selects its tests from the change, runs the lint, and runs the selected tests split into parts that run side by side.
It needs no run of the whole suite, which main's run after the merge does.
The selected browser tests run in a job of their own, on the built app with a mocked API and never on a live stage, and the job is skipped when the change selects none.
A browser test that passes only on a retry fails the job: a retry may keep a trace, and never turns a flaky test green.

**In jstack** `.github/workflows/check.yml` runs on each push of a pull request, a draft too, and a new push cancels the older run.
Its `reuse` job runs `python3 scripts/select_tests.py --parts 8 HEAD^1 HEAD`, which deals the selected files out to eight parts, or `all` where the change forces it.
Its `lint` job runs `features/writing/scripts/prose_lint.py HEAD^1` and `make lint BASE=HEAD^1`.
Its `check-shard` job runs `make test TESTS=<part>` in each of the eight parts.

Enforced by: `.github/workflows/check.yml`, `testing/tests/test_workflows.py`

### One required check gathers the rest

A pull request into main needs one check to pass, and that check passes only when every job of the run passed, or the run reused a pass of the same trees.
Otherwise a part that failed, was cancelled or never ran fails it.

**In jstack** the `check` job needs `reuse`, `lint` and every part of `check-shard`, and `check`, `borders` and `macos` are the checks the ruleset of main requires.

Enforced by: `.github/workflows/check.yml`, `features/repo-guards/main-ruleset.json`

### A pair of trees passes once

A check that passed on a head merged over its base passes again for the same two trees without running its tests.
So a stacked change that moves onto main, where the move replays the same trees, adds no round of the suite.

**In jstack** the `reuse` job asks `jmerge.reuse` whether a passed check already checked GitHub's merge of the head and that base, and on a yes each part of `check-shard` still starts, reads the `selection` artifact and skips its `part` and `make test` steps, so the parts run no tests, and `check` passes on the reuse.

Enforced by: `features/jmerge/src/jmerge/reuse.py`, `.github/workflows/check.yml`

### A passing tree leaves a marker

A run that passed the whole suite on a tree leaves a marker named for that tree, and a later run of the same tree skips the suite.
The tree is the key, not the commit, so a tag or a merge with the same files reads the same marker.

**In jstack** the marker is an artifact, `green-tree-<tree id>`, which main's `full` job uploads, and a pull request's `check` job too where its selection was `all`.
`scripts/green_tree.py` looks it up at the start of each part of main's full run.

Enforced by: `scripts/green_tree.py`, `.github/workflows/check.yml`

## Deploy

### Every deploy entry refuses a tree that is not green main

A repo ships through its deploy entries alone, and each one refuses a tree that is not main's, clean, and marked green by main's check.
It refuses before it builds, tags or uploads anything, and its refusal names the fix.

Each entry is a make target, listed in the config's `deploy` part, whose recipe runs `repo-standard green` before its first other command, and which has no prerequisite that make would run first.
`repo-standard green` exits 0 only when the checkout is clean, `HEAD` is main on the remote now, as `git ls-remote origin refs/heads/main` gives it and not a local `origin/main` that may be stale, and a run of `check.yml` passed the tree of `HEAD`.
It reads that from the marker `green-tree-<tree>`, and, where the marker expired or is missing, from the push run of `check.yml` on main for `HEAD`'s commit, when its conclusion is success.
It exits 1 with each of the three that failed, and 2 when it cannot ask the remote or GitHub.
The shared check workflow keeps the marker 90 days, which is as long as GitHub keeps a run by default.

**In jstack** the one deploy entry is the release, and it is waived: `make release` checks main, a clean tree and `origin/main` itself, then runs `make release-green`, which fails unless a green run of `check.yml` left the marker for the tree of `HEAD`.
`.github/workflows/release.yml` runs only on a pushed `v*` tag, and runs `make release-green` again on the tag's own checkout before `make dist` and the release.

Enforced by: `features/repo-standard/src/repo_standard/green.py`, `features/repo-standard/src/repo_standard/rules.py`, `.github/workflows/release.yml`

### Only a deploy entry runs a deploy command

A deploy command runs only in a deploy entry's recipe, or in a script that runs `repo-standard green` before it, so no path to prod steps around the refusal above.
Conform looks for these deploy commands in each tracked shell script, each make recipe and each workflow, with any global flags between the tool and its verb:

- `aws s3 sync` and `aws cloudfront create-invalidation`
- `sam deploy`
- `terraform apply`
- `cdk deploy`

A workflow step runs a deploy entry rather than a deploy command, and a make target that is not a deploy entry runs none.
A comment line is not read.
The list is kept beside the rule, in `features/repo-standard/src/repo_standard/rules.py`, and it does not see a deploy run from Python, through a package script such as `npm run deploy`, or by a workflow's `uses:` action.

**In jstack** no script, recipe or workflow runs one: the release builds and publishes through `make dist` and GitHub's release, which are not deploy commands.

Enforced by: `features/repo-standard/src/repo_standard/rules.py`

### A deploy is behind the `touches prod` gate

An agent never starts a deploy on its own default.
A deploy, a change to prod data or a message to anyone outside is the gate `touches prod or real users`, which holds until the user says go.

**In jstack** the gates are listed in `features/home/templates/gates.md`, and the `door-command` hook stops a command that matches one, such as a `deploy` or a `release`, until the user's word opens it.

Enforced by: `features/jbus/hooks/door-command.sh`, `features/jbus/src/jbus/party.py`, `features/home/templates/gates.md`

## Versions

### The standard is versioned by a tag

Each version of the standard is a git tag of jstack, `repo-standard-vN`, where `N` is a whole number that goes up by one with each version.
A repo that adopts the standard pins one version in its `.repo-standard.yml`, and its CI runs the shared check workflow and the conformance tool at that tag, so the standard changes under a repo only when the repo moves its pin.

### A breaking change takes a new version

A change to the standard is breaking when a repo that conformed at `repo-standard-vN` can fail at the new version with no change of its own.
These are breaking: a new rule at the error level, a rule made stricter, a make target or command a contract renames or drops, and a key of `.repo-standard.yml` renamed, dropped or given a new meaning.
These are not: a change of wording that keeps each rule's meaning, a new rule at the warn level, a rule made looser, and a new stack adapter.
A breaking change goes out only in a new version, `repo-standard-vN+1`, and a change that breaks nothing may go out in the next version or wait for one.

### A file a version owns is that version's copy

A version owns some of the files a repo takes from the skeleton and its adapters: the `Makefile`, the workflows, the schemas and the scripts.
The repo keeps each equal to the copy at the tag it pins, so a move to the next version replaces them and loses nothing, and the repo adds its own make targets in `local.mk`, which the `Makefile` includes.
A file the repo keeps as its own is named under `local:` in `.repo-standard.yml`, with the reason, and is not compared.
`repo-standard conform` warns of each other file that differs from its copy, with the runner's labels in the caller's `check.yml` left out, and `repo-standard upgrade --to N` writes version N's copies.
