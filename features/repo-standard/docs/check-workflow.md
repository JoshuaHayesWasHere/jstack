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
    runs-on: ubuntu-24.04
```

The caller also sets the triggers, the permissions and the concurrency, since a called workflow cannot.
It runs on each pull request, on each push to `main`, on a nightly schedule and by hand, and it grants `contents: read` and `actions: read`, which the marker lookups need.

The `uses:` line's tag and the `standard:` line of `.repo-standard.yml` name the same version, and a version bump moves both.
The plan fails when the config pins another version than the workflow's own.

| Input | What it sets | Default |
|---|---|---|
| `runner` | The label of the runner every job runs on, such as one on the repo's own machines | `ubuntu-24.04` |
| `command` | The repo's check command, which runs alone while the repo has no `.repo-standard.yml` | none |
| `timeout-minutes` | The cap of each part of the tests, and of the check command | 30 |

The label of a runner on the repo's own machines goes in `runner`, and in the caller's job `check` as its `runs-on`.

A step that the make targets need first, such as a toolchain the runner lacks or a cache of dependencies, goes in a composite action at `.github/actions/setup/action.yml` in the repo.
Each job that runs a make target runs that action after its checkout, where the file exists.

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
It reads the version `.repo-standard.yml` pins and clones jstack at the tag `repo-standard-vN`, which holds the code the workflow runs in the runner's `python3` before any setup.

| Job | On a pull request | On a push to main, a nightly run, a manual run |
|---|---|---|
| `plan` | Asks `jmerge.reuse` whether a passed check of the same two trees is reused, and runs `make select BASE=HEAD^1` | Asks `scripts/green_tree.py` whether a green run left a marker for the tree, except on a nightly run |
| `lint` | `make lint BASE=HEAD^1`, then `repo-standard conform` | The same |
| `test` | Each part runs what `plan` dealt it: `make test TESTS=<ids>`, the whole suite, or nothing | Each part runs the whole suite |
| `passed` | Passes when `plan`, `lint` and every part passed, or the pair of trees was reused | Passes when every job passed, or the tree's marker skipped the tests |

`repo-standard plan` deals a selection out to the parts in turn, and starts no more parts than the selection has ids.
A part dealt the whole suite runs `make test` with one part, and `make test SHARD=<part>/<parts>` with more, so a repo that sets `shards` above 1 gives its `test` target a `SHARD` variable.
An id `make select` prints holds no space, since the part passes its ids to `TESTS` with a space between each.

A reuse of a passed pair of trees, a tree a green run already passed, and a nightly run that `nightly` leaves off run no test.

### The markers

`passed` leaves the markers later runs read, as artifacts of the run:

- `checked-tree-<base tree>-<merge tree>`, after a pull request's check passed, which a later run of the same two trees reuses.
- `green-tree-<tree>`, after the whole suite passed on the tree: on main, on a nightly run, and on a pull request whose selection was `all`.

A deploy entry refuses a tree with no `green-tree` marker, as the standard's rule says.
`jmerge.green` reads a marker only from a run of `.github/workflows/check.yml`, so the caller keeps that name.

## Before the standard

A repo with no `.repo-standard.yml` runs its `command` alone, in one job, and the plan asks nothing else.
That is how /new-home's first pull request in a repo checks it: the repo adopts the standard later by adding the config, with no change to its caller.
