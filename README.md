# jstack

Private Claude Code config for this machine. `~/.claude` is the hub; the other
profiles (`~/.claude_prime`, `~/.claude_agent`) link to it.

| Here | Linked as |
|---|---|
| `settings.json` | `~/.claude/settings.json` (and the profiles' `settings.json` link to that) |
| `skills/<name>/` | `~/.claude/skills/<name>` (personal skills, one link each) |

`CLAUDE.md` and `statusline.sh` stay in the public dotfiles repo
(`~/dotfiles/claude/`), which links them into `~/.claude` itself.

Skills synced from claude.ai land in `~/.claude/skills/synced/` and are
re-downloaded, so turn them off with `skillOverrides` in `settings.json`
rather than deleting them.

## New machine

```sh
gh repo clone jstack ~/repos/jstack
ln -sfn ~/repos/jstack/settings.json ~/.claude/settings.json
for p in ~/.claude_prime ~/.claude_agent; do ln -sfn ~/.claude/settings.json "$p/settings.json"; done
```
