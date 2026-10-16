# A red main files the brief for its fix

When main's check fails at a commit within a day of a merge, a pass says `retro <slug>: main check failed at <sha12>, <n> merges since the last green`. The same pass writes the brief for the fix, `tasks/main-red-<sha12>.md` in the home's state, and adds it to the queue with no go: the user sees a `main-red-<sha12>` row waiting for approval. It is filed once for each red commit.

## Sub-features

- `red-retro` says the red main once, naming the merged slug and the merges since the last green.
- `red-brief` writes `tasks/main-red-<sha12>.md` with the failed job's URL, the failed test ids its log names, the merges since the last green and the files they changed, `Playbook: bug-fix` and `Size: S`.
- `red-row` queues the brief unapproved, so `jbus queue show` lists the row with `approved` empty.
- `red-once` files nothing more for the same commit on a later pass, and leaves an edited brief as it is.

## How to get to it (user POV)

- Run `jbus poll`, which the systemd timer runs on the live machine, after a merge whose commit on main has a failed check run.
- Run `jbus queue show` to see the row, and read the brief in the home's `tasks/`.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `gh/merged.json`, `gh/commits.json`, `gh/checks.json`, `gh/logs`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- No `jbus poll` has run in it.

- **First pass.** Run `record main-red jbus poll`. It only records what is already so: a finding about the past is not filed on a project's first pass.
- **Merge alpha onto a red main.** Write the outside world: a brief for `alpha`, a merge of it at a red commit over a green one, a failed `full` job at the red commit, and that job's log.

  ```sh
  red=dddddddddddddddddddddddddddddddddddddddd green=ffffffffffffffffffffffffffffffffffffffff
  printf '# alpha: a demo task\nWhere: `src/alpha/`\n' > "$HOME/.local/state/home/demo/tasks/alpha.md"
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ) before=$(date -u -d '-2 hours' +%Y-%m-%dT%H:%M:%SZ)
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

- The first pass in a sandbox files nothing for a red main it finds: run one pass before the merge is written.
- A commit older than a day, or one with no merge in the day before it, is not looked at. Write the dates from `date`, not by hand.
- `gh/checks.json` is keyed by the full sha. A commit with no key has no check runs, which reads as pending, not green.
- jbus files the brief while the queue has no `main-red-<sha12>` row: a brief deleted while its row stays is not written again, and neither is one whose row was removed.
- The stand-in `gh` lists no changed files for a commit, so `Where:` names only the failed tests' files in a sandbox.
