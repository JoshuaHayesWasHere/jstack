# jstack models

One line per role. Skills that read `pstack-models.mdc` read this file
instead. Delete a line to fall back to the skill's default. Edit by hand.

A value is `<provider>/<model> <effort>`. Providers are the T3 Code provider
instances: `claude` (Claude Code), `codex` (Codex), `cursor` (Cursor). A
`claude/` value can run as a native subagent with `model` and `effort`. Any
other provider runs through T3 Code's `delegate_task`. `inherit-parent` runs
the role on the parent chat's model.

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
