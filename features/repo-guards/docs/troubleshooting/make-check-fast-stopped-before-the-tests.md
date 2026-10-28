# `make check-fast` stopped before the tests

`make check-fast BASE=<rev>` runs the lint and the tests `scripts/select_tests.py` names for the diff from `<rev>` to `HEAD`, or `make check` where the script prints `all`.
A pull request's CI runs it with `BASE=HEAD^1`.
A desk takes `origin/main` by default.
Neither the script's list nor `make check` has the tests marked `browser`: those open a real browser.
`make check-browser` runs them: nightly, on a release tag, by hand, and on a pull request that changes the view, its tests or the workflow (`.github/workflows/browser.yml`).

| Line | Meaning | Do this |
|---|---|---|
| `select_tests.py: git diff failed: fatal: ambiguous argument '<rev>': unknown revision or path not in the working tree.` | `<rev>` is no commit of this checkout. No lint and no test ran. | Run `git fetch origin`, or name the commit: `make check-fast BASE=$(git merge-base origin/main HEAD)`. |
| `select_tests.py: nothing can be read (<error>), so all` | The script could not load jmerge's reading of a pattern from `features/jmerge/src/`, or a module does not parse, so it runs the whole suite. | Read the error: an import that `features/jmerge/src/jmerge` added needs no package beyond the standard library, `src/` and each `features/*/src/`, and a module must parse. |

The selection of each run is in its job summary, on one line: `check-fast selection=<all|some> files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n> forced-by=<path or ->`. The four counts are the files each cause selected on its own, so they overlap, and `forced-by` names the path that made it `all`.
