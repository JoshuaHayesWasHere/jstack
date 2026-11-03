# An example CI: jstack's own

A repo's CI can keep a green marker of a tree whose whole suite passed, so that main's run after a merge skips a suite that already passed on the same tree.
`jmerge` does not read the marker.
Its own `scripts/select_tests.py`, which says which tests a change needs, keeps a pull request's check short.

Your repo needs neither, and `jmerge` merges without them.
This page shows how jstack's own CI, `.github/workflows/check.yml`, gives both, as an example to copy from.

## The jobs

Every job runs on GitHub's hosted runner, `ubuntu-24.04`, and never on the machine that runs `jmerge`.
A pull request's run starts with the job `reuse`, which runs `python3 -m jmerge.reuse`.
It looks for a passed run that checked the same two trees: GitHub's merge of the head over its base, and that base.
When it finds one, no test job runs, and the job `check` passes on the run it reuses.
`reuse` also lists the tests that failed on main in the last 30 days (`scripts/select_tests.py --failed-on-main 30`), and every test job adds them to what it selects.
A lookup that fails adds no test, and the job `check` warns of it.
The same job fails a pull request whose title, body or commits credit an AI tool as a co-author (`scripts/no_ai_trailers.py`).

Without a reuse, the check runs as eight jobs side by side, `check 1 of 8` to `check 8 of 8`.
Each one runs `make check-fast BASE=HEAD^1 SHARD=<n>/8`, which runs the lint and an eighth of the tests that its change selects, split by each test's time (`testing/shard.py`).
The job `check` passes only when all eight passed.
It runs the whole suite instead only when the change touches a file every test depends on, however many test files the selection holds.
When the whole suite passes, the job `check` uploads the artifact `green-tree-<tree>` for the tree it checked out, which is GitHub's merge of the head over main.
A marker means the whole suite passed on that tree, so a run of only some tests uploads no marker.
The job summary says `full suite: yes` or `no` and `tree <tree>`, and `jbus ci --notice` writes the same to `ci.jsonl` as the job's `full` and `tree`.

The full suite runs on each push to main, and when someone starts the workflow by hand.
It runs as four jobs side by side, `full 1 of 4` to `full 4 of 4`, and the job `full` passes only when all four passed.
Each of the four first runs `scripts/green_tree.py`, which looks for a marker of the tree it checked out.
The marker is a `green-tree-<tree>` artifact of a successful run of the workflow.
With a marker, it skips `make check`.
Without one, it runs the whole suite and uploads the marker when the suite passes.
If main did not move before the merge, main's tree is the tree the pull request's run checked out, so the suite runs on that tree only once.
A test the selection missed fails the `full` job on main after the merge.

## The test selection

`make check` runs every test, but a change needs fewer.
`python3 scripts/select_tests.py <base> <head>` prints the test files a diff needs, one per line, or `all`.
It reads `git diff --name-only --no-renames <base> <head>`, where `<base>` is where the pull request left main or the parent of its merge commit.
It also reads the imports of the tree.
A changed module selects the tests that import it, through any chain of modules.
A changed file that is not a module selects the tests whose text contains its path.
The pages in `testing/verify/` and each `features/<name>/verify.md` add to the selection.
Each feature file names the paths it owns (`Paths:`) and the tests that read them in a way no import shows (`Tests:`).
The map, `features/verify-jstack/project-skill/map.md`, names the test files that read the whole tree (`Cross-cutting:`), and the selection includes them for every diff.
An edit to a feature file selects that feature's tests, not `all`.
Only these changes select `all`: `pyproject.toml`, `uv.lock`, the root `conftest.py`, a plugin of `testing/` that the root `conftest.py` names, a test module that a plugin loads for every test, and a fixture that no test names.
The script needs no package, so it runs before `uv sync`, and the same two commits always give the same output.
When `$GITHUB_STEP_SUMMARY` is set it adds one line to it, `check-fast selection=<all|some> files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n> forced-by=<path or ->`.
A collector reads the choice of every run from that line.
The script never prints a test module that marks itself `browser`.
`browser.yml` runs such a module with `make check-browser` nightly, on a release, by hand, and on a pull request into main that changes the view.
A test the selection missed fails the `full` job on main after the merge.
`testing/tests/test_select_tests.py` fails when no feature owns a path, or when no change selects a test file.
