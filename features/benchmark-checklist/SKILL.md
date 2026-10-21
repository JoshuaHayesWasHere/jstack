---
name: benchmark-checklist
description: Vet a measured number (its limiter, tuning, limits, errors, repeatability, relevance, and whether the work happened) before it is reported or acted on. Use for /benchmark-checklist, or when a playbook step names this skill.
tip: vets a measured number before it is reported or acted on | benchmark | benchmarks | benchmarked | measured number
disable-model-invocation: true
card: "Distrust the change | 4 | Vets a measured number before it is reported: its limiter, its tuning, its errors, whether it repeats, and whether the work happened. | Reach for it when a speedup, a regression or an eval result is about to be believed. | op: the operator; plain: a step of `perf-issue`, `hillclimb`"
---

# Benchmark checklist

Use this when you produce a performance number: a pull request's before and after, a regression claim, a harness for `playbooks/hillclimb.md`, a choice between two libraries or settings. Answer each question with evidence from a run, not with a guess about the code.

For a quick ballpark the user asked for, one run is enough. Still check questions 4 and 7, and say that it is one run. Skip the rest unless that run looks wrong. A choice between options is never a ballpark.

A path such as `playbooks/<name>.md` or `principles/<name>.md` is from the root of the repo this skill lives in. `principles/principle-explain-the-number.md` is the reason behind the questions.

## Before you run anything

- Write down the claim you expect to make, in the words you would ship: "export is 30% faster at the median on the 60k-row dataset". The questions test that sentence.
- Read the measurement script. Note what it times, what it counts and what it ignores.
- Check the load with `uptime` and the cores with `nproc`. Many threads share a machine: if it is busy, find out with what. If you cannot wait for it, run the sides in turn so both see the same noise, and say so in the report.

## Taking the runs

Run this, with the round count and the commands filled in. One command gives a baseline, two are compared:

```sh
S=$(realpath -q ~/.claude/skills/crew/../benchmark-checklist || true)
if [ ! -f "$S/scripts/runs.sh" ]; then
    echo "no runs: scripts/runs.sh of this skill was not found by way of ~/.claude/skills/crew"
else
    sh "$S/scripts/runs.sh" "${ROUNDS:-5}" "<command A>" "<command B>"
fi
```

`scripts/runs.sh` is beside this file. Each command is one argument, run by `sh -c` in the directory the block runs in. The sides run in turn (A, B, A, B), so warm-up, caches and drift favour neither. It prints a row per run (round, side, seconds, exit status, and the last line the run printed), then for each side its runs, its failed runs, and the median, least and most seconds. A command that ends by printing its count of work done, as a test run does, answers question 7 in that last column. Two sides that need two checkouts are two commands that each `cd` to their own worktree.

It times a whole command. A number from inside a process (a request's latency, a frame time) comes from the repo's own harness: then that harness is the command, and the questions are the same.

A command that starts several workers (a browser suite, a parallel build, a test run with more than one worker) is a heavy suite, and the measurement runs one at a time on the whole machine, the lock around the whole call and not around one side: `flock ~/.local/state/locks/heavy-suite.lock sh "$S/scripts/runs.sh" ...`, as `skills/crew/SKILL.md` "Do the task" says of a heavy suite. It queues behind other threads: give the call a long time limit and wait.

## The questions

1. **Why not double?** Name the limiter. Profile in a run you do not report, since a profiler slows the work down: the processor per process (`top`), the profiler the runtime ships (`python -m cProfile`, `node --cpu-prof`, `perf`), and system calls (`strace -c`). Map the hot spot to source. Watch the load generator too: if it is saturated first, you measured the load generator. If a change did not move the number, the limiter says why, so find it before you call the change useless.
2. **Was it tuned?** Run every side the way production runs it: release builds, production flags and environment, batching, pools, caches as warm or cold as production sees them, the same versions and data. If one side runs on defaults, you compared settings, not implementations. A limiter that is a setting (a commit per row, a debug build, a missing index) means that side is untuned: tune it and measure again before you pick a winner. If you cannot tune it, pick no winner from that run.
3. **Did it break limits?** Do the arithmetic. Compare bytes per second with the disk and the network, operations per second times the cost of one with the cores, and the time saved with the time the changed piece took. Removing a piece that takes 10% of the run makes the run at most about 11% faster. A result past a limit measured something other than the work: a cache, a no-op, a bug.
4. **Did it error?** Count failures, and check that the output is right and not only there. A rejection is often fast, and a timeout or a retry is slow. The script's `failed` column counts exit statuses that are not zero. If the command exits zero on a failure, make it count the failures itself.
5. **Does it reproduce?** At least 5 rounds, in turn, as the script does. Report the median and the range. A gap smaller than the spread between runs is no measurable difference.
6. **Does it matter?** Beside any small result, measure the path a user waits on from end to end, with real sizes of data and real concurrency, and report the small result as a share of the whole. A helper that takes 1% of a request makes the request at most 1% faster, however fast the helper gets.
7. **Did it even happen?** Confirm that the work ran inside the timed region: the request reached the server, the rows were written, the bytes were read, the result was used. Lazy code (a generator nobody iterates, a promise nobody awaits) and timeouts give numbers for work that never happened. A count of the work done, printed last by the command, settles it: the script keeps that line beside each run.

## Report

- Lead with the verdict: faster, slower, no measurable difference, or inconclusive.
- Give the number with its unit, the number of runs, the range and the limiter: "median 41 ms to 33 ms, 7 runs a side, 32 to 35 ms after, bound by JSON parsing on one core".
- The verdict is inconclusive when you claim a difference and cannot name the limiter, when a side ran untuned, or when you could not check questions 4 and 7. Name the gap.
- A pull request's body carries one primary number, under Verification (`features/writing/playbooks/opening-a-pr.md`). The runs, the range and the evidence for the limiter go on the Result's `Proof:` line.

## Where it is used

- `playbooks/perf-issue.md`: the baseline, before a fix is planned from it, and every number after.
- `playbooks/hillclimb.md`: the harness, before it is frozen. A frozen harness prints its count of errors and of work done, so each keep-or-revert has questions 4 and 7 answered.
