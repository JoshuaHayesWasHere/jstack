# What each name on a brief's Skills: line leaves in the Result

A brief's `Skills:` line names skills and principles by pstack's names, so a name reads the same in Grok Bot and in T3: a skill is `skills/<name>/SKILL.md` and written `architect`,
a principle is `principles/principle-<name>.md` and written `principle-model-the-domain`.
A principle's name from before the prefix, `model-the-domain`, still resolves, and so do `arena` and `swarm`, pstack skills that jstack keeps as playbooks.
`src/jbriefs/skills.py` is the one resolver.
A name that is none of these is refused by `jbus queue add` and gated at the launch.

The crewmate or the scout reads each named file in full at its start, does what it says, and leaves one artifact for it under `Skills run:` in the Result or the Report: one item, `- <name>: <the artifact>`, its further lines indented by two spaces.
The lines below say what the artifact is.
A name with no line of its own takes the `default` line.
`jmerge` merges no pull request whose brief names a skill that the Results leave with no artifact, an empty one or a placeholder (`<...>`, `none`, `n/a`, `TBD`, `skip`), and the reviewer judges whether each artifact is the real one.

- in-your-own-words: the goal restated in your own words: what the user is after and the problem it solves
- sharpen: the sharpened spec: the real goal, the approach a top expert would take, and what the task over- or under-specifies
- architect: two or more candidate designs, what each costs, and why the pick
- principle-model-the-domain: the state or type map: the data shape chosen, its states or types, and what it makes impossible
- blast-radius: the affected surfaces beyond the diff, and the one fact the change is safe because of, with how far it was proven
- principle-prove-it-works: the command run on the real thing and what it printed
- default: what running it produced, in the form its file names, or a line on what it changed in the work
