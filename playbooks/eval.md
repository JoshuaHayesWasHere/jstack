# Eval

Run by: a crewmate, for finding out whether a variant a model reaches by reading files (a playbook, a principle, a doc) changes what it does, in a brief with `Candidates:`, `Judge:` and `Pull request: ask first`.

Source: pstack, `pstack/skills/poteto-mode/playbooks/eval.md`

<!-- card: Decide by building | 3 | Finding out whether a variant a model reaches by reading files (a playbook, a principle, a doc) changes what it does. | plain: `Candidates:`; plain: `Judge:`; plain: `Pull request: ask first` -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the design of the experiment.** A candidate must not learn it is measured, nor the judge which model or set wrote what. Both are subagents, gone when they return: you keep the rubric, the key, the outputs and the verdict. Never more than ten subagents in one step.

1. Frame it, for yourself and the judge only: the variant under test, what counts as success, and a rubric of three to six criteria, each marked as one the files can show (the judge's) or one only a transcript can (yours). The candidates are the Claude models on the brief's `Candidates:` line and the judge the model on its `Judge:` line, a different one, all at medium effort. Against its absence, the variant has two sets, and one judge scores both in one pass, on one scale.
2. Build the skeleton, one directory per set: what a real task has around it, the variant where a user would keep it. Give each candidate its own copy (`principles/principle-separate-before-serializing-shared-state.md`), once per set, `key` kept from the first run:

   ```sh
   name=<a name a user would give the project>
   skeleton=<the set's directory>
   key=${key:-$(mktemp -d)/key.tsv}
   for model in <each model on the brief's Candidates line>; do
       d=$(mktemp -d "/tmp/$name.XXXXXX")
       cp -R "$skeleton/." "$d"
       printf '%s\t%s\t%s\n' "$d" "$model" "$skeleton" >> "$key"
   done
   echo "key=$key"
   ```

3. Write one prompt, as a user would type it: the goal, not what is measured. It names no other candidate and asks for notes, never which files were used. Save it beside the key, then see this print nothing:

   ```sh
   grep -rniwE 'eval|judge|experiment|rubric|score|compare|benchmark|candidate|arena' <the prompt's file> <each skeleton>
   ```

   A hit in the project's own content is no leak: one in the prompt, or in a name you gave, is.
4. Start the candidates, ten to a message, with `Agent`: `subagent_type` is `general-purpose`, `model` is its row of the key, `effort` is `medium`, `run_in_background` is false. Each gets the same prompt and its own directory, nothing else. Wait inside this turn. Say a dropout, replace none.
5. Read what each candidate did from its transcript, not from what it says (`principles/principle-prove-it-works.md`). Run the block under "1. Find the transcript" in `skills/reflect/SKILL.md` as it is: it prints this thread's file. The candidates' are in `<that file without .jsonl>/subagents/`: `grep -l <its directory> <there>/*.jsonl` finds each. Run the block under "2. Make the digest" there with `F` set to each, and write per candidate which files it opened and in what order it acted. One that never opened the variant was not under it: do not count it. A command the digest cut at 300 characters is read in the transcript, at its turn's line. Open no other file under `~/.claude/projects/`.
6. Read every output yourself, end to end, and write a score per criterion before the judge starts: you are not blind, and a written score is one the judge's cannot move.
7. Blind, then judge. Copy each directory to `<a new directory>/<the six characters after its last dot>` and take out of every copy the variant's files and what a run left behind, so none shows its set. See this name no file a candidate wrote:

   ```sh
   grep -rliwE 'claude|opus|sonnet|haiku|fable' <the new directory>
   ```

   Then start one `Explore` agent, `model` from the brief's `Judge:` line, `effort` `medium`. It gets the task as the candidates got it, the criteria the files can show, and the copies by label, never the key, a model's name or a set's.
8. Synthesize. Put a model and a set on each label from the key, and set the judge's scores beside yours: where they differ, read the output again. One candidate per model and set is one sample: say so (`principles/principle-explain-the-number.md`).
9. End as `skills/crew/SKILL.md` "End" says for a task with no pull request. The directories and the key stay, named in the Result.

Never done here, and who does it:

- **Promoting the variant.** A crewmate does, from a new brief the home plans.
- **An eleventh subagent in a step, or one that has to remember.** Nobody does. Work that must outlast the step is a thread the home launches: a line under "Noticed".
- **A model the brief does not name, or an effort above medium.** Nobody does. With no `Candidates:` line it is this session's model, with no `Judge:` line a Claude model no candidate ran on, and a line under "Noticed".
- **A copy of the blocks of `skills/reflect/SKILL.md`, or a change to them.** Nobody does.

**Hand over:** in the Result, to the home: the variant, the rubric, a note per candidate with its chain, the judge's verdict and where it differed from yours, and whether to promote the variant.
