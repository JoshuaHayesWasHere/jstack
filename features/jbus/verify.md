# jbus

`jbus poll` is one pass over every project.
It reads the queue, the briefs, T3 Code and GitHub, launches what is approved and has room, tells each thread what it must act on, runs `jmerge`, and writes what it saw to the state directory.
Every other `jbus` verb reads or writes that state, and `jbus view` is a local web page over it.
This page has six journeys: a queue row from add to launch, a scout's request from add to launch, a decision that wakes the home thread, a red main that files the brief for its fix, a check that ends merges within seconds, and a merged row whose revert opens it again for its redo.
The pass as a whole and the view have no recipe yet.
Their tests are the ones that import the `jbus` package, which `scripts/select_tests.py` follows through the imports.
A headless browser drives the view's page with axe (`features/jbus/tests/fixtures/jbus-view/axe-run.js`).

Paths:
- `features/jbus/src/jbus/`
- `features/jbus/docs/`
- `features/jbus/units/`
- `features/jbriefs/src/jbriefs/`
- `features/jgauge/src/jgauge/`
- `features/jmerge/src/jmerge/`
- `features/jmerge/docs/jmerge.md`
- `features/jpack/src/jpack/`
- `features/jroles/src/jroles/`
- `features/jsettings/`
- `features/home/docs/state.md`
- `features/jinstall/docs/configuration.md`
Tests: none

`features/jbus/tests/test_main_red_model.py` checks main's red record over every order of events.
The record is `main.json` as `mainmoved.tell` writes it and `mainjson.read` reads it.
`scripts/select_tests.py` selects the test by its imports.
`features/jbus/project-skill/verify-main-red/SKILL.md`, which the install links as the checkout's `.claude/skills/verify-main-red` and `.cursor/skills/verify-main-red`, says how to run it and read what it finds.

## Sub-features

A queue row, from add to launch (`queue-row`):

- `queue-add` adds a row with its brief from stdin, unapproved and `queued`.
- `queue-approve` records who approved, when, and for which brief (the first 12 characters of its sha256).
- `queue-hold` takes the approval back, and jbus does not launch an unapproved row.
- `queue-launch` launches one crew thread for an approved row on the next pass.
- `queue-thread-line` writes `Thread: <id>` into the brief the crewmate reads.
- `queue-derived` refuses a command that tries to write a derived column.

A scout's request, from add to launch (`scout-path`):

- `scout-add` stores a request in the template's shape in the home's `scouts/`, and refuses one with a crewmate's line, naming the line.
- `scout-approve` records the user's go for the request's sha, on a word that `jbus word` kept.
- `scout-launch` launches one `scout: <slug>` thread on the next pass, with `existing_worktree` into `$T3CODE_HOME/worktrees/<checkout>/scout+<slug>`, a worktree jbus made detached, with no branch, that holds `.claude/settings.json` and `.claude/.gitignore`, and removes it once its Report says done and no scout thread is at work.
- `scout-show` prints each request's state, its thread and what its last Report says.

A decision wakes the home thread (`home-wake`):

- `decide-queue` raises a decision with `jbus decide` and prints `raised:`.
- `decide-once` prints `raised already:` for the same decision raised twice.
- `wake-send` tells the home thread the decision through T3 Code on the next pass, one `wakes` message.
- `wake-once` sends nothing on a pass that finds nothing new for the home.
- `status` prints the status file: the last pass and the failed wakes.

A red main files the brief for its fix (`main-red`):

- `red-retro` reports main's failed check once, naming the merged slug and the merges since the last green.
- `red-brief` writes `tasks/main-red-<sha12>.md` with the failed job's URL, the failed test ids its log names, the merges since the last green with the files they changed, and `Playbook: bug-fix` and `Size: S`.
- `red-row` queues the brief unapproved, so `jbus queue show` lists the row with `approved` empty.
- `red-once` files nothing more for the same commit on a later pass, and leaves an edited brief as it is.

A merged row's revert opens it again for its redo (`revert-reland`):

- `revert-open` has a pass over a red main whose one culprit is a row's merge open its revert, `gh pr revert`, and print `revert <slug>: main red at <sha12>, jbus opened <address> to revert it`.
- `reland` has the pass after the revert merged take the row from `merged` to `left`, with an empty `pr` column and a `reland` event, and a line of `transitions.jsonl` marked `reverted`.
- `reland-review` has jbus launch the redo's reviewer, `review: <slug>, 1`, once the crew's desk proof holds at its pushed head, with no hand launch.
- `reland-merge` has `jmerge --check` say `ready` of the redo's pull request, with no wait line that asks for an accept, and the next pass's `jmerge` ask `gh pr merge` of it.

