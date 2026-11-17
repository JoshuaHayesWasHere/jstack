Use this guide to stop a skill that claude.ai syncs to Claude Code, such as `docs` or `pdf`.

Synced skills land in `~/.claude/skills/synced/`. Claude Code downloads them again on its next sync, so deleting the files does not last.

1. Open `~/repos/jstack/settings.json`.
2. Add the skill to `skillOverrides` with the value `"off"`. Use the `anthropic-skills:` prefix:

	```json
	"skillOverrides": {
		"anthropic-skills:pdf": "off"
	}
	```

3. Start a new session. The skill no longer appears in the session's skill list.
4. If the setting is worth sharing, copy it into `settings.example.json`, then commit and push. The live `settings.json` is not tracked.

To turn the skill back on, delete its line from `skillOverrides`.
