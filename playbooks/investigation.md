# Investigation

Run by: a scout, for a read-only question, in a scout's request and never in a brief: how does X work, why was Y built this way, are we sure about Z, should we do X or Y.

Source: pstack, `pstack/skills/poteto-mode/playbooks/investigation.md`

<!-- card: A scout runs it | 1 | A read-only question: how does X work, why was Y built this way, are we sure about Z, should we do X or Y. | look: scout -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/scout/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the answer.** An investigation only reads. It ends in a cited explanation or a recommendation, never in a change to the code: `skills/scout/SKILL.md` "Research" says what a read is.

1. State the question as you read it, in one line, and what would count as an answer. If the scope is unclear, say which reading you took and go on: the home or the user can redirect.
2. For a "how" question, read the code and the docs yourself. For a narrow one (one module, one function) read it straight through. For a subsystem, split it into two to four angles and take them one at a time. A search too wide to hold goes to one Explore subagent, and you keep its conclusion, not its output (`principles/principle-guard-the-context-window.md`).
3. For a "why" question, build the code anchor first: the paths and line ranges, the key symbols, and the history, from `git blame -L <start>,<end> <file>`, `git log --follow -p -- <file>` and `gh pr view <number> --json title,body,comments,reviews` for each commit that matters. Then look in each other place the session can read: the issue tracker, the repo's docs, and the home's files the request names. A place you could not search, or that held nothing, is written down as such. The newest commit is not the reason by default: trace back.
4. Keep the evidence beside each finding: the command and what it printed, the path and line, the URL and the part that matters. Check it against the real thing and not a summary of it (`principles/principle-prove-it-works.md`). Start from the raw data (the logs, the transcripts, the table, the run's own output) and the tools an expert in the field would use, and go deeper on the question rather than wider beside it (`principles/principle-depth-over-breadth.md`). Keep three things apart: what you found, what you infer from it, and what you do not know. A number you report is one you can explain: what limits it, and that it measured what you think (`principles/principle-explain-the-number.md`).
5. Write the answer. An explanation goes: Overview, Key Concepts, How It Works, Where Things Live, Gotchas, dropping any that do not apply, at the level of an engineer new to the subsystem and not of annotated source. A choice between alternatives goes as a recommendation with a table of tradeoffs. For "are we sure?", give your real judgment with its reasons, and say so if the premise of the question is wrong.
6. Put it in the report as `skills/scout/SKILL.md` "Write it down" says, within its length, and finish as its "End" says.

Never done here, and who does it:

- **The change the answer points to.** A crewmate does it, from a brief, in a fresh thread. When the request asks for a brief, say in it which playbook the task is: `playbooks/bug-fix.md`, `playbooks/feature.md`, `playbooks/refactoring.md` or `playbooks/authoring-a-skill.md`.
- **A run that writes.** A question that needs one is not answered: the report says what run would answer it, and a crewmate makes it.
- **A pull request.** A scout commits nothing and opens none.

**Hand over:** in the report, to the home: the answer, each finding with what it rests on, what was ruled out and why, and one recommendation.