A check that ends merges within seconds, apart from the pass (`merge-tick`):

- `tick-pending` has the pass keep the open pull requests whose checks are still going, in `checks-pending.json`.
- `tick-304` has each tick ask GitHub for the completed runs with the ETag it kept, and run no `jmerge` while GitHub answers 304.
- `tick-merge` runs `jmerge --if-free` on the first tick after a run ends, and its merge follows within a tick.

## How to get to it (user POV)

- Run `jbus queue add <slug> --priority <n>` with the brief on stdin.
- Run `jbus word --to <project> --message <thread id>/<message id>` to keep the user's word, then `jbus queue approve <slug> --word <id>`.
- Run `jbus queue hold <slug>`.
- Run `jbus queue show` to read the table.
- Run `jbus poll` for one pass.
  On the live machine, the systemd timer runs it.
- Run `jbus queue add <slug> --priority <n>` with a scout's request on stdin, `jbus queue approve <slug> --word <id>`, and `jbus queue show`.
- Run `jbus gate <slug>` with the gate's lines on stdin, from the project's repo.
- Run `jbus done <slug>` with the result's lines on stdin.
- Run `jbus poll` for one pass.
- Run `jbus status`.
- Read the wake in the project's home thread.
  A sandbox has no real thread.
- After a merge whose commit on main has a failed check run, run `jbus poll`.
  On the live machine, the systemd timer runs it.
- Run `jbus queue show` to see the row, and read the brief in the home's `tasks/`.
- After a revert jbus opened of a row's merge merges, run `jbus poll`, then `jmerge --check` from the repo once the redo's pull request is open.
- Run `jbus tick` between passes.
  On the live machine, `jbus-merge.timer` runs it every 10 seconds while the last pass saw a row's pull request open or another pull request's checks going, and 10 seconds after the pass starts it; the pass stops it while it saw neither.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`, `machine/proc`, `machine/limits`, `gh/commits.json`, `gh/checks.json`, `gh/logs`, `home`

Each journey below starts in a new sandbox of its own, and its `record` name keeps the evidence apart.

### A queue row, from add to launch

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it, and `jbus queue show` has no rows.

- **Add the row.**
  Pipe a brief in.
  Run `printf '# alpha: a demo task\nTask: alpha, a demo task\nWhy: the journey needs a row to carry from add to launch\nDone when:\n- the demo works\nProves it: the demo test\nSize: S\nWhere: `src/alpha/`\nDesign: none, a demo\nReview: none\nPlaybook: feature\nSkills: tdd\nPull request: none\nHome: uncategorized\n' | record queue-row jbus queue add alpha --priority 1`.
  The table has one row, `alpha`, priority 1, status `queued`, with `approved` and `brief_sha` empty.
- **Try a derived column.** Run `record queue-row jbus queue add gamma --priority 2 --status launched`. It prints `refused: status is derived from T3 Code and GitHub, and no command writes it` and exits 2. No `gamma` row is added.
- **Keep a word, and approve it.**
  Give the user's message to the stand-in with `printf '{"mcp:sandbox-chat": [{"itemId": "turn-item:message:m1", "messageId": "m1", "text": "go", "type": "user_message", "createdBy": "user", "updatedAt": "%s"}]}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$VERIFY_JSTACK_SANDBOX/t3/messages.json"`.
  Run `record queue-row jbus word --to demo --message mcp:sandbox-chat/m1`, which ends with the word's id.
  Then run `record queue-row jbus queue approve alpha --word <the id>`.
  The row's `approved` reads `your word, ...` and its `brief_sha` is the sha256 of `$JBUS_STATE_DIR/demo/briefs/alpha.md` less its `Home:` line.
