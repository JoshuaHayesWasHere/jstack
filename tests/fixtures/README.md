# Fixtures

`projects/-tmp-pipeline-check/` holds trimmed copies of two real sessions, recorded on 2026-10-09 with Claude Code 2.1.296. They are the two probe sessions behind `docs/meter-findings.md`. The tests in `tests/test_probes.py` hold `jgauge session` to a recount made by hand from the untrimmed files.

| Session | What ran |
|---|---|
| `a59133d5-...` | A home that started one scout (`aa8a78fa...`) in the foreground. |
| `4aa8337b-...` | A home that started a builder (`a2232bee...`), which started a scout of its own (`a6eb3a80...`). |

`projects/-tmp-plain-thread/` and `projects/-tmp-small-agent/` are written by hand for `tests/test_session.py`, not taken from a real session: a plain thread with no subagent, and one small session that the tests copy in as a thread's subagent. Their counts are small on purpose, so the expected sums can be checked by eye. `msg_p1` and `msg_b1` each sit on more than one line.

For the `-tmp-pipeline-check` sessions, what was kept: every `user` and `assistant` line, in order, with its `type`, `uuid`, `timestamp`, `sessionId`, `agentId`, `version`, the message's `id`, `model`, `stop_reason`, the four token counts of `usage`, and the tool calls. The Agent result lines keep the counts of `toolUseResult` and the harness's `<usage>` text, which `jgauge` does not read: a subagent's last call has no finished line here, so its output is counted as a floor.

What was dropped: every other line type (attachments, queue operations, titles, cost state), thinking signatures, long texts, the builder's report (replaced by a short placeholder, so its reply size here is not the real one), the subagents' meta files, and every other field.
