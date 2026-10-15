## 1. What a top professional would do
A reliability engineer working on resource governance would first establish which limit is overrun (tokens, wall-clock, turns, crewmates launched), in how many runs, and by how much. They would want that from every run on record, not from the one remembered case. They would also find where each limit is checked compared with where the spend happens. A budget checked only between turns lets one long turn, or a crewmate launched just before the check, run past it. They would reproduce the overrun in a failing test before changing any code.

## 2. The rawest material
- The homes' own session transcripts, `~/.claude/projects/*/*.jsonl`, with the per-turn `usage` fields and timestamps: in place of the impression that "homes run long".
- jbus's own log and message history (`jbus log` or its store under `~/.local/share/jbus/`), showing each home's launches, gates and stop messages with times: in place of a home's own summary of what it did.
- The code and config where the limits are declared and enforced, found with `rg -n 'limit|budget|max_(turns|tokens|crew)|deadline' homes/ principles/ tasks/`: in place of a remembered number for what the limits are.
- The briefs' `Result` sections in `tasks/*.md` that report a stop or an overrun: in place of a crewmate's "done within budget".
- `git log -S'limit' --oneline` across the enforcement code: in place of a guess at when the overruns began.

## 3. The methods and tools
- `jq` over the transcripts, e.g. `jq -s '[.[] | .message.usage? // empty] | map(.input_tokens + .output_tokens) | add' <session>.jsonl`, run once per home and compared with that home's limit: an overrun table of runs, the limit hit, the amount over and the turn where it was crossed. This measurement comes before any fix.
- `rg` and a read of the enforcement call sites: map each limit to the point where it is checked and the point where it is spent, to find the gap. The likely causes are a check after the call instead of before it, crewmate spend not counted against the home, or a timer that does not cover child processes.
- `git bisect run <the failing test>`: if the overruns began at some point, bisect to the commit instead of guessing.
- `/usr/bin/time -v` and `pidstat -t -p <pid> 1` on a live home and its crewmates: wall-clock and CPU across the whole process tree, not just the parent. `pidstat` comes from `sysstat`; install it with `pacman -S sysstat` if it is missing.
- `pytest -x tests/` (or the repo's runner), with a test that drives a home under a deliberately tiny limit: reproduce the overrun first, then fix it.

## 4. What outside the agent shows it is right
- A test that starts a home with a tiny limit for each kind of limit (tokens, turns, wall-clock, crewmates). It must fail on the current code and pass after the fix. It asserts that the home stops before the action that would cross the limit, not after it.
- A replay of the overrun table over the last N real runs' transcripts, after the fix ships. It must show zero runs over their limit. The target is 0 tokens over and 0 seconds over, not "within a turn's worth": deciding before each call whether the call would cross the limit is reasonable, so this target is reasonable too.
- The user's own check of the before-and-after overrun table built from the transcripts.

## Rewritten prompt
> "Fix the homes running past their limits." Start from the raw record, not from impressions:
> the homes' session transcripts in `~/.claude/projects/*/*.jsonl` (per-turn `usage` and
> timestamps), jbus's log of launches and stops, the `Result` sections of `tasks/*.md`, and the
> code where each limit is declared and enforced (`rg -n 'limit|budget|max_|deadline'`). With
> `jq`, build a table of every recorded run: which limit, the amount over, and the turn or
> launch that crossed it. Then map each limit's check against the place it is spent, and find
> why the check lets the spend through. Measure the whole process tree with `/usr/bin/time -v`
> and `pidstat`, and use `git bisect run` if the overruns began at a commit. Before changing
> anything, write a test that runs a home under a tiny limit of each kind and fails on today's
> code. Fix the enforcement so a home stops before the action that would cross its limit. Done
> when that test passes, and when a replay of the overrun table over the last N real runs shows
> zero overruns: 0 tokens and 0 seconds over, a target that is reasonable here. Show the
> before-and-after table so I can check it myself.