- **Hold it, and pass.** Run `record queue-row jbus queue hold alpha`, then `record queue-row jbus poll`. The row's `approved` is empty again, the pass prints no `launched` line, and `$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl` has no `t3_thread_launch`.
- **Approve again, and pass.** Run the approve command again, then `record queue-row jbus poll`. It prints `launched alpha: mcp:sandbox-thread-1`.
- **Read the table.** Run `record queue-row jbus queue show`. The row's `status` is `launched` and its `thread` is `mcp:sandbox-thread-1`.
- **Check the launch itself.** Run `record queue-row jq -c 'select(.tool == "t3_thread_launch") | .arguments | {title, workspaceStrategy}' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`. There is one line, titled `crew: alpha`, with a worktree on the branch `alpha` from `main`.
- **Check the brief.** Run `record queue-row cat "$HOME/.local/state/home/demo/tasks/alpha.md"`. It is the brief that was piped in, with the line `Thread: mcp:sandbox-thread-1` added.
- **Pass again.**
  Run `record queue-row jbus poll`.
  Nothing more launches, and `t3/calls.jsonl` still has one `t3_thread_launch`.
- **Proof.** Copy `t3/calls.jsonl`, `gh/calls.log`, the brief and `$JBUS_STATE_DIR/demo/queue.json` into `$VERIFY_JSTACK_EVIDENCE`, as the skill's Evidence section shows.

### A scout's request, from add to launch

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it.

- **Write the request.**
  Write a request in the shape of `features/scout/templates/scout-request.md` to `$VERIFY_JSTACK_SANDBOX/alpha.md`, with these lines: a first line `# alpha: <what to find out>`, a `Request:` line, a `Why:` line that says why the answer is wanted, a `Questions:` list, a `Deliver:` list, `Playbook: none`, `Out of bounds: read-only. <what it must not do>` and `Home: uncategorized`.
- **Add it.**
  Run `record scout-path jbus --project demo queue add alpha --priority 1 < "$VERIFY_JSTACK_SANDBOX/alpha.md"`.
  The table has one row, `alpha`, with `scout` in its `role` column and `approved` empty, and the request is in `$JBUS_STATE_DIR/demo/briefs/alpha.md`.
- **Try a crewmate's line.**
  Pipe in a request with a `Size:` line, as `{ cat "$VERIFY_JSTACK_SANDBOX/alpha.md" | sed 's/^# alpha:/# beta:/'; echo 'Size: S'; } | record scout-path jbus --project demo queue add beta --priority 1`.
  It exits 1 and names `a Size: line, which only a crewmate's brief has`, and no `beta` row is added.
- **Keep a word, and approve.**
  Give the user's message to the stand-in with `printf '{"mcp:sandbox-chat": [{"itemId": "turn-item:message:m1", "messageId": "m1", "text": "go", "type": "user_message", "createdBy": "user", "updatedAt": "%s"}]}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$VERIFY_JSTACK_SANDBOX/t3/messages.json"`.
  Run `record scout-path jbus word --to demo --message mcp:sandbox-chat/m1`, which ends with the word's id, then `record scout-path jbus --project demo queue approve alpha --word <the id>`.
  The row's `approved` reads `your word, ...`.
- **Pass.**
  Run `record scout-path jbus poll`.
  It prints `launched scout alpha: mcp:sandbox-thread-1`.
- **Check the launch itself.**
  Run `record scout-path jq -c 'select(.tool == "t3_thread_launch") | .arguments' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`.
  There is one line, titled `scout: alpha`, with the message `/scout alpha` and the workspace `{"type": "existing_worktree", "worktreePath": "<the worktree>"}`, and `t3/threads.json` gives its thread the branch `null`.
  The worktree is `$T3CODE_HOME/worktrees/demo/scout+alpha`, which jbus made: the sandbox leaves `T3CODE_HOME` unset, so it is `$HOME/.t3/worktrees/demo/scout+alpha`.
  Run `record scout-path git -C "$HOME/.t3/worktrees/demo/scout+alpha" status -sb` and `record scout-path ls -A "$HOME/.t3/worktrees/demo/scout+alpha/.claude"`.
  The worktree is detached, `## HEAD (no branch)`, with nothing to commit, and its `.claude` holds `settings.json` and `.gitignore`.
  The request is in `$HOME/.local/state/home/demo/scouts/alpha.md`, with the line `Thread: mcp:sandbox-thread-1` added.
- **Check the repo.**
  Run `record scout-path git -C "$VERIFY_JSTACK_SANDBOX/demo" for-each-ref --format='%(refname)'`.
  It lists `main` and the origin's refs, and no other branch.
