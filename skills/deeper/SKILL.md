---
name: deeper
description: "Use for /deeper. Given a task or a draft brief, asks for the deeper version of it, not a bigger one: what a top professional in the field would do that is not asked, the rawest material they would start from, the methods and tools they would use, and what outside the agent would show the result is right. Returns the four answers and the prompt rewritten to ask for exactly that."
tip: asks for the deeper version of a task, not a bigger one | go deeper | deeper version | more ambitious | what would an expert do
disable-model-invocation: true
card: "Settle the shape before code | 4 | Asks for the deeper version of a task, not a bigger one: what an expert would do, from what raw material, with which instruments, and what outside the agent proves it. Returns the four answers and the prompt rewritten. | Reach for it before a research, perf, analysis or outcome brief goes out. | op: the operator; plain: a home, before a brief"
---

# Deeper

Source: Felix Rieseberg, "How to be more ambitious: A tutorial for humans with models" (2026-10-13), the Depth type of his four types of ambition. `THIRD_PARTY.md` credits it.

The rule behind it is `principles/principle-depth-over-breadth.md`: in research, perf, analysis and outcome work, go one level deeper, not wider. It is not for a mechanical fix, a rename, or a task whose "Done when" already names its data, its instruments and its outside judge: say so in one line and stop.

To have the task sharpened and then done, with no rewrite handed back, use `/sharpen` (`skills/sharpen/SKILL.md`) in place of this.

## Input

What follows `/deeper`: the text of a task, or the path of a draft brief. For a path, read the file and take its `Task:` and `Done when:` lines as the task. Read only what the four answers need: the files the task names, and the data it would rest on, enough to name them by path, command or query. Do no part of the task itself.

## The four questions

These are Felix's words, and each answer is about this task, in this repo, on this machine:

> I want a deeper version of this task, not a bigger one. Before rewriting it: (1) say what a top professional in this field would do here that I'm not asking for; (2) name the rawest material they would start from instead of what has already been digested for me; (3) name the specific methods and tools they would use; (4) say what, other than you or me, would show the result is right. Then rewrite my prompt to ask for exactly that.

1. **What a top professional would do that is not asked.** Name the field first (a performance engineer, a statistician, a release manager), then the one or two things they would insist on. Deeper, not wider: a step that goes under the task, never a second task beside it.
2. **The rawest material.** The data before anybody summarised it: logs, transcripts, traces, a profile, the database, the CI run's own log, the counters of the machine, the user's own words. Name each by its path, command or query, and say what digested form it replaces (a scout's summary, a note, a remembered number).
3. **The methods and tools.** The instruments the best in the field use, by name and with the command that runs them here (`py-spy record`, `pytest --durations`, `hyperfine`, `perf stat`, `pidstat`, `git bisect`, `sqlite3`), and the method they serve (a profile before a fix, a bisect over a guess, a run count and a spread for a number). An instrument this machine lacks is named with how to get it.
4. **What outside the agent shows it is right.** A judge that is neither the agent nor the user's trust in it: a test that fails before and passes after, a measured number against a stated target, a dataset it predicts, an external tool's verdict, the user's own check. A reviewer of the same model, "the crewmate confirms", or a self-assessment is not one. Ask for an unreasonable target and say it is reasonable where the field would (Felix: "ask for 200ms").

## Output

Print exactly this, filled in, and nothing after it. The rewritten prompt is the block quote under its heading, every line of it starting `> `:

```markdown
## 1. What a top professional would do
<the field, then one to three lines>

## 2. The rawest material
- <the material, by path, command or query>: in place of <the digested form>

## 3. The methods and tools
- <the tool, with the command that runs it here>: <the method it serves>

## 4. What outside the agent shows it is right
- <the judge, and what it must say for the task to be done>

## Rewritten prompt
> <the task, rewritten to ask for exactly the four answers: the user's own words first, in
> quotes, then the material to start from, the instruments to use, and the outside judge as
> its proof>
```

The rewritten prompt keeps the user's goal and scope. It adds depth to them, never a new deliverable: what it adds is where to start, what to measure with, and what decides that it is done. In a brief, answer 2 is what to read first, answer 3 is how the work is done, and answer 4 is its proof.

## Run by a home

Typed by the user, the skill ends at its output. Run by a home on a brief it is writing, it does not block: the home takes the rewritten prompt as the default, writes the brief from it, and parks the choice as a gate for the user with the two options, then carries on. Run this with `<slug>` in place of the brief's slug in the four places it stands, and with the lines in angle brackets filled in:

```sh
gate=$(cat << 'THE_GATE_ENDS_HERE'
## Gate <n>: <slug>: keep the task as written, or take the deeper rewrite of it?
Status: open
Asked by: <slug>, thread <the home's thread id>
Default: the brief is written from the rewrite /deeper gave
Built on it: the brief tasks/<slug>.md, and the crewmate launched on it
Undo: write the brief again from the task as written, and tell its crewmate what changed
Context: <the four answers of /deeper, on this one line, separated by semicolons>
Option: use the rewrite (default, recommended): the brief starts from <answer 2>, works with <answer 3>, and is proved by <answer 4>
Option: keep the original: the brief asks for the task as written, and the crewmate picks its own sources, tools and proof
THE_GATE_ENDS_HERE
)
if ! command -v jbus > /dev/null; then
    echo "not sent: jbus is not installed here, so put the gate's lines in the brief's Result under Noticed"
elif said=$(printf '%s\n' "$gate" | jbus gate '<slug>' 2>&1); then
    echo "sent to jbus: $said"
else
    echo "not sent: jbus said: $said"
fi
```

Leave `<n>` as it is: jbus numbers the question. On `not sent: jbus said`, mend the line it names and run it again. An answer that keeps the original comes back as a message from jbus, and the home writes the brief again from the task as written.
