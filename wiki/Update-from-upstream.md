Use this guide to bring changes from pstack and tstack into jstack.

`UPSTREAM.md` records the commit that jstack copied from each source. It also lists every local change. Keep both current.

1. Clone each source into a scratch folder:

	```sh
	git clone https://github.com/cursor/plugins /tmp/up/plugins
	git clone https://github.com/t3dotgg/tstack /tmp/up/tstack
	```

2. List what changed since the recorded commit. Use the commit from `UPSTREAM.md`:

	```sh
	git -C /tmp/up/plugins diff <recorded-commit> HEAD --stat -- pstack/
	git -C /tmp/up/tstack diff <recorded-commit> HEAD --stat
	```

3. For each changed file that jstack also has, read the upstream diff. Port the change by hand. Keep the local changes that `UPSTREAM.md` lists.
4. If a skill was added upstream and you want it, copy it in. Add it to its group on the [[Skills]] page in the wiki and in the README's skill table, and give its frontmatter the group's `metadata.group` and `metadata.group-order` (see [[Add a skill]]).
5. Record the new commits in `UPSTREAM.md`.
6. Run `~/repos/jstack/install`, then commit and push.

Do not copy files over the jstack versions. Most pstack skills carry a jstack pointer line, and several carry adapted model and path rules.