- **Pass again, and read the table.**
  Run `record scout-path jbus poll`, then `record scout-path jbus --project demo queue show`.
  Nothing more launches, and the row is `running`, with `thread` `mcp:sandbox-thread-1`.
- **Write a Report.**
  Append `## Report` with `Status: done` to `scouts/alpha.md`, run `record scout-path jbus poll`, then `record scout-path jbus --project demo queue show --all`.
  The row's `status` is `done`.
- **Settle the scout, and pass.**
  Run `jq 'map(.settled = true)' "$VERIFY_JSTACK_SANDBOX/t3/threads.json" > "$VERIFY_JSTACK_SANDBOX/t3/t" && mv "$VERIFY_JSTACK_SANDBOX/t3/t" "$VERIFY_JSTACK_SANDBOX/t3/threads.json"`, then `record scout-path jbus poll`.
  It prints `removed scout alpha's worktree`, and `record scout-path git -C "$VERIFY_JSTACK_SANDBOX/demo" worktree list` lists the main checkout only.
- **Proof.**
  Copy `t3/calls.jsonl`, `t3/threads.json`, the request and `$JBUS_STATE_DIR/demo/queue.json` into `$VERIFY_JSTACK_EVIDENCE`.

### A decision wakes the home thread

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it: `$JBUS_STATE_DIR/status.json` does not exist.

- **Status before a pass.**
  Run `record home-wake jbus status`.
  It prints `refused: no status at <path>: no pass has run` and exits 1.
- **Raise a decision.**
  Run `record home-wake jbus decide alpha --question 'may the demo task skip its tests?' --reply 'reply in your own words to keep the tests or say what to do instead'`.
  It prints `raised: alpha: may the demo task skip its tests?`.
- **Raise it again.**
  Run the same command.
  It prints `raised already: alpha: may the demo task skip its tests?`.
- **Pass.**
  Run `record home-wake jbus poll`.
  It prints `wakes demo: told mcp:sandbox-home of decision alpha: may the demo task skip its tests?. Reply: reply in your own words to keep the tests or say what to do instead`.
- **Check the send.**
  Run `record home-wake jq -c 'select(.tool == "t3_thread_send") | .arguments | {threadId, mode, clientRequestId}' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`.
  There is one line, to `mcp:sandbox-home`, in `queue` mode, with a `clientRequestId` that begins `wakes|demo|`, and `t3/wake.jsonl` has the decision's line.
- **Ask whether wakes go.**
  Run `record home-wake jbus wakes`.
  It prints `wakes go: the home thread of demo is not failing`.
- **Pass with nothing new.**
  Run `record home-wake jbus poll`.
  It prints no `wakes` line, and `t3/calls.jsonl` still has one `t3_thread_send`.
- **Raise another, and pass.**
  Run `record home-wake jbus decide beta --question 'may beta wait a day?' --reply 'reply in your own words to let beta wait or say what to do instead'`, then `record home-wake jbus poll`.
  It prints `wakes demo: told mcp:sandbox-home of decision beta: may beta wait a day?. Reply: reply in your own words to let beta wait or say what to do instead`, and the new line of `t3/wake.jsonl` names beta alone.
- **Read the status.**
  Run `record home-wake jbus status`.
  `projects.demo.failed_wakes` is 0, and `last_pass` is this minute.
- **Proof.**
  Copy `t3/calls.jsonl` and `$JBUS_STATE_DIR/status.json` into `$VERIFY_JSTACK_EVIDENCE`.

### A red main files the brief for its fix

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it.

- **First pass.**
  Run `record main-red jbus poll`.
  It records the state it finds and files nothing, since a project's first pass files no finding about the past.
