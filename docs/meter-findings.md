# What `jgauge` reads from a transcript

`jgauge` counts tokens from the transcripts Claude Code writes. Claude Code does not document their shape, and it can change between versions. This page records what two probe sessions showed, and why the counting rule in `src/jgauge/transcript.py` is what it is.

The two sessions were recorded on 2026-10-09 with Claude Code 2.1.296. Trimmed copies are in `tests/fixtures/projects/-tmp-pipeline-check/`, and `tests/fixtures/README.md` says what was kept. `tests/test_probes.py` holds `jgauge session` to a recount made by hand from the untrimmed files.

| Session | What ran |
|---|---|
| `a59133d5-...` | A session that started one scout in the foreground. |
| `4aa8337b-...` | A session that started a builder, which started a scout of its own. |

## Where the transcripts are

```
~/.claude/projects/<project>/<session_id>.jsonl
~/.claude/projects/<project>/<session_id>/subagents/agent-<agent_id>.jsonl
```

The subagents of a session are in that one `subagents/` directory, also a subagent that another subagent started. An agent that a workflow started is one level below, in `subagents/workflows/<workflow id>/`. `jgauge session` searches the whole directory.

Every line has `sessionId`, `timestamp` and `version`, the version of Claude Code that wrote it. A subagent's line also has `agentId`.

## A subagent's own transcript gives a floor for output

An `assistant` line holds `message.id`, `message.model` and `message.usage`. A message has one line per content block, and every such line has the same `message.id`. A line written before the message finished has a null `stop_reason`, and its `output_tokens` is the count as the message started. That count is a floor. The input and cache counts are the same on every line of a message.

In both probe sessions, no subagent's last message has a finished line in the subagent's own transcript:

- The first session's scout shows `output_tokens: 3` on its only message. Claude Code reported 184 for that call.
- The builder shows 2 and 24 on its two messages. Claude Code reported 798 for its last call.

So a sum over a subagent's transcript gives exact input and cache counts for each call, and a floor for output. It does not give the final output.

## The starter's transcript has the last call's final count

The transcript of whoever started the subagent holds a `user` line with the result of the Agent call. For a subagent the session started, that line has a top-level `toolUseResult` object:

```json
{
  "status": "completed",
  "agentId": "aa8a78fae39e2eb67",
  "agentType": "scout",
  "resolvedModel": "claude-haiku-5-5",
  "totalDurationMs": 1635,
  "totalTokens": 6778,
  "totalToolUseCount": 1,
  "usage": {
    "input_tokens": 2,
    "output_tokens": 184,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 6592
  }
}
```

`usage` is the usage of the subagent's last call, with its final output count. `totalTokens` is the last call only: that call's input, cache write, cache read and final output added up. It is not the subagent's total, and it does not include the subagents that the subagent started:

- The scout made one call, and its `totalTokens` is 6778, which is 2 + 6592 + 0 + 184.
- The builder made two calls. Its `totalTokens`, 21975, is its second call alone: 2 + 2623 + 18552 + 798. Its first call is not in it.
- The builder started a scout that spent 6350. The builder's 21975 does not include it.

A subagent that another subagent started gets no `toolUseResult` in its starter's transcript. The text of the Agent call's result ends with `<usage>subagent_tokens: N ...</usage>`, where N is the same last-call total.

For these reasons `jgauge` never uses `totalTokens` as a cost. It sums a subagent's own transcript once per `message.id`, and counts a nested subagent from that subagent's own transcript.

## The session's own lines

In a session's own transcript, a finished message has a line with a `stop_reason` and the final `output_tokens`. A message can appear on two lines with the same id and the same counts. `jgauge` counts a call once per `message.id`, and takes the counts from the line that has a `stop_reason`.

## What `jgauge` does with this

- It reads transcripts and nothing else. It reads no hook payload, no `.meta.json` file and no `toolUseResult`.
- It takes input, cache read, cache write and the model of each call from the transcript, once per `message.id`.
- It takes the output of a call from the line with a `stop_reason`. A call with no such line has a floor. `jgauge` keeps the floor apart from the final output, adds it into the total as the least that the call's output can be, and says under the table how many calls and tokens are floors.
- It does not read the starter's `toolUseResult.usage`, so the last call of a subagent stays a floor. In the first probe session `jgauge session` counts 3 output tokens for the scout, not 184.
- It estimates nothing.
