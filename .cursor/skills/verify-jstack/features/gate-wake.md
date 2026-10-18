# A gate wakes the Chef

A thread with a question only the user can answer pipes it to `jbus gate`, and a thread that has finished pipes its result to `jbus done`. jbus keeps each as an event in the project's outbox, and the next pass POSTs what waits to the project's webhook, at most once in five minutes. `jbus status` says what the last pass left.

Paths: `src/jbus/questions.py`, `src/jbus/wake.py`, `src/jbus/alert.py`, `src/jbus/digest.py`, `src/jbus/record.py`, `src/jbus/word.py`, `src/jbus/asks.py`
Tests: none

## Sub-features

- `gate-queue` queues a gate from stdin and prints `queued`.
- `gate-once` prints `already sent` for the same gate piped twice.
- `done-queue` queues a result from stdin.
- `wake-post` POSTs the waiting events to the webhook on the next pass, with the project's key.
- `wake-gap` holds what is queued within five minutes of the last POST.
- `status` prints the status file: the last pass, the outbox count, failed wakes.

## How to get to it (user POV)

- Run `jbus gate <slug>` with the gate's lines on stdin, from the project's repo.
- Run `jbus done <slug>` with the result's lines on stdin.
- Run `jbus poll` for one pass.
- Run `jbus status`.
- Read the message the Chef posts where the webhook leads (not reachable from a sandbox).

## Driving it with verify-jstack

Needs: `demo`, `config`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- No `jbus poll` has run in it: `$JBUS_STATE_DIR/status.json` does not exist.

- **Status before a pass.** Run `record gate-wake jbus status`. It prints `refused: no status at <path>: no pass has run` and exits 1.
- **Pipe a gate.** Run `printf '## Gate <n>: may the demo task skip its tests?\nStatus: open\nDefault: it does not skip them\n' | record gate-wake jbus gate alpha`. It prints `queued`.
- **Pipe it again.** Run the same command. It prints `already sent`.
- **See it wait.** Run `record gate-wake jq -c '.[] | {event, slug, line}' "$JBUS_STATE_DIR/demo/outbox.json"`. One event: `gate`, `alpha`, `gate alpha: may the demo task skip its tests?`.
- **Pass.** Run `record gate-wake jbus poll`. It prints `woke demo: 1 events`.
- **Check the POST.** Run `record gate-wake jq -c '{key, events: [.events[] | {project, event, slug, line}]}' "$VERIFY_JSTACK_SANDBOX/t3/wake.jsonl"`. The webhook got the gate event for the project `demo`, and `key` is `true`: the POST carried the project's key in both headers jbus sends it in.
- **Pipe a result.** Run `printf 'Status: done\nBranch: alpha   Pull request: none\nLeft: none\n' | record gate-wake jbus done alpha`. It prints `queued`.
- **Pass inside the gap.** Run `record gate-wake jbus poll`. It prints no `woke` line, and `t3/wake.jsonl` still has one line.
- **Read the status.** Run `record gate-wake jbus status`. `projects.demo.outbox` is 1, `failed_wakes` is 0, and `last_pass` is this minute.
- **Proof.** Copy `t3/wake.jsonl` and `$JBUS_STATE_DIR/status.json` into `$VERIFY_JSTACK_EVIDENCE`.

## Gotchas

- A POST goes at most once in five minutes. After the first `woke` line, a recipe that needs a second POST waits five minutes or starts in a new sandbox. Do not edit `wake.json` to get past it.
- `jbus gate` and `jbus done` speak for the project whose repo the shell is in. `env.sh` leaves the shell in the demo checkout: from any other directory they print `refused: no project for this repo`.
- The gate's one line is its `## Gate <n>:` heading. The same question for the same slug is the same gate, whatever the other lines say.
- The stand-in's webhook always answers 200. A webhook that is down (`failed_wakes`, the desk notification after twelve in a row) is not driven here: `tests/test_jbus_wake.py` covers it.
- `wake.jsonl` keeps whether the key matched, never the key. `"key": false` is a POST with no key or a wrong one.
- The outbox may hold more than the events you piped: a pass adds its own (`queue demo: the table changed`). Assert on the event you sent, not on a count, once a queue row exists.
