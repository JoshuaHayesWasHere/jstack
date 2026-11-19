# jstack

Claude Code config and the skill set every agent on this machine
shares: Claude Code (all three profiles), Codex, Cursor, and Antigravity. Skills come from
[pstack](https://github.com/cursor/plugins/tree/main/pstack) and
[tstack](https://github.com/t3dotgg/tstack); see [UPSTREAM.md](UPSTREAM.md).

## Documentation

The [jstack wiki](https://github.com/JoshuaHayesWasHere/jstack/wiki) has a
tutorial, how-to guides, reference for every skill and mode, and the reasons
behind the design. Its source is [`wiki/`](wiki/). To publish changes, run
`scripts/publish-wiki`.

## Skills

Skills live flat in `skills/<name>/`, because they open each other by
relative path. jstack has three layers:

- **Modes**: `prototype`, `full-stop`, and `full-send` take a request from
  start to finish. Each reads [`docs/rules.md`](docs/rules.md) first.
- **Library**: `playbooks/` (step lists) and `principle-*` skills (one rule
  each). The modes read these, and you can ask for a playbook by name.
- **Skills**: the rest, grouped by the step of the work they serve. The
  [Skills page](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills)
  on the wiki lists each one with how it starts and where it came from.

| Group | Skills |
| --- | --- |
| [Understand](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#understand) | `how`, `why`, `teach`, `recall`, `ketchup` |
| [Triage](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#triage) | `tdd` |
| [Design](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#design) | `sharpen`, `in-your-own-words`, `architect`, `statechart` |
| [Hypothesize](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#hypothesize) | `swarm`, `arena` |
| [Prove](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#prove) | `blast-radius`, `benchmark-checklist`, `create-verification-skill`, `maintain-verification-skill`, `create-formal-verification-skill`, `maintain-formal-verification-skill` |
| [Review](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#review) | `sol-loop`, `council`, `interrogate`, `no-comments` |
| [Ship](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#ship) | `file-pr`, `babysit-pr`, `leaving-pr-comments`, `show-me-your-work` |
| [Write](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#write) | `technical-writing`, `unslop`, `bro` |
| [Learn](https://github.com/JoshuaHayesWasHere/jstack/wiki/Skills#learn) | `reflect`, `correct` |

Each `SKILL.md` names its group in `metadata.group` and `metadata.group-order`,
and T3 Code's `/` menu shows one heading per group in that order: Modes, the
groups above, then Principles. `tests/skill-groups.test.sh` checks the
frontmatter against this table.

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
  install, Claude Code, Codex, Cursor, and Antigravity.

## Install

```sh
./install            # link everything; safe to rerun
./install --dry-run  # show what would change
```

| Here | Linked as |
| --- | --- |
| `settings.json` (untracked, seeded from `settings.example.json`) | `~/.claude/settings.json`; the prime and agent profiles link to that |
| `skills/<name>/` | `~/.claude/skills/<name>` (Claude Code), `~/.agents/skills/<name>` (Codex), and `~/.gemini/config/skills/<name>` (Antigravity) |
| `agents/<name>.md` | `~/.claude/agents/<name>.md` and `~/.cursor/agents/<name>.md` |
| `hooks/<script>`, listed in `hooks/hooks.json` | Hook entries in `~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.cursor/hooks.json`, and `~/.gemini/config/hooks.json` |

The live `settings.json` is gitignored because it names private config paths.
`settings.example.json` is the published template. Mirror any setting worth
sharing into it by hand.

Cursor reads both `~/.claude/skills` and `~/.agents/skills`. Antigravity has
no custom agent folder that Claude Code's agent files fit, so
[`docs/harness/antigravity.md`](docs/harness/antigravity.md) briefs
`comment-sicko` by path, as Codex does. The global
`AGENTS.md` (linked as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`) and
`statusline.sh` stay in the public dotfiles repo.

### Hooks

`hooks/hooks.json` names each hook script and the event and matcher it runs on
in each harness. Install rewrites only the entries it owns (commands ending in
`hooks/<script> <harness>`, or Antigravity hooks named `jstack-<script>`), so
other hooks in those files are left alone. The
script gets the harness name as its argument and answers in that harness's
format. Cursor also runs hooks from `~/.claude/settings.json`, so the `claude`
entry steps aside when the payload comes from Cursor. Antigravity reads nothing
a `PostToolUse` hook prints, so its edit check runs at `PreToolUse` and refuses
the edit.

| Hook | What it does |
| --- | --- |
| `no-em-dash` | Blocks `git commit`, `git tag`, and `gh` commands that send an em dash, in their text or in a body file they read (`--body-file`, `-F body=@file`, `git commit -F`). Tells the agent to reword any em dash a file edit writes (Antigravity refuses the edit instead). `tests/no-em-dash.test.sh` covers it. |

Codex skips a hook nobody has trusted, without any warning, and that includes
every Codex thread in T3 Code. Install trusts its own hooks for you through
[`scripts/codex-trust-hooks.mjs`](scripts/codex-trust-hooks.mjs), which asks a
private `codex app-server` for each hook's hash, the same way Codex's `/hooks`
screen does. A changed entry in `hooks/hooks.json` needs trusting again, so rerun
install after editing it. Editing a hook script needs nothing.

Skills synced from claude.ai land in `~/.claude/skills/synced/` and are
re-downloaded, so turn them off with `skillOverrides` in `settings.json`
rather than deleting them.
