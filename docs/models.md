# jstack models

One line per role. Skills that read `pstack-models.mdc` read this file
instead. Delete a line to fall back to the skill's default. Edit by hand.

A value is `<provider>/<model> <effort>`. Providers are the T3 Code provider
instances: `claude` (Claude Code), `codex` (Codex), `cursor` (Cursor),
`antigravity` (Antigravity).
`inherit-parent` runs the role on the parent chat's model.

## Running a seat

1. If the seat's provider is the harness you are running in (`claude/` in
   Claude Code, `codex/` in Codex, `cursor/` in Cursor, `antigravity/` in
   Antigravity), spawn a native
   subagent with that model and effort, mapped by your harness file in
   `docs/harness/`. Antigravity's native subagents cannot pick a model and
   effort, so there only a seat on the session's own model and effort runs
   natively.
2. Otherwise, in T3 Code, call `orchestrator_capabilities` once, then
   `delegate_task` with that provider instance, model, and effort.
3. Outside T3 Code, run the seat on the session model and say so.
4. If a model or effort is rejected, use the nearest valid one of the same
   family, or drop the seat, and say so. A panel keeps at least two seats.

No role runs above `xhigh`. Gemini 4 Carbon tops out at `high`.

```
# defaults: 3
# budget: standard (high)
feature, refactoring: claude/claude-opus-5-5 medium
bug-fix: claude/claude-opus-5-5 medium
perf-issue: claude/claude-opus-5-5 high
hillclimb: claude/claude-opus-5-5 high
judgment and prose: antigravity/gemini-4-neon medium
arena runners: claude/claude-opus-5-5 high, codex/gpt-6.2-sol medium, antigravity/gemini-4-carbon medium
arena cross-judge pool: antigravity/gemini-4-neon medium, codex/gpt-6.2-sol medium, claude/claude-opus-5-5 medium
swarm workers: antigravity/gemini-4-neon medium
interrogate reviewers: claude/claude-sonnet-5-5 high, antigravity/gemini-4-carbon medium, antigravity/gemini-4-neon medium
council: antigravity/gemini-4-neon high, codex/gpt-6.2-sol high, antigravity/gemini-4-carbon medium
neon-loop reviewer: antigravity/gemini-4-neon high
```

The cross-judge pool lists a non-Claude seat first, because Arena's judge
must come from a vendor other than the parent chat's.
