# The skill listing of a mirror

A mirror is the home the launched roles run on, and the user's own sessions run on `~/.claude`.
So a thread on a mirror lists the user's skills and the repo's, and no skill of a plugin, of Claude Code itself or of the claude.ai account.
Each is a setting, and `jroles mirror` writes the mirror's `settings.json` as `~/.claude/settings.json` with these settings changed:

| Skills | Setting in the mirror |
| --- | --- |
| Each plugin's | `enabledPlugins`: every plugin `~/.claude` enables is `false` |
| Claude Code's bundled ones | `disableBundledSkills: true`, and `skillOverrides` turns `plugin-authoring` `off`, the one it leaves listed |
| The claude.ai account's, synced under `~/.claude/skills/synced/<login>/<name>` | `skillOverrides` turns each `anthropic-skills:<name>` `off` |

The mirror's other `skillOverrides` and every other key are `~/.claude`'s.
`plugins` and `skills` stay links, so a thread can still read a plugin's or an account skill's `SKILL.md` by its path.
A plugin you enable later, or an account skill Claude Code syncs later, is off in the mirror from the next run on, and `--check` prints `would write <home>/settings.json as ~/.claude/settings.json, trimmed` until then.
A change written to the mirror's `settings.json`, a copy the home held before it was a mirror included, lasts until the next run, which writes it from `~/.claude`'s again and keeps no backup of it: change `~/.claude/settings.json` instead.
A mirror copy that is not valid JSON is written again on the next run, like any other copy that differs.
