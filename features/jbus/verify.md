# jbus

`jbus poll` is one pass over every project.
It reads the queue, the briefs, T3 Code and GitHub, launches what is approved and has room, tells each thread what it must act on, runs `jmerge`, and writes what it saw to the state directory.
Every other `jbus` verb reads or writes that state, and `jbus view` is a local web page over it.
This page has four journeys: a queue row from add to launch, a scout's request from add to launch, a decision that wakes the home thread, and a red main that files the brief for its fix.
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

`features/jbus/tests/test_main_red_model.py` checks the red wait over every order of events.
The red wait is `main.json` as `mainmoved.tell` writes it and `rows.red` reads it.
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
- `scout-launch` launches one `scout: <slug>` thread on the next pass, in the project's own checkout, with no branch.
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

## How to get to it (user POV)

- Run `jbus queue add <slug> --priority <n>` with the brief on stdin.
- Run `jbus word --to <project> --message <thread id>/<message id>` to keep the user's word, then `jbus queue approve <slug> --sha <12 characters> --word <id>`.
- Run `jbus queue hold <slug>`.
- Run `jbus queue show` to read the table.
- Run `jbus poll` for one pass.
  On the live machine, the systemd timer runs it.
- Run `jbus queue add <slug> --priority <n>` with a scout's request on stdin, `jbus queue approve <slug> --sha <12 characters> --word <id>`, and `jbus queue show`.
- Run `jbus gate <slug>` with the gate's lines on stdin, from the project's repo.
- Run `jbus done <slug>` with the result's lines on stdin.
- Run `jbus poll` for one pass.
- Run `jbus status`.
- Read the wake in the project's home thread.
  A sandbox has no real thread.
- After a merge whose commit on main has a failed check run, run `jbus poll`.
  On the live machine, the systemd timer runs it.
- Run `jbus queue show` to see the row, and read the brief in the home's `tasks/`.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`, `machine/proc`, `machine/limits`, `gh/commits.json`, `gh/checks.json`, `gh/logs`, `home`

Each journey below starts in a new sandbox of its own, and its `record` name keeps the evidence apart.

### A queue row, from add to launch

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it, and `jbus queue show` has no rows.

- **Add the row.**
  Pipe a brief in.
  Run `printf '# alpha: a demo task\nTask: alpha, a demo task\nDone when:\n- the demo works\nProves it: the demo test\nSize: S\nWhere: `src/alpha/`\nDesign: none, a demo\nReview: none\nPlaybook: none\nPull request: none\nHome: root\n' | record queue-row jbus queue add alpha --priority 1`.
  The table has one row, `alpha`, priority 1, status `queued`, with `approved` and `brief_sha` empty.
- **Try a derived column.** Run `record queue-row jbus queue add gamma --priority 2 --status launched`. It prints `refused: status is derived from T3 Code and GitHub, and no command writes it` and exits 2. No `gamma` row is added.
- **Keep a word, and approve it.**
  Give the user's message to the stand-in with `printf '{"mcp:sandbox-chat": [{"itemId": "turn-item:message:m1", "messageId": "m1", "text": "go", "type": "user_message", "createdBy": "user", "updatedAt": "%s"}]}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$VERIFY_JSTACK_SANDBOX/t3/messages.json"`.
  Run `record queue-row jbus word --to demo --message mcp:sandbox-chat/m1`, which ends with the word's id.
  Then run `sha=$(grep -v '^Home:' "$JBUS_STATE_DIR/demo/briefs/alpha.md" | shasum -a 256 | cut -c1-12)` and `record queue-row jbus queue approve alpha --sha "$sha" --word <the id>`.
  The row's `approved` reads `your word, ...` and its `brief_sha` is the 12 characters.
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
  Write a request in the shape of `features/scout/templates/scout-request.md` to `$VERIFY_JSTACK_SANDBOX/alpha.md`, with these lines: a first line `# alpha: <what to find out>`, a `Request:` line, a `Questions:` list, a `Deliver:` list, `Playbook: none`, `Out of bounds: read-only. <what it must not do>` and `Home: root`.
- **Add it.**
  Run `record scout-path jbus --project demo queue add alpha --priority 1 < "$VERIFY_JSTACK_SANDBOX/alpha.md"`.
  The table has one row, `alpha`, with `scout` in its `role` column and `approved` empty, and the request is in `$JBUS_STATE_DIR/demo/briefs/alpha.md`.
- **Try a crewmate's line.**
  Pipe in a request with a `Size:` line, as `{ cat "$VERIFY_JSTACK_SANDBOX/alpha.md" | sed 's/^# alpha:/# beta:/'; echo 'Size: S'; } | record scout-path jbus --project demo queue add beta --priority 1`.
  It exits 1 and names `a Size: line, which only a crewmate's brief has`, and no `beta` row is added.
- **Keep a word, and approve.**
  Give the user's message to the stand-in with `printf '{"mcp:sandbox-chat": [{"itemId": "turn-item:message:m1", "messageId": "m1", "text": "go", "type": "user_message", "createdBy": "user", "updatedAt": "%s"}]}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$VERIFY_JSTACK_SANDBOX/t3/messages.json"`.
  Run `record scout-path jbus word --to demo --message mcp:sandbox-chat/m1`, which ends with the word's id, then `sha=$(grep -v '^Home:' "$JBUS_STATE_DIR/demo/briefs/alpha.md" | shasum -a 256 | cut -c1-12)` and `record scout-path jbus --project demo queue approve alpha --sha "$sha" --word <the id>`.
  The row's `approved` reads `your word, ...`.
- **Pass.**
  Run `record scout-path jbus poll`.
  It prints `launched scout alpha: mcp:sandbox-thread-1`.
- **Check the launch itself.**
  Run `record scout-path jq -c 'select(.tool == "t3_thread_launch") | .arguments' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`.
  There is one line, titled `scout: alpha`, with the message `/scout alpha` and the workspace `{"type": "root"}`, and `t3/threads.json` gives its thread the branch `null`.
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
  Run `record home-wake jbus decide alpha --question 'may the demo task skip its tests?' --reply 'scope: no, keep them'`.
  It prints `raised: alpha: may the demo task skip its tests?`.
- **Raise it again.**
  Run the same command.
  It prints `raised already: alpha: may the demo task skip its tests?`.
- **Pass.**
  Run `record home-wake jbus poll`.
  It prints `wakes demo: told mcp:sandbox-home of decision alpha: may the demo task skip its tests?. Reply: "demo scope: no, keep them"`.
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
  Run `record home-wake jbus decide beta --question 'may beta wait a day?' --reply 'scope: yes'`, then `record home-wake jbus poll`.
  It prints `wakes demo: told mcp:sandbox-home of decision beta: may beta wait a day?. Reply: "demo scope: yes"`, and the new line of `t3/wake.jsonl` names beta alone.
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

## Gotchas

A queue row, from add to launch:

- `--sha` is the sha of the brief that jbus stored, `$JBUS_STATE_DIR/demo/briefs/alpha.md`, not of the text you typed.
  Take it from that file.
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
