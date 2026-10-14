# Authoring or changing a skill

Run by: a crewmate, for writing or editing a `SKILL.md` or a template a skill reads.

Source: pstack, `pstack/skills/poteto-mode/playbooks/authoring-a-skill.md`

<!-- card: Work on jstack itself | 2 | Writing or editing a `SKILL.md`, or a template a skill reads. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the skill's voice.** Its reader is an agent that follows it to the letter, in a thread that has read nothing else.

1. Read the skill as it is on disk, every file it names, and the skills whose threads it hands to or hears from. A change to one side of a handover is checked against the other side.
2. Write the change. When in doubt, delete. Keep only prose that changes a decision. Tell the reader to do the thing and skip the reason, and explain only where the rule confuses without one. Match the tone to the scope. A rule you are about to write a second time belongs in something that runs, a shell block, a check or a test, and not in more text (`principles/encode-lessons-in-structure.md`). Point at the one place a fact lives (a template, a config file, another skill by its path) and do not restate it.
3. Validate the skill by running what can be run (`principles/prove-it-works.md`): the frontmatter has `name` and `description`; the name is not a built-in command's; every file it names exists; every link to another skill resolves; every shell block runs in a throwaway repo and prints what the text says it prints. In a shell block a positional is written `${1}` in sh and `$(2)` in awk, since loading a skill replaces the bare forms.
4. Test what is structural. A test executes something: it runs the block the skill tells an agent to run, or parses a command or JSON block out of the skill and checks it against the real tool (`principles/test-behavior-not-implementation.md`). A test that only finds sentences in the skill is not one. A change that is wording alone gets no test: say so in the Result. Show each new test red once, with a break made and undone before the commit.
5. Run `playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **Reaching running threads.** Nobody does: a thread keeps the skill text it loaded, so the change is read by threads started after the merge. Say in the Result if a thread now out depends on it.
- **Installing the skill.** The user does: a new skill needs a link from where skills are loaded, outside the repo. Name the link in the Result for the user to make.
- **Adding the next skill.** The home plans it: a workflow you keep meeting that no skill covers is a line under "Noticed".

**Hand over:** in the pull request and the Result, to the reviewer and the home: what the skill does now, the design decisions that matter, and what you ran to validate it.
