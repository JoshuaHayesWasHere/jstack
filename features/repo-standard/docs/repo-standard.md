# repo-standard

`repo-standard` holds a repo to [the repo standard](standard.md).
Its verb `conform` checks every rule of the standard at the version the repo pins, and its other verbs run one guard each, as [the guards' page](guards.md) says.
It reads the repo's `.repo-standard.yml` and uses the Python standard library alone.

## Run it from any repo

A repo needs no copy of the tool: `uvx` runs it from jstack at the tag the repo pins.

```sh
uvx --from git+https://github.com/JoshuaHayesWasHere/jstack@repo-standard-v3 repo-standard conform
```

In jstack, the command is on the path of the project's environment, so `uv run repo-standard conform` runs it.
CI's `lint` job in `.github/workflows/check.yml` runs it there, so the required check `check` fails when it does.

## The verbs

| Verb | What it does |
|---|---|
| `conform` | Checks every rule of the standard, and exits 1 on an error. |
| `borders` | Checks the layout's borders and, with a base, that a change touches one feature. |
| `stale` | Runs each generator in its check mode, which writes nothing. |
| `docs` | Checks that the docs name only paths and make targets the tree has. |
| `size` | Checks each file's length against its cap. |
| `comments` | Checks that code holds no plain comment. |
| `plan` | Prints what the jobs of [the shared check workflow](check-workflow.md) run, and checks nothing. |
| `stacks` | Runs `lint`, `test`, `select` or `e2e` over each stack of a repo whose config sets `stacks:`, as [the skeleton's page](skeleton.md#several-stacks) says. |
| `upgrade` | Moves the repo to another version of the standard, as [upgrade](#upgrade) says. |
| `green` | Says whether the checkout may deploy: it exits 0 on a clean checkout of the remote's main whose tree passed `check.yml`, as [the standard's rule](standard.md#every-deploy-entry-refuses-a-tree-that-is-not-green-main) says. |
| `routes` | Fails on each route a mock API answers that the real API lacks, as [the skeleton's page](skeleton.md#the-mock-api-and-its-contract) says. |
| `floor` | Prints the python3 it runs in and the standard's python3 floor, as [the standard's rule](standard.md#a-script-ci-runs-before-setup-needs-only-the-runners-python) says. |
| `misses` | Prints the miss rate of main's runs and the ledger's rows, as [the shared check's page](check-workflow.md#the-tests-that-failed) says. |

`repo-standard stacks lint` runs every stack's lint, `repo-standard stacks test [ids]` runs every stack's tests or the ids it is given, `repo-standard stacks select <base>` prints the ids the change from `<base>` reaches, and `repo-standard stacks e2e [<file>]` runs the browser tests of each stack with `e2e:`, or only the ids in the file, one a line.
`repo-standard stacks test --shard K/N` runs part K of N of the whole suite: each stack's listed ids, dealt to the parts in turn.
The skeleton's Makefile runs them from the repo's root, and they take no flag.

`repo-standard routes --producer <cmd> --mock <cmd>` runs each command in a shell and reads no config.

`repo-standard misses --days 30` prints the miss rate of the last 30 days, rows of class `miss` per merged pull request, and each row.
The shared check runs its other two forms: `repo-standard misses record --failed <dir> --out <dir>` writes the ledger of main's commit, and `repo-standard misses failing --days 30` prints the ids a pull request's selection adds.
It reads GitHub through `gh api`, for `$GITHUB_REPOSITORY` or the repo `gh repo view` names, and the caller's workflow from `$GITHUB_WORKFLOW_REF`, else `check.yml`.

Every verb but `stacks`, `routes`, `misses` and `floor` takes `--root` for another checkout, and every verb but `stacks`, `green`, `routes`, `misses` and `floor` takes `--config` for another config file than `<root>/.repo-standard.yml`.
`borders` alone reads `--base <ref>`, `--labels a,b` and `--hard`, which [the guards' page](guards.md) explains.
`conform` and `upgrade` read `--upstream`, `conform` alone reads `--list`, and `upgrade` alone reads `--to N`.
`plan` alone reads `--event`, by default `$GITHUB_EVENT_NAME`, and `--selection <file>`, the test ids the repo's select target printed.
A verb exits 2 when it cannot read the config or the tree.
`repo-standard floor` takes no flag, and `python -m repo_standard` refuses a python3 under the floor before any verb, with a message that names the floor.
`green` reads no config, exits 1 with each reason the checkout may not deploy, and exits 2 when it cannot ask the remote's main or GitHub's API, which it asks through `gh`.

## conform

`repo-standard conform` runs one check for each `###` rule of `features/repo-standard/docs/standard.md`.
A rule's id is its heading's anchor, so `standard.md#a-change-selects-its-tests` is the text of the rule `a-change-selects-its-tests`.
`repo-standard conform --list` prints each rule's level and id, and checks nothing.

It prints one line for each fault, each waiver and each note, then a count:

```text
error a-change-selects-its-tests: Makefile: has no `select` target
waiver every-file-has-a-place: the layout moves into this file in the next pull request
note: repo-standard-v3 is out, and this repo pins v2: move the pin when ready
conform repo-standard-v2, 35 rules: errors 1, warnings 0, waived 1
```

### Levels

Each rule has a level, which `--list` shows.
A fault of an `error` rule fails the run.
A fault of a `warn` rule prints and fails nothing.

### How each rule is checked

Most rules are checked from the tree: a guard runs, or the tool reads the targets of the Makefile and the make files it includes, the workflows under `.github/workflows/`, the manifests or the config.
A workflow that calls the shared check at a version's tag, `repo-standard-check.yml@repo-standard-v<N>`, counts as running what the shared check runs: the selection, the lint and the selected tests on a pull request, and the whole check on main.
A guard whose part the config does not set is a fault of its rule, so a repo never passes a rule it never set up.

Some rules no check of the tree can judge in every stack, such as "a test runs the code".
For each of those, the config's `enforced-by` names the files that enforce the rule in the repo.
Each named file must be tracked, and must be a test file, a workflow, or a file a workflow, the Makefile or a make file it includes names by its path.
A file nothing runs does not meet a rule.
The rules met this way are these:

- `a-commands-page-matches-its-help`
- `new-prose-has-one-sentence-per-line`
- `shell-runs-on-macos-as-well-as-on-linux`
- `a-test-runs-the-code`
- `a-shared-path-forces-the-whole-suite`
- `a-pair-of-trees-passes-once`
- `a-passing-tree-leaves-a-marker`

### Waivers

The config may waive a rule, with a reason:

```yaml
waivers:
  - rule: a-change-selects-its-tests
    reason: make check-fast calls scripts/select_tests.py by name until the select target lands
```

A waived rule still runs, and its faults print as `waived` and fail nothing.
Every waiver prints with its reason.
A waiver with no reason fails the run, and so does a waiver for a rule the standard does not have.
A waived rule that passes prints a note that its waiver can go.

A waiver may name the version by which the repo means to meet the rule, as `until: repo-standard-vN`.
Once the repo pins version N or a later one, the waiver prints a warning that it is due, which fails nothing.

### Files a version owns

Some files a repo takes from the skeleton and its adapters belong to the version it pins, as [the skeleton's page](skeleton.md#what-a-version-owns) says.
The rule `a-file-a-version-owns-is-that-versions-copy` warns of each that differs from its copy at the pinned tag, or is missing.
In the caller, `.github/workflows/check.yml`, the inputs `runner`, `browser-channel` and `timeout-minutes` of the call of the shared check are left out of the comparison, since they are the repo's own, as [the shared check's page](check-workflow.md#call-it) says; the job `check` takes its `runs-on:` from `runner`.
The tool reads the tag's copies from its own tree when that tree holds the skeleton, as a clone of the tag does, and otherwise from the clone in the repo's `.cache/`, which it makes from `--upstream` when it is not there.

The config's `local:` keeps an owned file as the repo's own, with the reason:

```yaml
local:
  .github/workflows/check.yml: the check also builds the app's image
```

A file `local:` names is not compared, and `upgrade` leaves it as it is.
A `local:` entry with no reason fails the run.

### Versions

The config pins a version of the standard as `standard: N`, for the tag `repo-standard-vN` of jstack.
The tool is the standard at one version, and judges by that version's rules, so a pin of another version fails the rule `a-breaking-change-takes-a-new-version`.

The tool lists the `repo-standard-vN` tags of `--upstream`, by default jstack on GitHub, and prints a note when a newer version is out.
The note fails nothing: a repo moves its pin when it chooses to.
When the tags cannot be listed, the tool prints a note and goes on.
`--upstream ""` skips the lookup.

## The config's parts for conform

Beside the guards' parts, which [the guards' page](guards.md) lists, `conform` reads these keys of `.repo-standard.yml`:

```yaml
standard: 3
deploy: [make release]
enforced-by:
  a-test-runs-the-code: [tests/test_run_not_read.py]
waivers:
  - rule: a-change-selects-its-tests
    reason: the select target lands with the python-uv adapter
```

`local` and a waiver's `until` are read as [Files a version owns](#files-a-version-owns) and [Waivers](#waivers) say.
`deploy` lists each deploy entry, and `deploy: []` says the repo deploys nothing.
Each entry is `make <target>` and names `deploy` or `release`, so the `touches prod` gate stops an agent that runs it.
Its recipe runs `repo-standard green` first, and only such a recipe, or a script that runs `repo-standard green` first, runs a deploy command, as [the standard's rules](standard.md#deploy) say.

## upgrade

`repo-standard upgrade --to N` moves the repo to version N of the standard:

```sh
uvx --from git+https://github.com/JoshuaHayesWasHere/jstack@repo-standard-v3 repo-standard upgrade --to 3
make lint
```

It runs from the tool at version N, since only that version's tool reads that version's config, and it refuses any other N, and an N below the repo's pin.
It writes the `standard:` line of `.repo-standard.yml`, the tag of each workflow's call of the shared check, and every file version N owns as N's copy, with the caller's `runner`, `browser-channel` and `timeout-minutes` kept, as [the shared check's page](check-workflow.md#call-it) says.
Where no glob of the config's `owners` names `local.mk`, it adds `local.mk` to the list that names the `Makefile`, or prints that the repo must name it.
It leaves the `local:` files and the seeded ones as they are, and prints each it left with why, and each waiver whose `until` version N reaches.
It writes only a file whose text differs, so a second run writes nothing, and a run after one that stopped part way writes what is left.
