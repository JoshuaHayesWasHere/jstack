# jstack harness map

Read this file once per session before you follow a skill from pstack. It maps
pstack names to this install. Then read the file for your harness:

- Claude Code: [claude-code.md](claude-code.md)
- Codex: [codex.md](codex.md)
- Cursor: no extra file. pstack skills already use Cursor names.

`<jstack>` is `~/repos/jstack`. Every skill lives flat in `<jstack>/skills/<name>/`.

## Names this install changes

| A skill says | In jstack |
| --- | --- |
| `<pstack>`, or a path under the pstack plugin | `<jstack>` |
| `~/.cursor/rules/pstack-models.mdc`, or `/setup-pstack` | [`<jstack>/docs/models.md`](../models.md). Read it before you pick a model. Edit it by hand to change a role. There is no setup skill. |
| The Subagents section of the **poteto-mode** skill | [`<jstack>/docs/subagents.md`](../subagents.md) |
| **poteto-mode**, as the mode that runs playbooks | One of jstack's three modes: **prototype** (explore on throwaway branches), **full-stop** (PR, never merged), or **full-send** (PR, merged). Their shared rules are [`<jstack>/docs/rules.md`](../rules.md). |
| A playbook, such as `session-pickup` or `bug-fix` | `<jstack>/playbooks/<title>.md`. [`rules.md`](../rules.md) says which mode runs it. Babysit, Shipping, and Opening a PR are not here: use **babysit-pr**, **full-send**, and **file-pr**. Autonomous run, Autopilot-full, and Autopilot-stack are folded into **full-send** and **full-stop**. |
| `subagent_type: "poteto-agent"`, or a brief that starts with `Read <path>/worker.md` | A general subagent whose brief opens with `Read <jstack>/docs/subagents.md before anything else.` |
| `subagent_type: "comment-sicko"` | The `comment-sicko` agent, installed from `<jstack>/agents/comment-sicko.md`. |
| `/deslop` | Not installed. Use **unslop** for prose and **no-comments** for code, and say so in one line. |
| `control-ui`, `control-cli`, or "the control skill" | The project's `verify-*` skill when it has one, otherwise the harness's browser, computer-use, or shell tools. |
| Cursor's `/loop` command | A watcher or timer: **babysit-pr**'s watcher, T3 Code's `watch_pull_request`, or the harness's scheduled wake-up. |
| Anything else from `cursor-team-kit` | Not installed. Skip the step and say so in one line. |
| **figure-it-out** | Write a short playbook of your own, as [`rules.md`](../rules.md) says. |
| **automate-me**, **typescript-best-practices**, **poteto-help** | Not installed. Skip the reference and say so in one line. |

## Models from other vendors

A model on another vendor (Gemini, GPT) runs through T3 Code: call
`orchestrator_capabilities` once, then `delegate_task` with the provider and
model from [`docs/models.md`](../models.md). Outside T3 Code, run that seat on
the session model and say so.
