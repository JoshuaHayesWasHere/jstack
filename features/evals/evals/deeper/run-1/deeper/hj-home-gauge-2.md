## 1. What a top professional would do
A reliability engineer working on resource limits would not start by tightening a number. They would first count the overruns: which homes, which limit (tokens, wall-clock, turns, crewmates spawned), and by how much. Then they would find the exact point where the limit is checked and why the check misses. The usual suspects are a check that runs only between turns, a count that leaves out crewmates' spend, or a limit that is advisory and never enforced. They would want the limit enforced from outside the home's own judgment, so a home cannot reason its way past it.

## 2. The rawest material
- `~/.claude/projects/*/*.jsonl`, the homes' own session transcripts, with the per-turn `usage` token counts summed by session: in place of a remembered "they keep going over" or a home's self-reported spend
- `jbus log` (or the bus's message store, queried directly), the timestamps of each home's launch, its crewmate launches and its last message: in place of a scout's summary of which homes overran
- The limits as configured: the home/brief files that state them (`tasks/<slug>.md` `Done when:` and budget lines, and the home's config): in place of the limit as people recall it
- `journalctl --user` and `/sys/fs/cgroup/.../memory.events`, `cpu.stat` for the homes' processes, if homes run as units: in place of guessing at wall-clock and CPU overrun

## 3. The methods and tools
- A census before a fix: `jq` over the transcripts (`jq -s '[.[]|.message.usage? // empty]|...'`) joined against each home's stated limit gives a table of home, limit, actual, and overrun %. This establishes the baseline and the shape of the failure.
- Reading the enforcement path: `rg -n 'limit|budget|max_' ` over the home and jbus code to find every place a limit is checked. The method is to name the one check that misses, not to add a second one beside it.
- A reproduction with a tiny limit: launch one home with a limit of a few thousand tokens or 60 s, and watch it with `pidstat -p <pid> 1` and `jbus log -f`. This is a failing case before any change.
- Hard enforcement from outside the process: `systemd-run --user --scope -p RuntimeMaxSec=… -p MemoryMax=…`, or `timeout`, for wall-clock and memory, plus a token meter that is checked before each model call rather than after the turn. The limit becomes a wall, not a request.

## 4. What outside the agent shows it is right
- A test that launches a home with a small limit fails before the fix (the home overruns) and passes after it. Passing means the home stops within one model call of the limit, at ≤5% over budget, and leaves a jbus message saying it stopped and why.
- The census, rerun on the next week of transcripts, shows 0 homes over their limit, against the baseline count from the first census. Zero is the right target: a limit that is passed sometimes is not a limit.
- The cgroup counters (`memory.events` `max`, the unit's `RuntimeMaxSec` stop in `journalctl`) record the kill when a home does try to run past its limit. These are the kernel's verdict, not the home's.

## Rewritten prompt
```
"Fix the homes running past their limits."

Start from the raw record, not from impressions: sum the per-turn token usage in the homes'
transcripts (~/.claude/projects/*/*.jsonl) by session, take each home's launch, crewmate
launches and last message from `jbus log`, and join both against the limits as written in
each brief and home config. Produce a table: home, limit, actual, overrun %. That is the
baseline.

Then find, in the home and jbus code (`rg -n 'limit|budget|max_'`), the one place each
limit is checked and why it misses (checked only between turns, crewmates' spend not
counted, or advisory only). Reproduce it first: launch a home with a tiny limit and show it
overrunning. Fix it at that check: count spend before each model call, include crewmates,
and enforce wall-clock and memory from outside the home with systemd-run/timeout limits,
so a home cannot decide to keep going.

Done when: a test that launches a home with a small limit fails before the fix and passes
after, with the home stopping within one model call of its limit (≤5% over) and posting a
jbus message saying why; the census rerun on the following week's transcripts shows 0 homes
over their limit against the baseline; and any home that still pushes past is stopped by the
cgroup, with the stop recorded in journalctl. Do not widen the work beyond the limits the
homes already have.
```
