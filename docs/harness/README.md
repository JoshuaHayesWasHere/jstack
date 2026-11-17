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
| **poteto-mode**, as the mode that runs playbooks | **full-send** or **full-stop** for work that ends in a PR. The **prototype** mode is planned and not built yet. Until then, follow the playbook directly. |
| A playbook, such as `session-pickup` or `bug-fix` | `<jstack>/playbooks/<title>.md`. Babysit, Shipping, and Opening a PR are not here. Use **babysit-pr**, **full-send**, and **file-pr**. |
| `subagent_type: "poteto-agent"` | A general subagent whose brief opens with `Read <jstack>/docs/harness/README.md and <jstack>/docs/subagents.md before anything else.` |
| `subagent_type: "comment-sicko"` | The `comment-sicko` agent, installed from `<jstack>/agents/comment-sicko.md`. |
| `/deslop`, `control-ui`, `control-cli`, or anything from `cursor-team-kit` | Not installed. Skip the step and say so in one line. |
| **automate-me**, **typescript-best-practices**, **figure-it-out**, **poteto-help** | Not installed. Skip the reference and say so in one line. |

## Models from other vendors

A model on another vendor (Gemini, GPT) runs through T3 Code: call
`orchestrator_capabilities` once, then `delegate_task` with the provider and
model from [`docs/models.md`](../models.md). Outside T3 Code, run that seat on
the session model and say so.
