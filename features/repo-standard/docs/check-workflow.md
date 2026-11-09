# The shared check workflow

`.github/workflows/repo-standard-check.yml` is the one check workflow every repo on [the repo standard](standard.md) runs.
A repo calls it from its own `.github/workflows/check.yml` at the tag of the version it pins, so the check changes under a repo only when the repo moves its pin.
The workflow reads the rest from the repo's `.repo-standard.yml` and runs the repo's make targets.

## Call it

/new-home writes the caller from its template, `features/home/templates/check.yml`, and a repo may copy that file by hand.
The caller's job `standard` calls the shared workflow, and its job `check` passes only when the call passed, so `check` stays the one check jmerge and the ruleset wait on:

```yaml
jobs:
  standard:
    uses: JoshuaHayesWasHere/jstack/.github/workflows/repo-standard-check.yml@repo-standard-v1
    with:
      runner: ubuntu-24.04
      command: 'make check'
  check:
    if: always()
    needs: standard
    runs-on: ${{ needs.standard.outputs.runner }}
```

The caller also sets the triggers, the permissions and the concurrency, since a called workflow cannot.
It runs on each pull request, on each push to `main`, on a nightly schedule and by hand, and it grants `contents: read` and `actions: read`, which the marker lookups need.

The `uses:` line's tag and the `standard:` line of `.repo-standard.yml` name the same version, and a version bump moves both.
The plan fails when the config pins another version than the workflow's own.

| Input | What it sets | Default |
|---|---|---|
| `runner` | The label of the runner every job runs on, such as one on the repo's own machines | `ubuntu-24.04` |
| `command` | The repo's check command, which runs alone while the repo has no `.repo-standard.yml` | none |
| `timeout-minutes` | The cap of each part of the tests, of the browser tests, and of the check command | 30 |
| `browser-channel` | A browser the runner has, such as `chrome`, for the browser tests to run in, in place of the Playwright image | none |
| `ref` | The ref of jstack the jobs and the repo's make take the standard's code from, such as a branch of a version not yet tagged | `repo-standard-vN`, the tag of the version `.repo-standard.yml` pins |

The label of a runner on the repo's own machines goes in `runner`.
The workflow gives it back as its output `runner`, and the caller's job `check` runs on it, so a repo whose account cannot start hosted jobs names its own label once.

To run a branch of jstack before its version is tagged, a caller names the branch in both the `uses:` line and `ref`:

```yaml
    uses: JoshuaHayesWasHere/jstack/.github/workflows/repo-standard-check.yml@repo-standard-v2-rc
    with:
      ref: repo-standard-v2-rc
```

The `uses:` line picks the workflow's own file, and `ref` the code its jobs clone, which the workflow cannot learn from the `uses:` line.
The workflow hands `ref` to the repo's make as `REPO_STANDARD_REF`, and the skeleton's Makefile clones that ref into `.cache/<ref>` once; a branch that moves on is taken again after that folder is deleted.
`make lint REPO_STANDARD_REF=<ref>` does the same on a checkout.
`repo-standard conform` takes a `uses:` line at such a branch only when the branch is named for a version, `repo-standard-v<N>-<name>`, and fails one at any other ref, such as `main`.
`repo-standard upgrade --to <N>` moves the `uses:` line to the tag `repo-standard-v<N>` and drops the `ref` input, so the branch can be deleted once the tag is out.

A step that the make targets need first, such as a toolchain the runner lacks or a cache of dependencies, goes in a composite action at `.github/actions/setup/action.yml` in the repo.
The jobs `lint`, `test` and `browser` run that action after their checkout, where the file exists.
The job `plan` runs `make select` before any setup, in the runner's `python3` alone.

## The config's part for the check

```yaml
check:
  shards: 4
  nightly: true
```

`shards` is the number of parts the tests run in side by side, 1 by default and at most 64.
`nightly` turns on the nightly run of the whole suite, off by default.
Both are optional, and a config with no `check` part runs the tests in one part and no nightly run.

## What a run does

The workflow's first job, `plan`, asks once what the run tests, and the other jobs read its answer.
It reads the version `.repo-standard.yml` pins and clones jstack at the tag `repo-standard-vN`, or at the ref `ref` names, which holds the code the workflow runs in the runner's `python3` before any setup.

| Job | On a pull request | On a push to main, a nightly run, a manual run |
|---|---|---|
| `plan` | Asks `jmerge.reuse` whether a passed check of the same two trees is reused, runs `make select BASE=HEAD^1`, and adds the tests main failed (`repo-standard misses failing --days 30`) | Asks `scripts/green_tree.py` whether a green run left a marker for the tree, except on a nightly run |
| `lint` | `make lint BASE=HEAD^1`, then `repo-standard conform` | The same |
| `test` | Each part runs what `plan` dealt it: `make test TESTS=<ids>`, its share of the whole suite, or nothing | Each part runs its share of the whole suite, and on a push to main a failed part runs its failed tests once more |
| `browser` | The target `e2e`, given `E2E_LIST=<file>` with the browser ids `plan` routed it, or given none on `all`, and skipped when `plan` routed it no id | The target `e2e`, every browser test, and on a push to main a failed run runs its failed tests once more |
| `passed` | Passes when `plan`, `lint` and every part passed, and `browser` passed or was skipped, or the pair of trees was reused | Passes when every job passed, or the tree's marker skipped the tests, and on a push to main whose tests or browser tests failed first writes the ledger |

