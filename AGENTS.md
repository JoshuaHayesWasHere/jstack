# jstack

The skills, hooks, playbooks and model seats every agent on this machine shares: Claude Code, Codex, Cursor and Antigravity. `./install` links them into each harness. This repo is public. The global `AGENTS.md` lives in `~/dotfiles/agents/`, not here.

## Commands

Tests, which stop at the first failure:

```sh
set -e; for t in tests/*.test.sh; do bash "$t"; done
```

| What | Command |
|---|---|
| See what install would change | `./install --dry-run` |
| Install (after a merge, from `~/repos/jstack` on `main`) | `./install` |
| Publish the wiki (after `wiki/` changes merge) | `scripts/publish-wiki` |

## A change to a skill is a change to five places

When you add, rename, regroup or remove a skill, or change which model a seat uses, update every one that applies in the same PR:

1. `skills/<name>/SKILL.md`, with `metadata.group` and `metadata.group-order` (`tests/skill-groups.test.sh` checks them).
2. The skills table in `README.md`.
3. `wiki/` (`Skills.md`, `Modes.md`, `Models-and-seats.md`, `Playbooks.md` as relevant).
4. `docs/models.md` for any seat change.
5. Every caller. Find them with `rg -n '<old-name>'` over the whole repo (skills, playbooks, docs, wiki, agents, hooks, tests, `README.md`, `UPSTREAM.md`) and say in the reply that you checked.

Then run the tests. `tests/skill-groups.test.sh` fails when the frontmatter and the README table disagree.

Skills open each other by relative path, so `skills/` stays flat.

## Rules

- Public repo. No private hostnames, email addresses, account names or machine-specific paths. The live `settings.json` is gitignored; mirror shareable settings into `settings.example.json` by hand.
- No em dashes in anything you write. The `no-em-dash` hook blocks commits, tags and `gh` bodies that carry one.
- Upstream skills come from pstack and tstack (`UPSTREAM.md`). Keep a skill's upstream name so later syncs line up.
- Commit subjects are one plain sentence saying what agents now do differently, for example `Full send and full stop review with neon-loop, and run council only on request`.

## Done means

End every task by saying: committed, pushed, merged, whether `./install` ran on the main checkout, and whether the wiki was published. Remove worktrees and branches you created once their work has merged.
