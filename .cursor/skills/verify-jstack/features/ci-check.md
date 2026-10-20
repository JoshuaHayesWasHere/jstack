# The check CI runs

The check workflow runs `make check-fast` on every pull request and `make check` on main, neither with the tests marked `browser`, which `.github/workflows/browser.yml` runs as `make check-browser` nightly and on a release. `scripts/green_tree.py` skips the suite for a tree that already passed, and `scripts/select_tests.py` turns a diff into the test files it needs, from the imports of the tree and this map, and writes what it chose to the job summary.

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
