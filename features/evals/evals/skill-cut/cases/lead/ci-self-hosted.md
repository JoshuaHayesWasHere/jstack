# ci-self-hosted

## Intent

Task: "fix this, we should have already with the local runners created during the infra rework" (the user, 2026-10-15 13:43 ET, jbus word d6b0e3becf11). Every job in .github/workflows/ci.yml, check and api, gets runs-on: ${{ vars.RUNS_ON || 'Winnifred-ephemeral' }}, as the infra repo's host README says, and the check job passes on that runner.
Done when:
- every job in .github/workflows/ci.yml (`api` and `check`) has `runs-on: ${{ vars.RUNS_ON || 'Winnifred-ephemeral' }}`, and no `ubuntu-latest` is left in it
- the `check` job's GitHub check run is named `check`: drop or change its `name: make check` (jmerge requires a check named exactly `check`, src/jmerge/ready.py REQUIRED in the jstack repo). The api job's display name may stay
- on the pull request, both jobs were picked up by a Winnifred-ephemeral runner and passed on GitHub, at the final head
- the stock runner image has no `make` (non-root, no apt; the infra home, 2026-10-15), so the check job does not call `make`: the six commands of the Makefile's `check` target move into one script (for example `scripts/check.sh`, `set -eu`, same order, stopping at the first failure), which both `make check` and the CI job run, so the list lives in one place. `make check` keeps working locally. setup-go and setup-node work on the runner as they are; anything else the image lacks is handled in the workflow, not by changing infra
Proves it: GitHub's check runs on the pull request: `gh pr checks <n>` shows `check` and the api job passing, and their logs name a Winnifred-ephemeral runner
Size: S
Where: .github/workflows/ci.yml, Makefile (the check target), the new check script, and a doc line where PROJECT_SPEC.md or DEVELOPMENT.md describe CI, if they do
Do not touch: the infra repo (the runner, its conf, its image and the RUNS_ON variable are the infra home's), application code, deploy scripts
Decisions: 2026-10-15, the user: "Do not merge by hand: jbus merges."
Design: none, a two-line workflow change

Scope of this review. It overrides anything above that reads wider.
Review only the lines this pull request changes: its diff against its base branch.
Report a finding only when it is about a changed line, or about something a changed line breaks. Give every finding the file and line of the changed line, and when the damage is elsewhere, say where in the text.
For a finding about a removed line, give the line that now sits just before or just after where it was. For a finding about what the change as a whole lacks (a "Done when" line it does not meet, a test it does not have), give no file and say so.
End every finding with the principle it breaks, `(principle: <name>)`, a name from the principles listed above, or `(principle: none)` when it breaks none of them or none is listed.
Do not report and do not fix a bug or weakness in code this pull request did not change, however real: those are handled elsewhere.
Do not ask for work beyond what the task above needed.
Read the changed code the way a tech lead would, and answer these about it:
1. Does it meet the task and every "Done when" line above? Name each line it does not meet.
2. Is it tested properly? A test must execute something. A new or changed test that only matches wording and executes nothing is a warning, and the remedy to name is a test that executes (one that runs the shell, parses the block and checks it, or runs the script), not deleting the test.
3. Does it do what the user wanted, not only what the words of the task say?
4. Is it correct? Look for these too, in the changed lines:
   - Run twice, or after a run that crashed halfway: if what happens depends on the state left behind, a reconciliation step is missing.
   - Shared state: where several actors can touch the same files, branches or data, is access kept in step by structure (a lock, sequential phases, one owner), or only by a convention that will not hold?
   - A rule in prose: a comment or convention someone has to remember, where a type, a lint rule or a runtime check would make the wrong thing impossible.
   - An old path kept beside a new one: with no outside consumer, the callers move and the old path goes in the same change.
   - A proxy: a check that reads a file's age, a cached value or a self-report, and not the real value or the output itself.
   - A bug fix with no test for the bug.
5. Could it be done more simply or cheaply? Look for these too, in the changed lines:
   - Be ambitious about structural simplification. Do not stop at "this could be a bit cleaner." Look for reframings that make whole branches, helpers, modes, conditionals or layers disappear. Assume a "code judo" move is often available: one that uses the existing architecture more effectively and makes the change dramatically simpler. If you can delete complexity rather than rearrange it, push hard for that.
   - A file the change pushes from under 1,000 lines to over 1,000: should it be split first?
   - Ad-hoc conditionals, special cases or one-off branches put into an existing flow, where a helper or a module of its own would hold the logic.
   - A thin abstraction, identity wrapper or pass-through helper that adds indirection and no clarity.
   - Logic outside its canonical layer: feature logic in a shared path, or a one-off where an existing helper would do.
   When the remedy for one of these would change a file outside the "Where" line above, say so in the finding: it is noted for later, not asked for in this pull request.
6. Does it leave everything it did not mean to change unaffected? Look for these too, in the changed lines:
   - A changed line that does not trace to the task: adjacent code, comments or formatting "improved" in passing, or a refactor of something that was not broken. Every changed line should trace directly to the task above.
   - A removal the change did not earn: an import, variable or function that was already unused before this change is named in the finding, not deleted. What the change itself made unused goes in the same change, and one left behind is a finding too.
7. Does it change a file outside the "Where" line above? Each such file is a finding.

## Findings

### A1

### 1. [warning] The `runs-on` expression cannot keep a stranger's pull request off this machine
**Location**: `.github/workflows/check.yml:18-20` (same comment at `.github/workflows/pstack-drift.yml:44-46`)
**Finding**: The comment states "A public one never does: a stranger's pull request must not run here", but the expression only governs pull requests that leave the line alone.
**Evidence**: For a `pull_request` event GitHub evaluates the workflow file from the pull request's own merge commit.
Once the repo is public, a fork PR can rewrite line 20 to `runs-on: [self-hosted, attic]`.
The runner is still registered to the repo, and it runs as a systemd user service with access to the real home directory.
The only gate left is the fork-approval setting, which is not in this diff.
This is a rule in prose where the real control sits elsewhere.
**Suggestion**: Reword the comment to claim only what the line does (the repo's own jobs stop using the runner once public). Removing the runner's registration before going public is the real control; that is outside the "Where" line, so it is noted for later.

### A2

### 2. [warning] On the weekly schedule the expression may pick `ubuntu-latest`, and the test cannot see it
**Location**: `.github/workflows/pstack-drift.yml:46`
**Finding**: `pstack-drift` runs on `schedule` and `workflow_dispatch`. The expression reads `github.event.repository.private`, which exists only if the event payload carries a `repository` object.
**Evidence**: From memory, the `schedule` payload has often been just `{"schedule": "<cron>"}`; `github.event.repository.*` being empty on cron runs is a known gotcha. I could not confirm this here (no run, no network). If it is empty, the expression falls to `'ubuntu-latest'`, so the weekly job keeps using hosted minutes and the "picks its runner the same way" line is not met. The test at `tests/test_workflows.py:136-142` models `private` as a boolean and has no notion of the triggering event, so it passes either way. The PR's own `check` run only proves the `pull_request` path.
**Suggestion**: Trigger `pstack-drift` once by schedule (or inspect a past scheduled run's context) and read the runner name. If the payload lacks it, a single expression needs a source present on every event, for example a repository variable (`vars.*`).

### A3

### 3. [warning] The drift job leaves a clone in the real `~/.cache`, which breaks "leaves nothing behind"
**Location**: `.github/workflows/pstack-drift.yml:46` (damage is in `src/pdrift/cli.py:64-77`, unchanged)
**Finding**: Moving this job to the self-hosted runner makes `make pstack-drift` write its cache clone to `~/.cache/attic/cursor-plugins` in the user's real home.
That is outside the job's workspace and survives every run.
**Evidence**: `cache()` uses `XDG_CACHE_HOME` or `Path.home() / ".cache"`. `fetch()` reuses the clone whenever `.git` exists. `actions/checkout`'s clean only covers the workspace. A run killed mid-clone (the job has `timeout-minutes: 10`) leaves a partial `.git`, and every later run takes the reuse branch. The same directory is shared with the user's own local `make pstack-drift`.
**Suggestion**: Set `XDG_CACHE_HOME: ${{ runner.temp }}` (or a workspace path) as `env` on the job or step. This stays inside the "Where" files.

### A4

### 4. [warning] `uv`'s cache and tool install persist outside the workspace across jobs
**Location**: `.github/workflows/check.yml:20` and `.github/workflows/pstack-drift.yml:46` (effect is at the unchanged `astral-sh/setup-uv` and `uv sync --locked` steps)
**Finding**: The "Done when" line asks that `uv sync --locked` builds its environment inside the job's workspace. `.venv` does land there and is cleaned by checkout, but the uv cache does not.
**Evidence**: On a self-hosted runner `setup-uv` does not, as I recall, redirect the cache to a throwaway directory, so `uv sync` uses `~/.cache/uv`. That is the same cache the user's own `uv` uses, plus any uv-managed Python under `~/.local/share/uv`. A wheel built by one job is reused by the next. I did not confirm `setup-uv`'s self-hosted defaults at this pinned version.
**Suggestion**: Set `UV_CACHE_DIR: ${{ runner.temp }}/uv-cache` on the job, or state in the Result that the shared content-addressed cache is accepted.

### A5

### 5. [nit] The test only globs `*.yml` and crashes on a job with no `runs-on`
**Location**: `tests/test_workflows.py:154` and `tests/test_workflows.py:139`
**Finding**: `WORKFLOWS.glob("*.yml")` skips a workflow named `*.yaml`, so a bare hosted label there passes unseen. A job with no `runs-on` (a reusable-workflow `uses:` job) leaves `found[job] = None`, and `PICK.fullmatch(None)` raises `TypeError` instead of failing an assertion.
**Evidence**: GitHub loads both extensions. `jobs()` at line 130 seeds `None` and `runner()` passes it straight to `fullmatch`.
**Suggestion**: Glob `*.y*ml`, and return `[]` from `runner` for `None`.

### A6

### 6. [nit] The comment copied into `pstack-drift.yml` describes a trigger that workflow lacks
**Location**: `.github/workflows/pstack-drift.yml:44-45`
**Finding**: "a stranger's pull request must not run here" sits on a workflow triggered only by `schedule` and `workflow_dispatch`.
**Evidence**: Lines 5-8 of that file list the triggers; no pull request can start this job.
**Suggestion**: Say "same runner rule as check.yml", or drop the second sentence.

### A7

### 7. [nit] "Done when" line 3 cannot be confirmed from the diff
**Location**: no file; this is about what the change as a whole has to show
**Finding**: The passing `check` run on `the user-attic` with its URL belongs in the Result.
Nothing in the diff evidences it, and I ran nothing.
**Evidence**: That run would also only cover the `pull_request` event (see finding 2).

### B1

### 1. [warning] The weekly `pstack-drift` run probably still picks `ubuntu-latest`
**Location**: `.github/workflows/pstack-drift.yml:17`
**Finding**: The expression reads `github.event.repository.private`, but this workflow is triggered by `schedule`. As far as I recall, a cron-triggered run's `github.event` payload carries only `schedule`, with no `repository` object. I could not confirm this here (nothing run, no docs fetched).
**Evidence**: If `repository` is absent, `github.event.repository.private` is null, the `&&` short-circuits, and `|| 'ubuntu-latest'` wins. The Monday 13:00 UTC run then goes to a GitHub-hosted runner in the private repo, which is the minutes the task set out to stop spending. Nothing in this pull request exercises the path: its own run is `check` on `pull_request`, and the new test accepts the expression by its spelling. "Done when" line 2 is unproven for the trigger that matters, and likely unmet.
**Suggestion**: Dispatch `pstack-drift` by hand and read the runner name, then dump `toJSON(github.event)` in one scheduled run. If `repository` is absent there, the expression needs a source that exists on every trigger.

### B2

### 2. [warning] The "public repo never uses this runner" rule lives in a file a pull request can rewrite
**Location**: `.github/workflows/check.yml:18-20` (same comment and expression at `.github/workflows/pstack-drift.yml:15-17`)
**Finding**: The comment states "A public one never does: a stranger's pull request must not run here", but the only thing enforcing it is the `runs-on` expression in the workflow file itself.
**Evidence**: On `pull_request`, GitHub runs the workflow as it appears in the pull request's head.
Once the repo is public, a fork's pull request can replace line 20 with `runs-on: [self-hosted, attic]`.
The runner is still registered to the repo, so the job lands on this machine as the user's systemd user service.
The only remaining gate is the repo's fork-approval setting.
This is a rule in prose and convention where structure is needed.
**Suggestion**: The real guard is outside the "Where" line, so it is noted for later: remove the runner's registration before the repo's visibility changes. Within this pull request, reword the comment so it does not claim "never".

### B3

### 3. [warning] The test's `PICK`/`runner`/`runners` layer is an evaluator that evaluates nothing
**Location**: `tests/test_workflows.py:16-19`, `100-113`, `124-128`
**Finding**: `PICK.fullmatch` already pins the expression character for character, leaving only the two quoted payloads free. `runner()` then "evaluates" by returning one capture group or the other. That is a hand-written model of GitHub's `&&`/`||`, not GitHub's evaluator.
**Evidence**: The private/public split adds no checking power over comparing `jobs(text)` to the one expected string. It does add a regex, two helpers, a `json` import, and a second test (lines 124-128) whose only subject is the helper. It also gives the appearance of checking behaviour; finding 1 is exactly what the model cannot see, because it assumes `private` is always a boolean.
**Suggestion**: Keep `jobs()` and delete the layer: `assert jobs(path.read_text()) == {"check": RUNS_ON}` per file, with `RUNS_ON` the literal expression. The bare-label case then needs only `jobs(text) != {"check": RUNS_ON}`.

### B4

### 4. [nit] The glob misses `.yaml` workflows
**Location**: `tests/test_workflows.py:118`
**Finding**: `WORKFLOWS.glob("*.yml")` skips `*.yaml`, which GitHub also loads.
**Evidence**: A later `.github/workflows/foo.yaml` with `runs-on: ubuntu-latest` passes this test, which the fifth "Done when" line says must fail. The exact-dict equality catches any new `.yml` file but not this one.
**Suggestion**: Glob `*.y*ml`, or iterate the directory and assert on suffixes.

### B5

### 5. [nit] The comment copied into `pstack-drift.yml` describes a trigger it does not have
**Location**: `.github/workflows/pstack-drift.yml:15-16`
**Finding**: "a stranger's pull request must not run here" sits on a workflow triggered only by `schedule` and `workflow_dispatch`.
**Evidence**: No pull request can start this job, so the stated reason is false for this file and is duplicated text that will drift.

### B6

### 6. [nit] Two "Done when" lines have no evidence in the diff (no file: about what the change lacks)
**Finding**: Line 3 (the `check` run passes and its log shows `the user-attic`, with the run's URL) and line 4 (a job leaves nothing behind) are not shown by any changed line.
**Evidence**: Line 4 holds only through defaults the diff does not state or test: `actions/checkout`'s clean, and `uv sync` placing `.venv` in the workspace unless the runner's unit sets `UV_PROJECT_ENVIRONMENT`. The uv cache and any uv-managed Python live in the service user's home and persist across jobs. Line 3 can only be confirmed from the run itself, which I did not open.
