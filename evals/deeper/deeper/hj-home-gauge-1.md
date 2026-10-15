## 1. What a top professional would do
A site reliability engineer who owns resource governance. Before touching any code, they would first count the overruns: which homes went past which limit (tokens, turns, wall-clock or memory), how often, and by how much. That census shows whether the limit is never checked, checked too late (accounting lag, or a check only between long steps), or checked against the wrong counter. They would fix the place where enforcement happens. They would not raise the limits or add a wrapper on top.

## 2. The rawest material
- Each home's own session transcripts, with per-turn usage fields: `~/.claude/projects/*/<thread-id>.jsonl`. These replace remembered "it ran long" impressions and the crewmates' summaries of their runs.
- jbus's event log for each home's thread (start, every step, limit checks, stop): `jbus log <slug>`, or its store at the expected `~/.local/share/jbus/` (`sqlite3 …/jbus.db '.tables'`). These replace the status lines the homes report about themselves.
- The limits as configured, read from the file that sets them (the home definitions under `homes/` and jbus's config). This replaces the limit values as people remember them.
- The kernel's record of process overruns: `journalctl --user -u 'jbus*' --since -7d`, plus `memory.events` and `cpu.stat` under `/sys/fs/cgroup/user.slice/user-$UID.slice/`. These replace guesses about whether a home was killed or just ran on.
- The history of the enforcement code: `git log -p -S '<limit field name>'` in the jbus repo. This replaces "it used to work".

## 3. The methods and tools
- `jq` over the transcripts, e.g. `jq -s 'map(.message.usage.output_tokens // 0) | add'` for each thread, joined against each home's configured limit. **Method:** a census of every overrun from the past week, each with its size, before any fix.
- `sqlite3` or `jbus log` to place each limit check on the timeline next to the step that crossed the limit. **Method:** classify every overrun as unchecked, checked late, or miscounted.
- A minimal repro: a throwaway home with an absurdly low limit (1 turn, 1,000 tokens, 30 s), launched through jbus. **Method:** reproduce the failure deterministically before fixing it.
- `git bisect run <repro script>` if the census shows a date when overruns began. **Method:** a bisect instead of a guess.
- `pidstat -r -u -p <pid> 1` and `systemd-cgtop` while the repro runs, for memory and wall-clock limits. **Method:** measure what the process actually does against the cap. The first is in `sysstat`; install it with `pacman -S sysstat` if it is missing.

## 4. What outside the agent shows it is right
- A test in jbus's suite that launches a home with a limit of N and asserts that it stops at or below N, with overshoot no larger than one step. The test must fail on the current code and pass after the fix.
- Re-run the census over the week of homes after the fix, from the same transcripts and logs. It must show zero homes past their limit. That target is ambitious but reasonable: a hard cap that is enforced at the right point has no tail.
- The user's own check, after a week of normal use: no home they launched ran past its limit.

## Rewritten prompt
```
"Fix the homes running past their limits."

Start from the raw record, not from reports: the homes' transcripts in
~/.claude/projects/*/<thread-id>.jsonl, jbus's own event log for each home's thread
(jbus log <slug> / its sqlite store), the limits as written in the home and jbus config,
and journalctl plus the cgroup memory.events/cpu.stat for anything killed or throttled.

First make a census with jq/sqlite3: every home in the past week that went past a limit,
which limit (tokens, turns, wall-clock, memory), and by how much. Classify each overrun
as never checked, checked too late, or counted wrong. Reproduce the worst class with a
throwaway home that has an absurdly low limit. If overruns began on a date, git bisect
run the repro. Fix it where the limit is enforced. Do not raise limits or add a wrapper.

Done when: a new test that launches a home with limit N and asserts it stops at or below N
(overshoot no more than one step) fails on the old code and passes on the new, and
re-running the census over the homes after the fix shows zero past their limit.
```
