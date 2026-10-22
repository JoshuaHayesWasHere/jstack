## 1. What a top professional would do
An observability / metering engineer. They would not build a dashboard first. First they would find the event that records every token at the source, one usage record per model call, and attribute each record to a task and a home through a join key that already exists. Then they would reconcile the totals against the bill before anyone trusts a chart. "Context" would get a measured definition: the input plus cache tokens of a turn, as a share of the window. A felt one would not count.

## 2. The rawest material
- `~/.claude/projects/*/*.jsonl` (every session transcript; each assistant line carries `message.usage` with `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, plus `sessionId`, `cwd`, `timestamp`, `message.model`): in place of the token counts copied by hand
- `ls ~/.claude/projects/` (the directory name encodes the cwd, e.g. `-tmp`): in place of remembering which home a session belonged to
- jbus's own log of threads and gates (expected under the jbus state dir, e.g. `jbus log` or its sqlite file), giving thread id → slug: in place of a note of which crewmate ran which task
- `tasks/<slug>.md` briefs, for the slug ↔ session/thread link: in place of the scout's summary of what each task was
- The Anthropic Console usage export (console.anthropic.com → Usage → export CSV) or the Admin API usage report (`/v1/organizations/usage_report/messages`): in place of trusting the transcripts as the bill

## 3. The methods and tools
- `jq -c 'select(.message.usage) | {sessionId, cwd, timestamp, model: .message.model, u: .message.usage}' ~/.claude/projects/*/*.jsonl`: extract at the source, one row per model call, before any aggregation
- `sqlite3 usage.db` with `.import` (or `sqlite-utils insert`): one table of calls joined to a table of session → thread → slug → home, so "per task" and "per home" are `GROUP BY`s, not sums done by hand
- Per-turn context = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of each call, with its max and its last value per session as a share of the model's window: a defined metric, not an impression
- `npx ccusage daily` / `npx ccusage session` (install with `npm i -g ccusage` if missing): an independent parser of the same transcripts to cross-check against
- `watch -n 30` or an `inotifywait -m ~/.claude/projects` hook re-running the extract: freshness without hand counting
- Dedupe on `message.id`, because streamed or retried lines can repeat. Count rows before and after.

## 4. What outside the agent shows it is right
- For one chosen day, the per-day totals of the four token types agree with the Anthropic Console / Admin API usage report within 1% (unreasonable for most homemade meters; reasonable here, since both read the same `usage` fields)
- The same totals agree with `ccusage daily` exactly (same source, independent parser)
- One task the user already counted by hand reproduces their number, and any gap is explained line by line
- Every row has a slug and a home, with zero unattributed calls (a `SELECT count(*) WHERE slug IS NULL` that returns 0)
- The user reads the per-task / per-home view and can answer "what did task X cost and how full did its context get" in under 10 seconds, with no hand counting

## Rewritten prompt
```
"i can montior every single aspect of work in a digestable format": today tokens and context
per task and per home are counted by hand; make that automatic.

Start from the raw usage records, not from counts or summaries: the `message.usage` of every
assistant line in ~/.claude/projects/*/*.jsonl (with sessionId, cwd, timestamp, model,
message.id), the project directory name for the home, jbus's thread log and tasks/<slug>.md
for session → thread → slug. Pull the Anthropic Console usage export (or the Admin API usage
report) for one recent day as the bill to reconcile against.

Extract with jq into one sqlite3 table of calls, deduped on message.id, joined to a table of
session → slug → home. Define context per turn as input + cache_creation + cache_read tokens,
and report its max and last value per task as a share of the model's window. Produce one
per-task and one per-home view (tokens by type, calls, peak context %), refreshed on its own
when transcripts change.

Done when: one day's totals match the Console / Admin API usage within 1% and `npx ccusage
daily` exactly; a task I counted by hand reproduces my number; zero calls are left without a
slug and home; and I can read any task's cost and peak context from the view in under 10
seconds.
```
