# usage-ledger: derive per-task and per-home token and context numbers from raw usage records
Task: "i can montior every single aspect of work in a digestable format": tokens and context per task and per home are counted by hand today. Replace the hand count with numbers derived from the raw usage records.
Done when:
- Per-day, per-model totals match the Console/Admin API usage report within 1% over the last 7 days.
- Unattributed tokens are under 2% of the total.
- A pytest fixture built from one session the user counted by hand fails on an empty ingest and passes with the user's exact numbers.
- "What did task X cost, and how close did home Y get to the window" can be answered from the view in under 10 seconds.
- The ingest runs on a systemd --user timer and prints one digestible table per task and one per home.
- The view shows, per task and per home, input, output, cache write and cache read tokens, plus context occupancy per turn (input + cache_read + cache_creation) as a time series with its peak and compaction count.
Where: the Claude Code transcripts in ~/.claude/projects/*/*.jsonl (message.usage on every assistant line, plus the compaction entries), read-only; the jbus threads and tasks/<slug>.md, read-only, for the session→thread→task→home join; the Anthropic Console usage export or the Admin API usage_report as the billed reference; a new ingest (jq into sqlite3) with its sqlite database, view and table printer; a systemd --user service and timer; the pytest fixture and test.
Do not touch: the transcripts, jbus threads and tasks/<slug>.md files, which are read-only sources; the hand-counted numbers in the fixture, which must not be adjusted to make the test pass; any Admin API key or Console credentials, which stay out of the repo, logs and printed output.
Decisions: "Start from the raw material, not summaries"; "extract one row per API call with jq into sqlite3"; "Join sessions to slug and home"; "Roll up tokens (input, output, cache write, cache read) per task and per home"; "Keep an explicit 'unattributed' bucket"; "Run the ingest on a systemd --user timer and print one digestible table per task and per home".
Design: none, the user already set the method: the sources, one row per API call via jq into sqlite3, the join, the rollups, the occupancy series, the unattributed bucket and the timer.
Pull request: ask first
Review: review
Playbook: none
