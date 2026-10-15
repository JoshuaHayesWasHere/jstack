## 1. What a top professional would do
An observability engineer who does LLM cost accounting would replace the hand count with the counter the API already writes. They would insist on two things:
- Every number traces back to a raw usage record, keyed to its session, task and home.
- The totals reconcile against the provider's own bill before anyone reads the digest built on them.

## 2. The rawest material
- `~/.claude/projects/*/*.jsonl`, one file per session. Each assistant line's `message.usage` holds `input_tokens`, `output_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`, along with `sessionId`, `cwd` and `timestamp`. This replaces the hand-counted tally.
- `tasks/<slug>.md`, the briefs, and the home's thread ids in jbus (expected as `jbus log <thread>` or the jbus store on disk). These give the session → task → home mapping. They replace remembering which session served which task.
- Context size per turn, computed as `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` on each assistant line. Its peak against the model's window shows how full the context got. This replaces an eyeballed "context felt full".
- The Anthropic Console usage export (Usage → Export CSV) for the same dates. This replaces trusting the local count.

## 3. The methods and tools
- `jq -c 'select(.message.usage) | {s:.sessionId, t:.timestamp, cwd, u:.message.usage}' ~/.claude/projects/*/*.jsonl`: extract the raw usage records before any summarising.
- `duckdb` (`pacman -S duckdb`, or `pip install duckdb`) or `sqlite3`: load the JSONL into one table and `GROUP BY` task and home. The digest is a query, not a tally.
- `npx ccusage@latest daily --json`: an independent parser of the same files, used to cross-check the per-day totals.
- `hyperfine 'make usage-report'`: measure that the digest regenerates fast enough to run on every task's close.
- Method: count once at the source, join on ids rather than names, and reconcile against the bill before presenting any number.

## 4. What outside the agent shows it is right
- Per-day token totals match the Console usage export within 0.5%, for each of the four token kinds. That target is reasonable, since both read the same API counters.
- Per-day totals agree with `ccusage` exactly, because it reads the same JSONL.
- The user picks one task they counted by hand last week, and the report reproduces that figure.
- No session's tokens are left unattributed to a task or home. Any orphan is listed by `sessionId`.
- The report regenerates in under 2 seconds and needs zero hand counting.

## Rewritten prompt
> "i can montior every single aspect of work in a digestable format": tokens and context per
> task and per home are counted by hand today; replace that hand count with a generated digest.
> Start from the raw usage records in `~/.claude/projects/*/*.jsonl` (`message.usage`:
> input, output, cache-creation and cache-read tokens, with `sessionId`, `cwd`, `timestamp`),
> joined to tasks via `tasks/<slug>.md` and to homes via their jbus thread ids. Report context
> per turn as input + cache-read + cache-creation, with its peak per task against the model's
> window. Extract with `jq`, aggregate in `duckdb` (or `sqlite3`) by task and by home, and
> cross-check with `npx ccusage daily --json`. It is done when:
> - per-day totals match the Anthropic Console usage export within 0.5% for every token kind
>   and agree exactly with ccusage;
> - one task I counted by hand is reproduced;
> - every session is attributed or listed as an orphan by id;
> - the digest regenerates in under 2 seconds (`hyperfine`) with no hand counting at all.
