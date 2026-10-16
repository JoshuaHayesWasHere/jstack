# jgauge

`jgauge` prints what a thread cost in tokens, and says whether the machine and the plan have room for one more thread. For token counts it reads the transcripts Claude Code wrote under `~/.claude/projects/` and nothing else.

| Command | What it does |
|---|---|
| `jgauge session [--format json] <project>/<session>.jsonl` | Prints what one thread cost: a row for the session, a row for each subagent it started (found under `<session>/subagents/`), and the total. It prints a table, and with `--format json` the same report as JSON. |
| `jgauge context <project>/<session>.jsonl` | Prints one number: how full the thread's context is now. It is the input side of the transcript's last call, and 0 for a transcript with no call. `hooks/home-gauge.sh` tells a home the same count, which it works out with `jq`. |
| `jgauge room` | Prints `go`, or `wait: ` and the first reading with no room. The readings are the one-minute load at or over 85% of the cores, under 6 GB of memory available, memory pressure (`some avg60`) at or over 10, more than 85% of the file slots of `/tmp` used, and the plan's five-hour or weekly limit at or over 85% used. A machine reading it cannot read is a `wait: `. A plan limit it cannot read stops nothing: `jgauge room` then prints `go` with a `note: ` line on stderr. With `jgauge room --wait <seconds>` it looks again until the answer is `go` or that long has passed, then prints the last answer and exits 0 on `go` and 75 on a `wait: `. `jgauge room --wait <seconds> --every <seconds>` sets the pause between two looks, 15 seconds with none. |
| `jgauge test-slot [--slots N] -- <command>` | Runs the command while it holds one of N machine-wide test slots, and ends with the command's exit code. A slot is a lock file, `~/.local/state/locks/test-slot.<n>.lock`. When all are held it prints `test-slot: waiting for one of <N> slots` on stderr and waits. N is `--slots`, else `TEST_SLOTS`, else 2. |

`src/jgauge/room.sh` is the one copy of the room check. The `home` skill runs it before a launch, the `pr-review` skill before a review, and `jbus` before each launch. A crewmate runs its one full run of the check command under a test slot: `jgauge test-slot -- make check`.

The counting rule is in `src/jgauge/transcript.py`, and `docs/meter-findings.md` has the observations behind it:

- **A call** is one `message.id`. A message has one line per content block, so `jgauge` never counts lines. It counts a message id seen in two transcripts of one report once.
- **Total** is input, cache write, cache read and output added up.
- **Peak context** is the largest input side (input plus cache read plus cache write) of any one call. Across rows it is the largest, never a sum.
- **Context** is the input side of the last call, which is what the next call sends again.
- **A floor** is the output of a call that has no finished line in the transcript. `jgauge` includes it in the total as the least that call's output can be, and a note under the table says how many calls and how many tokens. It estimates nothing upward.

A subagent's last call often has no finished line in its own transcript, so its output is a floor. `jgauge session` on a reviewer thread counts the whole review in the thread's own row: a reviewer starts no subagent.
