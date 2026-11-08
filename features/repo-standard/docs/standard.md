# The repo standard

This page is the standard a repo holds to: where its files go, how it maps its features, and what its docs must keep true.
jstack is the repo the standard is taken from, and every rule here is one that jstack's checks enforce today.
Other repos adopt the standard by its contracts, and a stack adapter fills in the commands for their language.

## How to read a rule

Each rule is a `###` heading under one of the parts below.
Its first lines state the contract, which holds in any repo.
The lines under **In jstack** say how jstack meets it.
Its `Enforced by:` line names each file that fails a check when the rule breaks, as a path from the repo root.
A rule names at least one such file under `scripts/`, `.github/` or `features/`, and `features/repo-standard/tests/test_standard_cites.py` fails on a rule that names none.

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
The manifest lists the feature's pages, and the first is its main page.

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
