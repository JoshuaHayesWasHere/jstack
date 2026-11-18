Use this guide to add your own skill to jstack so every agent gets it.

1. Create the folder. Use a short kebab-case name:

	```sh
	mkdir ~/repos/jstack/skills/my-skill
	```

2. Write `~/repos/jstack/skills/my-skill/SKILL.md`. Start it with frontmatter:

	```markdown
	---
	name: my-skill
	description: What the skill does, and the phrases that should start it.
	---
	```

	- To make the skill run only when you type `/my-skill`, add `disable-model-invocation: true`.
	- To get help writing it, ask the agent for the "authoring a skill" playbook. It uses `anthropic-skills:skill-creator` in Claude Code, `skill-creator` in Codex, and `create-skill` in Cursor.

3. Link the skill into every harness:

	```sh
	~/repos/jstack/install
	```

	The installer prints `linked` twice, once for `~/.claude/skills/my-skill` and once for `~/.agents/skills/my-skill`.

4. Start a new agent session and check that the skill loads.

5. Add the skill to its group on the [[Skills]] page in the wiki. Then commit and push.
