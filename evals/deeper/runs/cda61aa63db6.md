# home-limit-overrun: make homes stop before any turn that would cross their limit, with each refusal logged

Task: "Fix the homes running past their limits." Before changing anything, build the evidence from the raw record. From the session transcripts in `~/.claude/projects/*/*.jsonl` (per-turn `usage` and timestamps), the jbus thread logs, and the unit counters from `journalctl` and `systemctl show` if homes run as units, use `jq` to tabulate every home from the last two weeks: which limit (tokens, turns, wall-clock, cost), its configured value as the code reads it (`rg -n 'limit|budget|max_turns|max_tokens'`), the actual figure, the overshoot, and the turn of the breach. Find the enforcement path, and show whether the check runs before or after a turn spends and whether crewmates count against their home. Reproduce one overrun with a stub model under `pytest -k limit`. If homes once kept their limits, bisect with `git bisect run`. Then fix it so a home stops before any turn that would cross its limit: zero overshoot, with each refusal logged. It is done when the new test fails on the old code and passes on the new; when the same `jq` table over at least 20 homes run after the fix shows zero overruns; and when I have read the before and after tables. Do not widen the work to changing what the limits are.
Done when:
- A "before" `jq` table covers every home from the last two weeks, built from the session transcripts, the jbus thread logs, and the unit counters if homes run as units. Each row gives the limit (tokens, turns, wall-clock or cost), the configured value as the code reads it, the actual figure, the overshoot, and the turn of the breach.
- The enforcement path is identified. The findings show whether the check runs before or after a turn spends, and whether crewmates count against their home.
- A stub-model test under `pytest -k limit` reproduces an overrun. It fails on the old code and passes on the new.
- If homes once kept their limits, `git bisect run` has found the commit that broke it.
- A home stops before any turn that would cross its limit, with zero overshoot, and each refusal is logged.
- The same `jq` table, run over at least 20 homes after the fix, shows zero overruns.
- The user has read the before and after tables.
Where: the code that reads and enforces home limits (find it with `rg -n 'limit|budget|max_turns|max_tokens'`); how a home's spend is counted, including its crewmates; the limit tests under `pytest -k limit`; and, read only, `~/.claude/projects/*/*.jsonl`, the jbus thread logs, `journalctl` and `systemctl show`.
Do not touch: the limit values themselves. Do not change what the limits are. Leave the session transcripts, thread logs and unit records unchanged.
Decisions: "fix it so a home stops before any turn that would cross its limit: zero overshoot, with each refusal logged"; "Do not widen the work to changing what the limits are."
Design: none, the user already set the behaviour (stop before the crossing turn, zero overshoot, log each refusal), and the work is to move or repair an existing check, not to choose a new design.
Pull request: ask first
Review: review
Playbook: none