- **Merge alpha onto a red main.**
  Write the files that the stand-ins read: a brief for `alpha`, a merge of it at a red commit over a green one, a failed `full` job at the red commit, and that job's log.

  ```sh
  red=dddddddddddddddddddddddddddddddddddddddd green=ffffffffffffffffffffffffffffffffffffffff
  printf '# alpha: a demo task\nWhere: `src/alpha/`\n' > "$HOME/.local/state/home/demo/tasks/alpha.md"
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ) before=$(perl -MPOSIX -e 'print strftime("%Y-%m-%dT%H:%M:%SZ", gmtime(time - 7200))')
  jq -n --arg red "$red" --arg now "$now" '[{number: 7, url: "https://example.test/pull/7", title: "feat: alpha", headRefName: "alpha", mergeCommit: {oid: $red}, mergedAt: $now}]' > "$VERIFY_JSTACK_SANDBOX/gh/merged.json"
  jq -n --arg red "$red" --arg green "$green" --arg now "$now" --arg before "$before" '[{sha: $red, commit: {message: "feat: alpha (#7)", committer: {date: $now}}}, {sha: $green, commit: {message: "feat: older (#6)", committer: {date: $before}}}]' > "$VERIFY_JSTACK_SANDBOX/gh/commits.json"
  jq -n --arg red "$red" --arg green "$green" '{($red): [{name: "check", status: "completed", conclusion: "success", id: 900}, {name: "full", status: "completed", conclusion: "failure", id: 901, html_url: "https://example.test/o/r/actions/runs/77/job/901"}], ($green): [{name: "full", status: "completed", conclusion: "success", id: 800}]}' > "$VERIFY_JSTACK_SANDBOX/gh/checks.json"
  printf '2026-10-16T15:01:02Z FAILED tests/test_a.py::test_one - AssertionError\n' > "$VERIFY_JSTACK_SANDBOX/gh/logs/901"
  ```

- **Pass over the red main.** Run `record main-red jbus poll`, then `record main-red jbus events`. The log has `retro alpha: main check failed at dddddddddddd, 1 merges since the last green`.
- **Read the row.** Run `record main-red jbus queue show`. It lists `main-red-dddddddddddd`, priority 0, with `approved` empty.
- **Read the brief.** Run `record main-red cat "$HOME/.local/state/home/demo/tasks/main-red-dddddddddddd.md"`. It names the job's URL, `tests/test_a.py::test_one`, the merge `dddddddddddd feat: alpha (#7)`, `Playbook: bug-fix` and `Size: S`, and not `feat: older (#6)`.
- **Pass again.**
  Edit the brief (`echo 'Steers: edited' >> <that file>`), then run `record main-red jbus poll` and `record main-red jbus queue show`.
  The brief still ends with the edit, and the table still has one `main-red-` row.
- **Proof.** Copy `gh/calls.log`, the brief and `$JBUS_STATE_DIR/demo/queue.json` into `$VERIFY_JSTACK_EVIDENCE`, as the skill's Evidence section shows. `gh/calls.log` has the `check-runs` call for the red commit and the `actions/jobs/901/logs` call.

### A check that ends merges within seconds

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.

- **A reviewed pull request whose check is going.**
  Give it a real head, a check still going, and a clean review:

  ```sh
  head=$(git commit-tree -p HEAD -m beta "$(git rev-parse 'HEAD^{tree}')") && git push -q origin "${head}:refs/heads/beta" && "$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py > /dev/null
  jq --arg head "$head" '.[0].headRefOid = $head | .[0].statusCheckRollup[0].status = "IN_PROGRESS" | .[0].statusCheckRollup[0].conclusion = null' "$VERIFY_JSTACK_SANDBOX/gh/open.json" > "$VERIFY_JSTACK_SANDBOX/gh/o" && mv "$VERIFY_JSTACK_SANDBOX/gh/o" "$VERIFY_JSTACK_SANDBOX/gh/open.json"
  printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n\n## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" > "$HOME/.local/state/home/demo/tasks/beta.md"
  ```

- **A pass.**
  Run `record merge-tick jbus poll`, then `record merge-tick cat "$JBUS_STATE_DIR/demo/checks-pending.json"`.
  It lists `7`.
- **Ticks as the timer runs them.**
  In the background, run `jbus tick` every 5 seconds for a minute, each line with the time (`while :; do date +%T.%3N; jbus tick; sleep 5; done > ticks.log`).
  The first tick runs `jmerge`, and each tick after it asks `actions/runs` with `If-None-Match` and runs no `jmerge`.
- **The check ends.**
  Note the time, then set the check to `COMPLETED` and `SUCCESS` in `gh/open.json` and write one completed run to `gh/runs.json`.
  The next tick prints `tick demo: a run ended, and jmerge ran`, and `gh/calls.log` has `pr merge 7`, which the stand-in refuses, within 5 seconds of the noted time.
- **Proof.**
  Copy `ticks.log` and `gh/calls.log` into `$VERIFY_JSTACK_EVIDENCE`.

### A merged row's revert opens it again for its redo

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it.

