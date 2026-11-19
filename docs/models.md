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
   effort, so there only a seat on the session's own model runs natively.
2. Otherwise, in T3 Code, call `orchestrator_capabilities` once, then
   `delegate_task` with that provider instance, model, and effort.
3. Outside T3 Code, run the seat on the session model and say so.
4. If a model or effort is rejected, use the nearest valid one of the same
   family, or drop the seat, and say so. A panel keeps at least two seats.

No role runs above `xhigh`. Gemini tops out at `high`.

```
# defaults: 3
# budget: large (xhigh)
feature, refactoring: claude/claude-opus-5-5 xhigh
bug-fix: claude/claude-opus-5-5 xhigh
perf-issue: claude/claude-opus-5-5 xhigh
hillclimb: claude/claude-opus-5-5 xhigh
judgment and prose: claude/claude-opus-5-5 xhigh
arena runners: claude/claude-fable-5-2 high, claude/claude-opus-5-5 high, cursor/gemini-4-carbon high
arena cross-judge pool: cursor/gemini-4-carbon high, codex/gpt-6.1-sol high, claude/claude-opus-5-5 high
swarm workers: claude/claude-opus-5-5 high
interrogate reviewers: claude/claude-fable-5-2 high, claude/claude-opus-5-5 high, cursor/gemini-4-carbon high
council: claude/claude-opus-5-5 xhigh, codex/gpt-6.1-sol xhigh, cursor/gemini-4-carbon high
sol-loop reviewer: codex/gpt-6.1-sol xhigh
```

The cross-judge pool lists a non-Claude seat first, because Arena's judge
must come from a vendor other than the parent chat's.