`repo-standard plan` deals a selection out to the parts in turn, and starts no more parts than the selection has ids.
A part dealt the whole suite runs `make test` with one part, and `make test SHARD=<part>/<parts>` with more.
That part runs its share of the suite, not the whole of it: the skeleton's `test` target lists every test id the stacks know and deals them to the parts in turn, by the rule `plan` deals a selection, so across the parts each test runs once.
A part dealt no id runs no test.
A repo whose Makefile is not the skeleton's and that sets `shards` above 1 gives its `test` target a `SHARD` variable that does the same.
An id `make select` prints holds no space, since the part passes its ids to `TESTS` with a space between each.
A browser id is the exception, and `plan` routes it to `browser` instead of a part: an id `<spec> > <title>`, or a `*.spec.*` file under the `testDir` of the Playwright config of a stack whose config sets `e2e:`, as the node adapter's browser selection in the repo reads it.
A `*.spec.*` file outside that `testDir`, such as a unit spec Vitest's `include` names, goes to a part.
An id `stack:<name>` of such a stack goes to both, as that stack's whole suite.

The job `browser` runs in the container `mcr.microsoft.com/playwright:v<version>-noble`, the version the e2e root's `package-lock.json` pins, and the plan fails where it pins none or two e2e roots pin two.
With `browser-channel` set, it runs on the runner instead, prints the browser's version, and the Playwright config reads the channel as `$REPO_STANDARD_BROWSER_CHANNEL`.
The target `e2e` passes `--fail-on-flaky-tests`, so a test that passes only on a retry fails the job, and the job keeps `playwright-report/` and `test-results/` as artifacts unless the run was cancelled.

A reuse of a passed pair of trees, a tree a green run already passed, and a nightly run that `nightly` leaves off run no test.

### The tests that failed

Each part runs `make test` with `REPO_STANDARD_FAILED=$RUNNER_TEMP/failed/failed.txt`, and each adapter's test command writes there the id of each test that failed, one a line, in the form `make select` prints.
A repo whose Makefile is not the skeleton's does the same, or its failed parts name no test.
A part that failed lists its ids in the job's summary, and every part uploads the folder as `failed-<run id>-<part>`, so a part run again replaces what it said; `passed` names the ids in its error line.
The job `browser` does the same with the target `e2e`: it writes the failed browser tests to `repo-standard-failed/failed.txt` in the checkout, each as `<spec> > <title>` read from Playwright's JSON report, and uploads the folder as `failed-<run id>-browser`.

On a push to the default branch a failed part runs its failed ids once more, `make test TESTS=<ids>`, and writes those that failed again to `again.txt`; a failed `browser` runs the target `e2e` once more on its failed ids.
`passed` then checks out the commit, runs `repo-standard misses record`, and uploads the ledger `miss-ledger-<run id>`, kept 90 days, one JSON row a failed test: its id, the merged pull request, whether `make select BASE=HEAD^1` selects it, and its class, `flaky`, `miss`, `race` or `env`, as [the standard's rule](standard.md#main-runs-the-whole-suite-after-each-merge) says.
The rows go to the job's summary too.

A pull request's `plan` reads the ledgers of main's runs of the last 30 days through `gh api`, with the run's token, and adds to the selection each id a row names that is not `flaky`, that no later green run of main passed and whose path is still in the tree.
A lookup that fails warns and adds nothing, so the check never waits on it.
`repo-standard misses --days 30` prints the miss rate and the rows for a person.

### The markers

`passed` leaves the markers later runs read, as artifacts of the run:

- `checked-tree-<base tree>-<merge tree>`, after a pull request's check passed, which a later run of the same two trees reuses.
- `green-tree-<tree>`, after the whole suite passed on the tree: on main, on a nightly run, and on a pull request whose selection was `all`.

A deploy entry refuses a tree with no `green-tree` marker through `repo-standard green`, as the standard's rule says, so the workflow keeps that marker 90 days, as long as GitHub keeps a run by default.
Where the marker has gone, `repo-standard green` reads the push run of `check.yml` on main for the commit.
`jmerge.green` reads a marker only from a run of `.github/workflows/check.yml`, so the caller keeps that name.

## Before the standard

A repo with no `.repo-standard.yml` runs its `command` alone, in one job, and the plan asks nothing else.
That is how /new-home's first pull request in a repo checks it: the repo adopts the standard later by adding the config, with no change to its caller.
