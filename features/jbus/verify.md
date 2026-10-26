# jbus

`jbus poll` is one pass over every project.
It reads the queue, the briefs, T3 Code and GitHub, launches what is approved and has room, tells each thread what it must act on, runs `jmerge`, and writes what it saw to the state directory.
Every other `jbus` verb reads or writes that state, and `jbus view` is a local web page over it.
This page has four journeys: a queue row from add to launch, a scout's request from add to launch, a gate that wakes the Chef, and a red main that files the brief for its fix.
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

A gate wakes the Chef (`gate-wake`):

- `gate-queue` queues a gate from stdin and prints `queued`.
- `gate-once` prints `already sent` for the same gate piped twice.
- `done-queue` queues a result from stdin.
- `wake-post` POSTs the waiting events to the webhook on the next pass, with the project's key.
- `wake-gap` holds what is queued within five minutes of the last POST.
- `status` prints the status file: the last pass, the outbox count, failed wakes.

A red main files the brief for its fix (`main-red`):

- `red-retro` reports main's failed check once, naming the merged slug and the merges since the last green.
- `red-brief` writes `tasks/main-red-<sha12>.md` with the failed job's URL, the failed test ids its log names, the merges since the last green with the files they changed, and `Playbook: bug-fix` and `Size: S`.
- `red-row` queues the brief unapproved, so `jbus queue show` lists the row with `approved` empty.
- `red-once` files nothing more for the same commit on a later pass, and leaves an edited brief as it is.

## How to get to it (user POV)

- Run `jbus queue add <slug> --priority <n>` with the brief on stdin.
- Run `jbus queue approve <slug> --by <who> --at "<YYYY-MM-DD HH:MM ZONE>" --sha <12 characters>`.
- Run `jbus queue hold <slug>`.
- Run `jbus queue show` to read the table.
- Run `jbus poll` for one pass.
  On the live machine, the systemd timer runs it.
- Run `jbus scout add <slug>` with the request on stdin, `jbus scout approve <slug> --sha <12 characters> --word <id>`, and `jbus scout show`.
- Run `jbus gate <slug>` with the gate's lines on stdin, from the project's repo.
- Run `jbus done <slug>` with the result's lines on stdin.
- Run `jbus poll` for one pass.
- Run `jbus status`.
- Read the message that the Chef posts to you once the webhook wakes it.
  A sandbox cannot reach the Chef.
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

- **Add the row.** Pipe a brief in. Run `printf '# alpha: a demo task\nWhere: `src/alpha/`\nPull request: none\n' | record queue-row jbus queue add alpha --priority 1`. The table has one row, `alpha`, priority 1, status `queued`, with `approved` and `brief_sha` empty.
- **Try a derived column.** Run `record queue-row jbus queue add gamma --priority 2 --status launched`. It prints `refused: status is derived from T3 Code and GitHub, and no command writes it` and exits 2. No `gamma` row is added.
- **Approve it.**
  Run `sha=$(shasum -a 256 "$JBUS_STATE_DIR/demo/briefs/alpha.md" | cut -c1-12)`, then `record queue-row jbus queue approve alpha --by user --at "2026-10-12 00:30 $(perl -MPOSIX -e 'print strftime("%Z", localtime(mktime(0, 30, 0, 12, 9, 126, 0, 0, -1)))')" --sha "$sha"`.
  The sandbox has no config of jstack's own, so the name is `user`.
  The word after the time is the abbreviation of the machine's zone at that time, and perl's `strftime` prints it.
  The row's `approved` reads `2026-10-12 00:30 <that word> by user` and its `brief_sha` is the 12 characters.
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
  Write a request in the shape of `features/scout/templates/scout-request.md` to `$VERIFY_JSTACK_SANDBOX/alpha.md`, with these lines: a first line `# alpha: <what to find out>`, a `Request:` line, a `Questions:` list, a `Deliver:` list, `Playbook: none` and `Out of bounds: read-only. <what it must not do>`.
- **Add it.**
  Run `record scout-path jbus --project demo scout add alpha < "$VERIFY_JSTACK_SANDBOX/alpha.md"`.
  It prints `added alpha: request <12 characters>, waits for a go`, and the request is in `$HOME/.local/state/home/demo/scouts/alpha.md`.
- **Try a crewmate's line.**
  Pipe in a request with a `Task:` line, as `printf '# beta: x\nTask: "do it"\n' | record scout-path jbus --project demo scout add beta`.
  It exits 1 and names `a Task: line, which only a crewmate's brief has`, and no `scouts/beta.md` is written.
- **Keep a word, and approve.**
  Run `record scout-path jbus word --to demo --by user --at "$(date '+%Y-%m-%d %H:%M %Z')" go`, which ends with the word's id, then `record scout-path jbus --project demo scout approve alpha --sha <the 12 characters> --word <the id>`.
  It prints `approved alpha: request <12 characters>, your word, ...`.