- **Launch a reviewed row.**
  Run the first recipe's add, word and approve with the record name `revert-reland`, with `Review: review` and `Pull request: open one when done` in the brief, then `record revert-reland jbus poll`.
  It prints `launched alpha: mcp:sandbox-thread-1`.
- **Merge it onto a red main.**
  The crew commits in the worktree jbus made, GitHub squash-merges it as #7, and main's check fails there:

  ```sh
  S=$VERIFY_JSTACK_SANDBOX G=$VERIFY_JSTACK_SANDBOX/gh W=$HOME/.t3/worktrees/demo/alpha
  git config user.email sandbox@example.test && git config user.name sandbox
  green=$(git rev-parse HEAD)
  mkdir -p "$W/src/alpha" && echo 'x = 1' > "$W/src/alpha/a.py" && git -C "$W" add src/alpha/a.py && git -C "$W" commit -qm 'feat: alpha' && git -C "$W" push -q origin alpha
  head7=$(git -C "$W" rev-parse HEAD)
  git merge -q --squash alpha && git commit -qm 'feat: alpha (#7)' && git push -q origin main
  red=$(git rev-parse HEAD)
  printf '\n## Result\nStatus: done\nDone when: holds\nProof:\n- the demo test\nBranch: alpha   Pull request: https://example.test/pull/7\nChanged: src/alpha/a.py\nSteers: none\nLeft: none\n' >> "$HOME/.local/state/home/demo/tasks/alpha.md"
  jq 'map(.status = "completed" | .latestRunId = "run-1")' "$S/t3/threads.json" > "$S/t3/t" && mv "$S/t3/t" "$S/t3/threads.json"
  at=$(perl -MPOSIX -e 'print strftime("%Y-%m-%dT%H:%M:%SZ", gmtime(time - 7200))') before=$(perl -MPOSIX -e 'print strftime("%Y-%m-%dT%H:%M:%SZ", gmtime(time - 10800))')
  jq -n --arg red "$red" --arg at "$at" --arg h "$head7" '[{number: 7, url: "https://example.test/pull/7", title: "feat: alpha", headRefName: "alpha", headRefOid: $h, baseRefName: "main", mergeCommit: {oid: $red}, mergedAt: $at}]' > "$G/merged.json"
  jq -n --arg red "$red" --arg green "$green" --arg at "$at" --arg before "$before" '[{sha: $red, commit: {message: "feat: alpha (#7)", committer: {date: $at}}}, {sha: $green, commit: {message: "feat: older (#6)", committer: {date: $before}}}]' > "$G/commits.json"
  jq -n --arg red "$red" --arg green "$green" '{($red): [{name: "check", status: "completed", conclusion: "failure", id: 901, html_url: "https://example.test/o/r/actions/runs/77/job/901"}], ($green): [{name: "check", status: "completed", conclusion: "success", id: 800}]}' > "$G/checks.json"
  printf '2026-11-13T05:01:02Z FAILED tests/test_a.py::test_one - AssertionError\n' > "$G/logs/901"
  ```

- **Pass over the red main.**
  Run `record revert-reland jbus poll`.
  It prints `revert alpha: main red at <red's sha12>, jbus opened https://example.test/pull/8 to revert it`, and `jbus queue show --all` has alpha `merged` with `#7`.
  `gh/calls.log` has the `compare` of `$green...$head7` and the `pr revert https://example.test/pull/7`, and `t3/calls.jsonl` a `t3_thread_send` that tells `mcp:sandbox-thread-1` of the revert.
- **Merge the revert, and pass.**
  GitHub merges #8 and main's check passes there:

  ```sh
  git fetch -q origin && rv=$(git rev-parse origin/revert-7-alpha) && git merge -q --ff-only "$rv" && git push -q origin main
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  jq --arg rv "$rv" --arg now "$now" '. + [{number: 8, url: "https://example.test/pull/8", title: "Revert \"feat: alpha\"", headRefName: "revert-7-alpha", headRefOid: $rv, baseRefName: "main", mergeCommit: {oid: $rv}, mergedAt: $now}]' "$G/merged.json" > "$G/m" && mv "$G/m" "$G/merged.json"
  echo '[]' > "$G/open.json"
  jq --arg rv "$rv" --arg now "$now" '[{sha: $rv, commit: {message: "Revert \"feat: alpha\" (#8)", committer: {date: $now}}}] + .' "$G/commits.json" > "$G/c" && mv "$G/c" "$G/commits.json"
  jq --arg rv "$rv" '.[$rv] = [{name: "check", status: "completed", conclusion: "success", id: 902}]' "$G/checks.json" > "$G/k" && mv "$G/k" "$G/checks.json"
  jq 'map(.status = "completed" | .settled = false | .latestRunId = "run-2")' "$S/t3/threads.json" > "$S/t3/t" && mv "$S/t3/t" "$S/t3/threads.json"
  ```

  Run `record revert-reland jbus poll`, `record revert-reland jbus queue show --all` and `record revert-reland jbus events`.
  alpha is `left`, its `pr` column empty, the events have `reland alpha: its revert https://example.test/pull/8 merged, so the row is open for its redo`, and `$JBUS_STATE_DIR/demo/transitions.jsonl` has the line `merged` to `left` with `"reverted": "https://example.test/pull/8"`.
