# The check CI runs

On every pull request the check workflow's job `select` runs `scripts/select_tests.py --parts 8 HEAD^1 HEAD`, the prose lint and `make lint` once, and eight parts, `check 1 of 8` to `check 8 of 8`, each run `make test` on the test files it dealt them. On main it runs `make check`. Neither runs the tests marked `browser`, which `.github/workflows/browser.yml` runs as `make check-browser` nightly and on a release. `scripts/green_tree.py` skips the suite for a tree that already passed, and `scripts/select_tests.py` turns a diff into the test files it needs, from the imports of the tree and this map, and writes what it chose to the job summary.

Paths:
- `scripts/`
Tests: none

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
