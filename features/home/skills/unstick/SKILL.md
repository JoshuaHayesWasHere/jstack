---
name: unstick
description: "Find why rows of the jbus queue have not moved, from jbus's own records: each stalled row's cause and age, the reversible step that moves it taken at once, and the rest parked as gates. Use for /unstick, 'why are we stalled', 'why is nothing moving', 'why do these crewmates look stalled'."
disable-model-invocation: true
card: "Catch up and keep track | 5 | Names why each stalled row of the queue has not moved, from jbus's records: a gate, a review, checks, a slot, the usage limit or a dead thread, with its age. It takes the reversible step that moves each row and parks the rest as gates. | Reach for it when the pipeline looks stalled and you want the cause, not a catch-up. | op: the operator"
---

# unstick

`ketchup` catches up and does not diagnose.
This skill reads what jbus recorded and says, row by row, why the work stopped, then moves what it can.

## 1. Read the records

This prints every open row past its stage's 90th percentile, oldest first, with its cause, its age and what to do.
It reads jbus's state and the test slots' waiters, and writes nothing:

```sh
S=$(realpath ~/.claude/skills/unstick 2> /dev/null)/scripts/unstick.py
if [ ! -f "$S" ]; then
    echo "no unstick: the skill's script is not installed at $S"
elif ! command -v uv > /dev/null; then
    echo "no unstick: uv is not installed here"
else
    uv run --script "$S"
fi
```

Add `--project <name>` to read one project, and `--all` to see every open row, stalled or not.
`nothing is stalled` ends the skill: say so in one line, with the count it gives.

Each stalled row is two lines.
The first is `<project> <slug>: <stage> <age> (p90 <its stage's p90>), <cause>: <the evidence>`.
The cause is one of `gate`, `review`, `checks`, `slot`, `usage-limit`, `dead-thread`, `depends`, `approval`, `held`, `thread-asks`, `leftover`, `closed`, `result`, `working`, `launching`, `next-pass` and `unknown`, each read from a record: the pass's own judgement of the row (`work.json`), an open question, a slot waiter, or a capped provider in the row's events.
The second line is what to do, by its first word.

## 2. Do what each line says

- `act: send <thread>: <text>` or `act: tell <thread>: <what>`: send that thread the message now, with the `t3-code` server's `t3_thread_send` (if your harness defers it, load it first).
  `send` gives the text as it is; `tell` gives what to say, which you word as one line from this thread.
  Each is reversible: the thread reads it and goes on.
- `wait: <when>`: do nothing; the line says what moves it and when.
- `user: <what>`: jbus already holds this for the user (a question, a go, a hold on a pull request).
  Name it, with the command the line gives where it gives one, and raise nothing more.
- `gate: <default>`: no record settles it.
  Take the default the line gives, where it is reversible, at once, and park the question with `jbus gate <slug>`, the gate's lines on stdin: it checks them against jstack's gate template and names each line that is missing.
  On `unknown`, read the row's events first (`jbus --project <name> events --slug <slug>`), and put what they show in the gate's `Context:` line.

A row whose cause is `depends` moves when the row it waits on does: unstick that one first, and say so on both.

## 3. Report

Answer in one table, oldest first: project, slug, stage, age, cause, and what you did (`sent`, `waits until <when>`, `yours: <the command>`, `gate <number>`).
Under it, one line for each `user` row, each decidable from that line alone.
Then stop: what jbus should have noticed by itself is not this skill's to fix.
