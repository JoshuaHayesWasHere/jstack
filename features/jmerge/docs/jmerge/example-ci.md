# An example CI: jstack's own

A repo's CI can give `jmerge` two things, which [Fresh against main](../jmerge.md#fresh-against-main) uses:

- a green marker of a tree whose whole suite passed
- a `scripts/select_tests.py` that says which tests a change needs

Your repo needs neither, and `jmerge` merges without them.
This page shows how jstack's own CI, `.github/workflows/check.yml`, gives both, as an example to copy from.

## The jobs

Both jobs run on GitHub's hosted runner, `ubuntu-24.04`, and never on the machine that runs `jmerge`.
A pull request's job, `check`, runs `make check-fast BASE=HEAD^1`, which runs the lint and the tests that its change selects.
It runs the whole suite instead when that selection is 80% of the test files or more, or when the change touches a file every test depends on.
When the whole suite passes, the job uploads the artifact `green-tree-<tree>` for the tree it checked out, which is GitHub's merge of the head over main.
A marker means the whole suite passed on that tree, so a run of only some tests uploads no marker.
The job summary says `full suite: yes` or `no` and `tree <tree>`, and `jbus ci --notice` writes the same to `ci.jsonl` as the job's `full` and `tree`.

The job `full` runs on each push to main or to an integration branch, and when someone starts the workflow by hand.
It first runs `scripts/green_tree.py`, which looks for a marker of the tree it checked out.
The marker is either the ref `refs/jstack/green-tree/full/<tree>` that `jmerge` pushes after a fresh check of the whole suite passes, or a `green-tree-<tree>` artifact of a successful run of the workflow.
With a marker, the job skips `make check`.
The ref `refs/jstack/green-tree/selected/<tree>`, left by a fresh check of selected tests, is no such marker, and the job runs the suite.
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
`make check-browser` runs such a module nightly and on a release.
A test the selection missed fails the `full` job on main after the merge.
`testing/tests/test_select_tests.py` fails when no feature owns a path, or when no change selects a test file.
