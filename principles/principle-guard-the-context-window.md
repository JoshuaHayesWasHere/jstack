# Guard the Context Window

Apply when context is filling up: large outputs, long files, repeated reads, fan-out planning. Route bulk to subagents; keep summaries in the main thread, not raw payloads.

**Why:** Context overflow degrades reasoning quality, creates compression artifacts, and halts progress.

**Pattern:**
- **Size phases and cap scope.** Limit files per phase, set turn budgets, account for mechanism costs.

<!-- card: Keep moving with nobody watching | 5 | Route bulk to subagents and keep summaries, not raw payloads, in the main thread. | `investigation`; `swarm`; `orchestrate` -->
