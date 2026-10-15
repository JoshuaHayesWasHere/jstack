## 1. What a top professional would do
The field is observability engineering for LLM spend (FinOps / telemetry). They would not build a dashboard from hand counts. They would:
- Derive every number from the per-message `usage` records the API already writes, and attribute each record to a task and a home through a join key, not by reading.
- Reconcile the totals against the provider's own billing before anyone trusts the view.

## 2. The rawest material
- `~/.claude/projects/*/*.jsonl` (Claude Code session transcripts): in place of hand-counted token tallies. Each assistant line carries `message.usage.{input_tokens,output_tokens,cache_creation_input_tokens,cache_read_input_tokens}`, `sessionId`, `timestamp` and `model`.
- The `isCompactSummary` / compaction entries in those same JSONL files: in place of a remembered sense of "context got full". Each one is a dated event of hitting the window.
- The jbus thread and gate logs (`jbus` store, plus `tasks/<slug>.md` front matter): in place of memory of which session belonged to which home and task. These supply the session→thread→slug join.
- Anthropic Console usage export, or the Admin API `GET /v1/organizations/usage_report/messages`: in place of trusting our own sum. This is the billed truth per day and per model.

## 3. The methods and tools
- `jq -c 'select(.message.usage) | {sessionId, timestamp, model: .message.model, u: .message.usage}' ~/.claude/projects/*/*.jsonl`: extracts raw events, one row per API call, before any aggregation.
- `sqlite3 usage.db` with tables `calls`, `sessions(sessionId, thread, slug, home)`: aggregates by a join, not by eye. Rollups are `GROUP BY slug` and `GROUP BY home`. An explicit `unattributed` bucket is kept and never hidden.
- Context occupancy per turn, computed as `input + cache_read + cache_creation` of each call: the method is a time series per session, with its peak and its compaction count, not a single "context used" guess.
- `watch -n 60` or a `systemd --user` timer running the ingest, with `hyperfine 'ingest'`: the view stays current, and its cost is measured.
- A hand-counted session from today as a fixture (`pytest tests/test_usage.py`): the old manual method becomes the regression test for the new one.

## 4. What outside the agent shows it is right
- The Console / Admin API usage report. Our per-day, per-model token totals must match it within 1%, over the last 7 days. That is a demanding target, and it is a reasonable one, since both read the same `usage` fields.
- The `unattributed` bucket must stay under 2% of tokens. Anything above that means the join key is broken, not that the work is unknowable.
- The fixture test: it must fail on an empty ingest and pass with the exact numbers from one session the user counted by hand.
- The user's own check: they open the view and can answer "what did task X cost, and how close did home Y get to the window" in under 10 seconds, without opening a transcript.

## Rewritten prompt
```
"i can montior every single aspect of work in a digestable format": tokens and context per task
and per home are counted by hand today. Replace the hand count with numbers derived from the raw
usage records.

Start from the raw material, not summaries: the Claude Code transcripts in
~/.claude/projects/*/*.jsonl (message.usage on every assistant line, plus the compaction entries),
and the jbus threads and tasks/<slug>.md for the session→thread→task→home join. Pull the Anthropic
Console usage export (or the Admin API usage_report) as the billed reference.

Method: extract one row per API call with jq into sqlite3. Join sessions to slug and home. Roll
up tokens (input, output, cache write, cache read) per task and per home. Compute context
occupancy per turn (input + cache_read + cache_creation) as a time series, with its peak and its
compaction count. Keep an explicit 'unattributed' bucket. Run the ingest on a systemd --user
timer and print one digestible table per task and per home.

Done when: per-day, per-model totals match the Console/Admin API report within 1% over the last
7 days; unattributed tokens are under 2%; a pytest fixture built from one session I counted by
hand fails on an empty ingest and passes with my exact numbers; and I can answer "what did task X
cost, and how close did home Y get to the window" from the view in under 10 seconds.
```
