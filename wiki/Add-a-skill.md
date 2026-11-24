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
	metadata:
	  group: Design
	  group-order: "4"
	---
	```

	- Set `group` and `group-order` to the skill's group and that group's place in the README's skill table, counting Modes as 1. T3 Code's `/` menu lists the skill under that heading.
	- To make the skill run only when you type `/my-skill`, add `disable-model-invocation: true`.
	- To get help writing it, ask the agent for the [authoring a skill](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/authoring-a-skill.md) playbook. It uses `anthropic-skills:skill-creator` in Claude Code, `skill-creator` in Codex, `create-skill` in Cursor, and `agy-customizations` in Antigravity.

3. Link the skill into every harness:

	```sh
	~/repos/jstack/install
	```

	The installer prints `linked` twice, once for `~/.claude/skills/my-skill` and once for `~/.agents/skills/my-skill`.

4. Start a new agent session and check that the skill loads.

5. Add the skill to its group on the [[Skills]] page in the wiki and in the README's skill table. Run `tests/skill-groups.test.sh` to check that its frontmatter matches the table. Then commit and push.
