# jstack

Private Claude Code config and the skill set every agent on this machine
shares: Claude Code (all three profiles), Codex, and Cursor. Skills come from
[pstack](https://github.com/cursor/plugins/tree/main/pstack) and
[tstack](https://github.com/t3dotgg/tstack); see [UPSTREAM.md](UPSTREAM.md).

## Skills

Skills live flat in `skills/<name>/`, because they open each other by
relative path. The groups below are how to think about them.

Most pstack skills run only when you type them (`/how`, `/arena`). The tstack
skills also fire when you say their phrase ("full send", "babysit").

### Researching

| Skill | Use it when |
| --- | --- |
| `/sharpen` | You want a prompt made deeper, not bigger, before you send it. |
| `/how` | You want a walkthrough of how a subsystem works. |
| `/why` | You want to know why something was built this way, from the commits and PR record. |
| `/swarm` | You want N parallel workers across slices, then one report. |
| `/arena` | You want N parallel attempts at one task, then the best parts of each. |

### Prototyping

| Skill | Use it when |
| --- | --- |
| `prototype` | Explore a vague or open request on throwaway `proto/` branches, try several routes, and report back with evidence. Never opens a PR. |
| `/in-your-own-words` | You want the agent to play back your goal and the problem before it starts. |
| `/architect` | You're about to cross a function boundary and want the caller's usage, types, and module shape settled first. |

### Building

**prototype**, **full-stop**, and **full-send** are jstack's three modes. Each reads [`docs/rules.md`](docs/rules.md) first (pstack's poteto-mode rules and principles index) and runs the playbooks that fit it.

| Skill | Use it when |
| --- | --- |
| `full-send` | Take a change all the way to a merged PR, unattended. Runs a playbook, proves it, sol-loop review, files, babysits, merges. |
| `full-stop` | Same as full-send, but stop with the PR ready for you to merge. |
| `file-pr` | Open a short PR that leads with the problem. |
| `babysit-pr` | Watch a PR through CI and review bots and fix real findings. |
| `leaving-pr-comments` | Automatic. Formats comments an agent posts for you. |
| `/tdd` | Fix a bug with a cheap local test path: failing test first. |

### Utility

| Skill | Use it when |
| --- | --- |
| `/reflect` | A long task landed and you want the recipe captured as a skill edit. |
| `/correct` | You keep correcting agents for the same mistakes. |
| `/teach` | You want to actually understand a change or subsystem. |
| `/no-comments` | Strip comments before review (runs the `comment-sicko` agent). |
| `/statechart` | Someone needs to see a behavior as a checked statechart, not a spec. |
| `/ketchup` | Catch up on what changed in this chat since your last message. |
| `/recall` | Rebuild your recent context on a topic from your chat history. |
| `/unslop` | Remove AI tells from writing. |
| `/bro` | Restate the last message in plain words. |

### Agent driven

| Skill | Use it when |
| --- | --- |
| Playbooks | `playbooks/`: 16 step lists the modes follow. **prototype**: investigation, prototype, runtime and trace forensics, eval, multi-phase plan. **full-stop** and **full-send**: bug fix, feature, refactoring, perf, hillclimb, visual parity, authoring a skill. Any mode: session pickup, pause safely, worktree cleanup. |
| `/blast-radius` | A small-looking change: what else could it break? |
| `/show-me-your-work` | Keep a reviewable decision trail on long or unattended runs. |
| `principle-*` | 24 one-rule skills (laziness protocol, prove it works, fix root causes, and more) that other skills cite. |

### Verification and Validation

| Skill | Use it when |
| --- | --- |
| `/create-verification-skill` | Your project has no scripted way to prove app behavior. |
| `/maintain-verification-skill` | That verify skill's feature map has drifted from the app. |
| `/create-formal-verification-skill` | Tests can't reach the case that breaks a race, retry, or state machine. |
| `/maintain-formal-verification-skill` | Code your formal verification covers has changed. |
| `/technical-writing` | Docs, RFCs, READMEs, PR descriptions, commit messages. |
| `council` | Review from three models on three providers, looped until they agree. |
| `sol-loop` | Review with GPT Sol in a loop until both agents agree. |
| `/interrogate` | Different models try to break a diff; keep only findings a run proves. |
| `/benchmark-checklist` | Vet a measured number before you trust it. |

## Models and harnesses

- [`docs/models.md`](docs/models.md): which model fills each role and panel
  seat. Edit it by hand. Non-Claude seats run through T3 Code's
  `delegate_task`.
- [`docs/rules.md`](docs/rules.md): the modes' shared rules, principles
  index, and which playbooks each mode runs.
- [`docs/subagents.md`](docs/subagents.md): shared rules for spawning
  subagents, and the worker rules every subagent reads.
- [`scripts/worktree-audit.sh`](scripts/worktree-audit.sh): used by the
  worktree-cleanup playbook.
- [`docs/harness/`](docs/harness/): maps pstack's Cursor names to this
  install, Claude Code, and Codex.

## Install

```sh
./install            # link everything; safe to rerun
./install --dry-run  # show what would change
```

| Here | Linked as |
| --- | --- |
| `settings.json` | `~/.claude/settings.json`; the prime and agent profiles link to that |
| `skills/<name>/` | `~/.claude/skills/<name>` (Claude Code) and `~/.agents/skills/<name>` (Codex) |
| `agents/<name>.md` | `~/.claude/agents/<name>.md` and `~/.cursor/agents/<name>.md` |

Cursor reads both `~/.claude/skills` and `~/.agents/skills`. `CLAUDE.md` and
`statusline.sh` stay in the public dotfiles repo (`~/dotfiles/claude/`).

Skills synced from claude.ai land in `~/.claude/skills/synced/` and are
re-downloaded, so turn them off with `skillOverrides` in `settings.json`
rather than deleting them.