- **Push the redo with its desk proof, and pass twice.**
  The crew brings alpha back as a doc on its branch, with no rewrite of it, and writes the desk proof's Result:

  ```sh
  git -C "$W" pull -q --no-rebase --no-edit origin main
  git -C "$W" rm -q src/alpha/a.py && mkdir -p "$W/docs" && echo 'alpha, again' > "$W/docs/alpha.md" && git -C "$W" add docs/alpha.md && git -C "$W" commit -qm 'docs: alpha, again' && git -C "$W" push -q origin alpha
  redo=$(git -C "$W" rev-parse HEAD)
  printf '\n## Result, follow-up (the redo)\nStatus: done\nDone when: each holds\nProof:\n- the check: Checked below\nChecked: make check-fast BASE=%s PART=touched exit 0 at %s\nProved: none, docs\nBranch: alpha   Pull request: after the review\nChanged: docs/alpha.md\nSteers: none\nLeft: none\n' "$(git rev-parse origin/main)" "$redo" >> "$HOME/.local/state/home/demo/tasks/alpha.md"
  jq --arg w "$W" 'map(.status = "completed" | .settled = false | .archived = false | .latestRunId = "run-3" | .worktreePath = $w)' "$S/t3/threads.json" > "$S/t3/t" && mv "$S/t3/t" "$S/t3/threads.json"
  ```

  Run `record revert-reland jbus poll` twice.
  The first prints `launched review alpha: mcp:sandbox-thread-2 at <the redo's sha12>`, and `t3/calls.jsonl` has a `t3_thread_launch` titled `review: alpha, 1`.
- **Review it, open its pull request, and check.**
  The reviewer writes its section, and the crew opens #9 and names it:

  ```sh
  printf '\n## Review\nBy: claudeAgent claude-sonnet-5-5 #1\nVerdict: clean\nMeets the brief: yes, 1 of 1\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$redo" >> "$HOME/.local/state/home/demo/tasks/alpha.md"
  jq 'map(if .threadId == "mcp:sandbox-thread-2" then .status = "completed" | .settled = true else . end)' "$S/t3/threads.json" > "$S/t3/t" && mv "$S/t3/t" "$S/t3/threads.json"
  jq -n --arg h "$redo" '[{number: 9, url: "https://example.test/pull/9", title: "docs: alpha, again", headRefName: "alpha", headRefOid: $h, baseRefName: "main", mergeable: "MERGEABLE", isDraft: false, changedFiles: 1, files: [{path: "docs/alpha.md", additions: 1, deletions: 0, changeType: "ADDED"}], statusCheckRollup: [{__typename: "CheckRun", name: "check", status: "COMPLETED", conclusion: "SUCCESS"}, {__typename: "CheckRun", name: "borders", status: "COMPLETED", conclusion: "SUCCESS"}]}]' > "$G/open.json"
  printf '\n## Result, follow-up (the redo pull request)\nStatus: done\nDone when: each holds\nProof:\n- the check: Checked above\nBranch: alpha   Pull request: https://example.test/pull/9\nChanged: docs/alpha.md\nSkills run:\n- tdd: the demo test\nSteers: none\nLeft: none\n' >> "$HOME/.local/state/home/demo/tasks/alpha.md"
  ```

  Run `record revert-reland jbus poll`, then `record revert-reland jmerge --check`.
  alpha is `pr` with `#9`, and `jmerge --check` prints `ready 9 <the redo's sha> alpha alpha`: no wait line, and none that asks for an accept.
