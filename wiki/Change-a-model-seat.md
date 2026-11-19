Use this guide to change which model a skill uses for a role, such as an arena runner or a council member.

1. Open `~/repos/jstack/docs/models.md`.
2. Find the line for the role. For example:

	```
	council: antigravity/gemini-4-neon high, codex/gpt-6.2-sol high, claude/claude-sonnet-5-5 high
	```

3. Change the value. Each entry is `<provider>/<model> <effort>`.
	- The provider is a T3 Code provider instance: `claude`, `codex`, `cursor`, or `antigravity`.
	- To list the models a provider offers, ask an agent in T3 Code to call `orchestrator_capabilities`.
	- Keep the effort at `xhigh` or below. Gemini 4 Carbon through `cursor/` goes up to `high`.
4. To fall back to the skill's default, delete the line.
5. Commit and push. The next session reads the new value.

For every role and its default, see [[Models and seats]].
