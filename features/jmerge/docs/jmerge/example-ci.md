# An example CI: jstack's own

`jmerge` reads two things a repo's CI can give it: a green marker of a tree whose whole suite passed, and a `scripts/select_tests.py` that says which tests a change needs ([Fresh against main](../jmerge.md#fresh-against-main)).
Your repo needs neither, and `jmerge` merges without them.
This page shows how jstack's own CI, `.github/workflows/check.yml`, gives both, as an example to copy from.

## The jobs

Both jobs run on GitHub's hosted runner, `ubuntu-24.04`, and never on the machine that runs `jmerge`.
A pull request's job, `check`, runs `make check-fast BASE=HEAD^1`, the lint and the tests its change reaches.
Where that selection is 80% of the test files or more, or the change touches something every test rests on, it runs the whole suite.
A pass of the whole suite uploads the artifact `green-tree-<tree>` for the tree it checked out, GitHub's merge of the head over main.
A marker says the whole suite passed a tree, so a run of only some tests leaves none.
The job summary says `full suite: yes` or `no` and `tree <tree>`, and the same goes to `ci.jsonl` as the job's `full` and `tree` (`jbus ci --notice`).

The job `full` runs on each push to main or to an integration branch, and when the workflow is started by hand.
It first runs `scripts/green_tree.py`, which looks for a marker of the tree it checked out: the ref `refs/jstack/green-tree/<tree>` that `jmerge` pushes after a fresh check passes, or a `green-tree-<tree>` artifact of a successful run of the workflow.
With a marker it skips `make check`, and without one it runs the whole suite and uploads the marker when it passes.
Where main did not move before the merge, main's tree is the one the pull request's run checked out, so the tree is tested once.
A test the selection missed fails the `full` job on main after the merge.

## The test selection

The check runs every test, and a change needs fewer: `python3 scripts/select_tests.py <base> <head>` prints the test files a diff needs, one per line, or `all`.
It reads `git diff --name-only --no-renames <base> <head>`, where `<base>` is where the pull request left main or the parent of its merge commit, and the imports of the tree: a changed module selects the tests that import it, through any chain of modules, and a changed file that is no module selects the tests that spell its path.
The pages in `testing/verify/` and each `features/<name>/verify.md` adds to it: each feature file names the paths it owns (`Paths:`) and the tests that read them in a way no import shows (`Tests:`), and the map's README names the test files that read the whole tree (`Cross-cutting:`), which every diff runs.
An edit to a feature file selects that feature's tests, not `all`.
Only `pyproject.toml`, `uv.lock`, the root `conftest.py`, a plugin of `testing/` it names, a test module a plugin loads for every test, and a fixture no test names select `all`.
It needs no package, so it runs before `uv sync`, and the same two commits give the same lines.
When `$GITHUB_STEP_SUMMARY` is set it adds one line to it, `check-fast selection=<all|some> files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n> forced-by=<path or ->`: a collector reads the choice of every run from that line.
A test module that marks itself `browser` is never printed: `make check-browser` runs it nightly and on a release.
A test the selection missed fails the `full` job on main after the merge.
`testing/tests/test_select_tests.py` fails when a path is owned by no feature, or a test file is selected by no change.
