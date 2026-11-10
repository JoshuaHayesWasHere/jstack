# The check CI runs

On every pull request the check workflow's job `reuse` runs `scripts/select_tests.py --pull-request --parts 8 HEAD^1 HEAD` once, where an import reaches only the tests near the change, the job `lint` beside it runs the prose lint and `make lint`, and eight parts, `check 1 of 8` to `check 8 of 8`, each run `make test` on the test files it dealt them. On main it runs `make check`. Neither runs the tests marked `browser`, which `.github/workflows/browser.yml` runs as `make check-browser` nightly and on a release. `scripts/green_tree.py` skips the suite for a tree that already passed, and `scripts/select_tests.py` turns a diff into the test files it needs, from the imports of the tree and this map, and writes what it chose to the job summary.

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

- When GitHub's hourly allowance for the run's token is spent, the API answers 403 or 429, and a run still ends green on its own merits. The lookup of the tests that failed on main cannot read main's runs, so it prints `all` and a warning, and `reuse` selects the whole suite (`forced-by=failed-on-main`). The AI co-author trailer check reads the pull request's commits with the checkout's git from `origin`, which spends none of that allowance, says so in one line, and fails only on a real trailer. A run that cannot reach GitHub at all, with no answer, still fails the trailer check: an unread range is not a clean one.