- **Pass, and merge.**
  Run `record revert-reland jbus poll`.
  `gh/calls.log` has the pass's `pr merge 9 --squash`, which the stand-in refuses, and no `--accept` anywhere.
  Merge #9 the way the revert was merged above, and run `record revert-reland jbus poll` and `record revert-reland jbus queue show --all`: alpha is `merged` with `#9`.
- **Proof.**
  Copy `t3/calls.jsonl`, `gh/calls.log`, the brief, `$JBUS_STATE_DIR/demo/queue.json` and `$JBUS_STATE_DIR/demo/transitions.jsonl` into `$VERIFY_JSTACK_EVIDENCE`.

## Gotchas

A queue row, from add to launch:

- A go is for the brief that jbus stored, `$JBUS_STATE_DIR/demo/briefs/alpha.md`, not the text you typed, and the row's `brief_sha` is of that file.
  `approve` needs no `--sha`, and takes one given beside the basis without reading it.
- `max_running` is 1 in the sandbox's config. A second approved row waits (`max_running is 1: <slug> waits`) while the first thread is `running` in `t3/threads.json`.
- jbus records a launch under `$JBUS_STATE_DIR/launches/demo/<slug>/`.
  It never launches a slug with a record again, so use a new slug, or a new sandbox, for a second launch.
- The stand-in gives every new thread the status `running`. Edit `t3/threads.json` to move it on (`completed`, or `"settled": true`).
- The first pass in a sandbox records the state it finds and reports nothing about it.
  So a recipe that needs jbus to report something must run one pass before that thing happens.

A decision wakes the home thread:

- A wake goes at most once in five minutes.
  After the first `woke` line, a recipe that needs a second wake waits five minutes or starts in a new sandbox.
  Do not edit `wake.json` to get past it.
- `jbus decide` acts for the project whose repo the shell is in.
  `env.sh` leaves the shell in the demo checkout.
- The stand-in takes every `t3_thread_send`.
  This recipe does not drive a home thread that T3 Code refuses.
  `failed_wakes` counts such failures, and the third in a row raises the `home thread demo` alert.
  `features/jbus/tests/test_jbus_wake_home.py` covers that case.
- The outbox may hold more than the decisions you raised, because a pass adds its own.
  Assert on the event you raised, not on a count.

A red main files the brief for its fix:

- The first pass in a sandbox files nothing for a red main it finds, and the next pass files it.
  Run one pass before you write the merge.
- jbus does not look at a commit older than a day, or at one with no merge in the day before it.
  Write the dates from `date`, not by hand.
- `gh/checks.json` is keyed by the full sha.
  A commit with no key has no check runs, and jbus reads that as pending, not green.
- jbus files the brief while the queue has no `main-red-<sha12>` row.
  So if you delete the brief while its row stays, jbus does not write it again.
  It also does not write the brief again once its row is removed.
- The stand-in `gh` lists no changed files for a commit, so `Where:` names only the failed tests' files in a sandbox.

A merged row's revert opens it again for its redo:

- jbus reverts only a culprit whose own head holds the green under the red, which it asks GitHub with `compare`.
  The stand-in answers that from `origin.git`, so every commit the recipe names is a real one pushed there: a sha written only to `gh/*.json` is not found, and the pass files `main-red-<sha12>` in place of the revert.
- jbus asks GitHub for the merged list only once a base branch moved in git.
  A merge written to `gh/merged.json` alone, over a main that did not move, makes the pass ask `gh pr view <the Result's address>`, and a merge the stand-in does not hold stops the pass at `wait demo: could not ask GitHub`.
  Push each merge to the sandbox's origin `main`.
- A desk proof with `Proved: none, docs` holds only for a change of docs: over a change to `src/` the pass prints `prereview-refused alpha` and launches no review.
  So the redo is a doc.
- jbus writes `Reviewer: <thread> #1` when it launches the review, so the round counts only a `## Review` whose `By:` line ends `#1`.
  Without it, or without `Meets the brief: yes, <n> of <n>`, jmerge waits on the review, which is no fault of the reland.
- The stand-in names no worktree for a thread until a drive writes its `worktreePath` in `t3/threads.json`.
  Without it the pass prints `prereview-refused alpha`, and tells the crew `T3 Code names no worktree for its crew`.
- The door hook refuses `git push -f`, even to the sandbox's origin, so the redo goes on the branch as a new commit.
