## 1. What a top professional would do
A site reliability engineer, treating this as an incident class rather than a bug report. They would first count and timeline every overrun: which limit (tokens, turns, wall-clock, cost), which home, by how much, and on which turn. Then they would find the one place the limit is checked and show why the check comes after the spend instead of before it. They would not touch the code until they could reproduce one overrun on demand.

## 2. The rawest material
- The homes' own session transcripts, `~/.claude/projects/*/*.jsonl`, with each turn's `usage` and timestamp: in place of the remembered sense that "homes run long".
- The jbus message and thread log for each home (`jbus log <thread>` or its store on disk): in place of the homes' own Result notes about when they stopped.
- The limit definitions as the code reads them, found with `rg -n 'limit|budget|max_turns|max_tokens' homes/ principles/`: in place of the limits as written in a brief or a principle.
- If homes run as units, the machine's counters, from `journalctl --user -u 'home-*'` and `systemctl --user show home-<slug> -p CPUUsageNSec,MemoryPeak,ActiveEnterTimestamp`: in place of the homes' self-reported elapsed time.

## 3. The methods and tools
- `jq` over the transcripts, for example `jq -s 'map(.message.usage // empty) | ...'` per home: one table of limit against actual, overshoot and the turn of the breach, for every home in the last two weeks, before any fix.
- `rg` and a read of the enforcement path: a cause found in code, showing whether the check runs before or after a turn spends, and whether subagents and crewmates are counted against their home.
- A fake-model harness (a stub that returns fixed-size turns) under `pytest -k limit`: the overrun reproduced as a failing test before it is fixed.
- `git log -S '<the limit check>'`, then `git bisect run pytest -k limit` if homes once stayed within their limits: a bisect over a guess.
- `systemd-cgtop` and `pidstat -u -r 5` during one live home, if the limit is time or memory: measured counters, not elapsed time from the log.

## 4. What outside the agent shows it is right
- A test that drives a stub home past each limit fails on the current code and passes after the fix, with overshoot of 0. Not "within one turn": the home must stop before a turn that would cross the limit. A good SRE would call that a reasonable target.
- The same `jq` table, run over transcripts of homes launched after the fix (at least 20 runs), shows zero overruns. A turn that was refused for budget is logged as refused, not silently dropped.
- The user reads the before and after tables and agrees the limits now hold.

## Rewritten prompt
> "Fix the homes running past their limits." Before changing anything, build the evidence from
> the raw record. From the session transcripts in `~/.claude/projects/*/*.jsonl` (per-turn
> `usage` and timestamps), the jbus thread logs, and the unit counters from `journalctl` and
> `systemctl show` if homes run as units, use `jq` to tabulate every home from the last two
> weeks: which limit (tokens, turns, wall-clock, cost), its configured value as the code reads
> it (`rg -n 'limit|budget|max_turns|max_tokens'`), the actual figure, the overshoot, and the
> turn of the breach. Find the enforcement path, and show whether the check runs before or
> after a turn spends and whether crewmates count against their home. Reproduce one overrun
> with a stub model under `pytest -k limit`. If homes once kept their limits, bisect with
> `git bisect run`. Then fix it so a home stops before any turn that would cross its limit:
> zero overshoot, with each refusal logged. It is done when the new test fails on the old code
> and passes on the new; when the same `jq` table over at least 20 homes run after the fix
> shows zero overruns; and when I have read the before and after tables. Do not widen the work
> to changing what the limits are.
