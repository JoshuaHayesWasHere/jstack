`docs/models.md` assigns a model to each role that a skill fills with a subagent. Edit it by hand. See [[Change a model seat]].

## Value format

Each value is `<provider>/<model> <effort>`.

- The provider is a T3 Code provider instance: `claude`, `codex`, or `cursor`.
- `inherit-parent` runs the role on the model of the chat that started it.
- No role runs above `xhigh`. Gemini models go up to `high`.

## How a seat runs

1. If the seat's provider matches the tool you are in, the skill starts a native subagent. A `claude/` seat runs natively in Claude Code, a `codex/` seat in Codex, and a `cursor/` seat in Cursor.
2. Otherwise, in T3 Code, the skill starts the seat with `delegate_task`.
3. Outside T3 Code, the seat runs on the current model, and the skill says so.
4. If a model is rejected, the skill uses the nearest model of the same family or drops the seat. A panel keeps at least two seats.

## Roles

| Role | Default | Used by |
| --- | --- | --- |
| `feature, refactoring` | `claude/claude-opus-5-5 xhigh` | Feature and Refactoring playbooks |
| `bug-fix` | `claude/claude-opus-5-5 xhigh` | Bug fix playbook |
| `perf-issue` | `claude/claude-opus-5-5 xhigh` | Perf issue playbook |
| `hillclimb` | `claude/claude-opus-5-5 xhigh` | Hillclimb playbook |
| `judgment and prose` | `claude/claude-opus-5-5 xhigh` | Writing and judgment calls |
| `arena runners` | Fable 5.2 high, Opus 5.5 high, Gemini 4 Carbon high | `arena`, `eval` |
| `arena cross-judge pool` | Gemini 4 Carbon high, GPT-6.1 Sol high, Opus 5.5 high | `arena` judge |
| `swarm workers` | `claude/claude-opus-5-5 high` | `swarm`, verification, trivial edits |
| `interrogate reviewers` | Fable 5.2 high, Opus 5.5 high, Gemini 4 Carbon high | `interrogate` |
| `council` | Opus 5.5 xhigh, GPT-6.1 Sol xhigh, Gemini 4 Carbon high | `council` |
| `sol-loop reviewer` | `codex/gpt-6.1-sol xhigh` | `sol-loop` |

The arena judge never comes from the same vendor as the chat that started it. Fable counts as Claude for that rule.

## Choosing effort

Skills start from the role's effort, then adjust it. They raise it one step for the hardest work and lower it for routine work. Fable 5.2 runs outside a panel only when you name it, or after two Opus 5.5 runs of the same task fail their check. The full rules are in `docs/subagents.md`.