- **Pass.**
  Run `record scout-path jbus poll`.
  It prints `launched scout alpha: mcp:sandbox-thread-1`.
- **Check the launch itself.**
  Run `record scout-path jq -c 'select(.tool == "t3_thread_launch") | .arguments' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`.
  There is one line, titled `scout: alpha`, with the message `/scout alpha` and the workspace `{"type": "root"}`, and `t3/threads.json` gives its thread the branch `null`.
- **Check the repo.**
  Run `record scout-path git -C "$VERIFY_JSTACK_SANDBOX/demo" for-each-ref --format='%(refname)'`.
  It lists `main` and the origin's refs, and no other branch.
- **Pass again, and read the table.**
  Run `record scout-path jbus poll`, then `record scout-path jbus --project demo scout show`.
  Nothing more launches, and the row reads `| alpha | launched | none | mcp:sandbox-thread-1 | ...`.
- **Write a Report.**
  Append `## Report` with `Status: done` to the request, then run `record scout-path jbus --project demo scout show`.
  The row's report reads `reported`.
- **Proof.**
  Copy `t3/calls.jsonl`, `t3/threads.json`, the request and `$JBUS_STATE_DIR/demo/scouts.json` into `$VERIFY_JSTACK_EVIDENCE`.

### A gate wakes the Chef

Preconditions:

- You are in a new sandbox, `env.sh` is sourced, and the doctor prints `doctor: ok`.
- No `jbus poll` has run in it: `$JBUS_STATE_DIR/status.json` does not exist.

- **Status before a pass.** Run `record gate-wake jbus status`. It prints `refused: no status at <path>: no pass has run` and exits 1.
- **Pipe a gate.** Run `printf '## Gate <n>: may the demo task skip its tests?\nStatus: open\nDefault: it does not skip them\n' | record gate-wake jbus gate alpha`. It prints `queued`.
- **Pipe it again.** Run the same command. It prints `already sent`.
- **See it wait.**
  Run `record gate-wake jq -c '.[] | {event, slug, line}' "$JBUS_STATE_DIR/demo/outbox.json"`.
  It shows one event: `gate`, `alpha`, `gate alpha: may the demo task skip its tests?`.
- **Pass.** Run `record gate-wake jbus poll`. It prints `woke demo: 1 events`.
- **Check the POST.**
  Run `record gate-wake jq -c '{key, events: [.events[] | {project, event, slug, line}]}' "$VERIFY_JSTACK_SANDBOX/t3/wake.jsonl"`.
  The webhook got the gate event for the project `demo`, and `key` is `true`.
  So the POST carried the project's key in both headers jbus sends it in.
- **Pipe a result.** Run `printf 'Status: done\nBranch: alpha   Pull request: none\nLeft: none\n' | record gate-wake jbus done alpha`. It prints `queued`.
- **Pass inside the gap.** Run `record gate-wake jbus poll`. It prints no `woke` line, and `t3/wake.jsonl` still has one line.
- **Read the status.** Run `record gate-wake jbus status`. `projects.demo.outbox` is 1, `failed_wakes` is 0, and `last_pass` is this minute.
- **Proof.** Copy `t3/wake.jsonl` and `$JBUS_STATE_DIR/status.json` into `$VERIFY_JSTACK_EVIDENCE`.

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
- **Pass again.** Edit the brief (`echo 'Noticed: edited' >> <that file>`), then run `record main-red jbus poll` and `record main-red jbus queue show`. The brief still ends with the edit, and the table still has one `main-red-` row.
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

A gate wakes the Chef:

- A POST goes at most once in five minutes. After the first `woke` line, a recipe that needs a second POST waits five minutes or starts in a new sandbox. Do not edit `wake.json` to get past it.
- `jbus gate` and `jbus done` act for the project whose repo the shell is in.
  `env.sh` leaves the shell in the demo checkout.
  From any other directory they print `refused: no project for this repo`.
- jbus tells gates apart by the `## Gate <n>:` heading alone.
  The same question for the same slug is the same gate, whatever the other lines say.
- The stand-in's webhook always answers 200.
  This recipe does not drive a webhook that is down.
  `failed_wakes` counts such failures, and twelve failed wakes in a row raise a desktop notification.
  `features/jbus/tests/test_jbus_wake.py` covers that case.
- `wake.jsonl` keeps whether the key matched, never the key. `"key": false` is a POST with no key or a wrong one.
- The outbox may hold more than the events you piped, because a pass adds its own (`queue demo: the table changed`).
  Once a queue row exists, assert on the event you sent, not on a count.

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
