# A queue row, from add to launch

The jbus queue is a table of work waiting for a crew thread. A user adds a row with its brief, approves the brief they were shown, and the next pass launches a crew thread for it, writes the thread into the brief, and shows it in the table.

Paths: `src/jbus/queue.py`, `src/jbus/dispatch.py`, `src/jbus/work.py`, `src/jbus/waiting.py`, `src/jbus/stall.py`, `src/jbus/plan.py`
Tests: `tests/test_jbus_approval.py`, `tests/test_jbus_approve_by_page.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_brief_meaning.py`, `tests/test_jbus_dispatch.py`, `tests/test_jbus_kitchen.py`, `tests/test_jbus_plan.py`, `tests/test_jbus_queue.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_resume.py`, `tests/test_jbus_row_ends.py`, `tests/test_jbus_row_history.py`, `tests/test_jbus_unlock.py`, `tests/test_stall.py`, `tests/test_work.py`

## Sub-features

- `queue-add` adds a row with its brief from stdin, unapproved and `queued`.
- `queue-approve` records who approved, when, and for which brief (the first 12 of its sha256).
- `queue-hold` takes the approval back, and an unapproved row is not launched.
- `queue-launch` launches one crew thread for an approved row on the next pass.
- `queue-thread-line` writes `Thread: <id>` into the brief the crewmate reads.
- `queue-derived` refuses a command that tries to write a derived column.

## How to get to it (user POV)

- Run `jbus queue add <slug> --priority <n>` with the brief on stdin.
- Run `jbus queue approve <slug> --by <who> --at "<YYYY-MM-DD HH:MM ZONE>" --sha <12 characters>`.
- Run `jbus queue hold <slug>`.
- Run `jbus queue show` to read the table.
- Run `jbus poll`, which the systemd timer runs on the live machine, for one pass.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`, `machine/proc`, `machine/limits`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- No `jbus poll` has run in it, and `jbus queue show` has no rows.

- **Add the row.** Pipe a brief in. Run `printf '# alpha: a demo task\nWhere: `src/alpha/`\nPull request: none\n' | record queue-row jbus queue add alpha --priority 1`. The table has one row, `alpha`, priority 1, status `queued`, with `approved` and `brief_sha` empty.
- **Try a derived column.** Run `record queue-row jbus queue add gamma --priority 2 --status launched`. It prints `refused: status is derived from T3 Code and GitHub, and no command writes it` and exits 2. No `gamma` row is added.
- **Approve it.** Run `sha=$(sha256sum "$JBUS_STATE_DIR/demo/briefs/alpha.md" | cut -c1-12)`, then `record queue-row jbus queue approve alpha --by user --at "2026-10-12 00:30 $(date -d '2026-10-12 00:30' +%Z)" --sha "$sha"`. The sandbox has no config of jstack's own, so the name is `user` and the word after the time is what the machine's zone prints for it, which `date` gives. The row's `approved` reads `2026-10-12 00:30 <that word> by user` and its `brief_sha` is the 12 characters.
- **Hold it, and pass.** Run `record queue-row jbus queue hold alpha`, then `record queue-row jbus poll`. The row's `approved` is empty again, the pass prints no `launched` line, and `$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl` has no `t3_thread_launch`.
- **Approve again, and pass.** Run the approve command again, then `record queue-row jbus poll`. It prints `launched alpha: mcp:sandbox-thread-1`.
- **Read the table.** Run `record queue-row jbus queue show`. The row's `status` is `launched` and its `thread` is `mcp:sandbox-thread-1`.
- **Check the launch itself.** Run `record queue-row jq -c 'select(.tool == "t3_thread_launch") | .arguments | {title, workspaceStrategy}' "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl"`. There is one line, titled `crew: alpha`, with a worktree on the branch `alpha` from `main`.
- **Check the brief.** Run `record queue-row cat "$HOME/.local/state/home/demo/tasks/alpha.md"`. It is the brief that was piped in, with the line `Thread: mcp:sandbox-thread-1` added.
- **Pass again.** Run `record queue-row jbus poll`. Nothing is launched: `t3/calls.jsonl` still has one `t3_thread_launch`.
- **Proof.** Copy `t3/calls.jsonl`, `gh/calls.log`, the brief and `$JBUS_STATE_DIR/demo/queue.json` into `$VERIFY_JSTACK_EVIDENCE`, as the skill's Evidence section shows.

## Gotchas

- `--sha` is of the brief jbus stored, `$JBUS_STATE_DIR/demo/briefs/alpha.md`, not of the text you typed. Take it from that file.
- `max_running` is 1 in the sandbox's config. A second approved row waits (`max_running is 1: <slug> waits`) while the first thread is `running` in `t3/threads.json`.
- A launch is recorded under `$JBUS_STATE_DIR/launches/demo/<slug>/`. A slug with a record is never launched again, so use a new slug, or a new sandbox, for a second launch.
- The stand-in gives every new thread the status `running`. Edit `t3/threads.json` to move it on (`completed`, or `"settled": true`).
- The first pass in a sandbox only records what was already so. A recipe that needs a finding about the past sent needs a pass before the thing happens.
