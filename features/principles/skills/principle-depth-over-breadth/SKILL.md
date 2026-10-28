---
name: principle-depth-over-breadth
description: "Apply when scoping research, perf, analysis or outcome work: before a brief goes out, and before you plan how to do one. Go one level under the task, to the data, the instruments and the judge a field-leading expert would use, instead of adding a second task beside it."
disable-model-invocation: true
---

# Depth over Breadth

Apply when scoping research, perf, analysis or outcome work: before a brief goes out, and before you plan how to do one. Go one level under the task, to the data, the instruments and the judge a field-leading expert would use, instead of adding a second task beside it.

A task can grow in two directions. It can grow wider: more ground, covered from the same digested inputs and judged by the agent that did the work. Or it can grow deeper: the same ground, covered from the raw material, with the tools the best in the field use, and proved by something other than the agent. Deeper work finds what was not already known. Wider work restates it at greater length.

The difference is where a new finding can come from. A summary, a remembered number or a scout's paraphrase is the conclusion of someone else's analysis, with its errors baked in. An agent that starts from it can only agree or disagree in words. And an agent that judges its own result agrees with itself, as does a reviewer of the same model when it is the only judge. What was not known enters through three doors only: raw data, an instrument that measures, and a judge that can say no.

Judge a plan or a draft brief by three questions:

- **Where does it start?** Each input is named by its path, command or query: the logs, the transcripts, the traces, the profile, the database, the CI run's own log, the machine's counters. An input that is a note describing one of these is a pointer: go to what it describes. Before building on a known number, reproduce it from the raw data. A number nobody can reproduce is a claim, not a starting point.
- **What does it measure with?** The instruments a field-leading expert would reach for: a profiler, a bisect, a benchmark harness with a run count and a spread, a query over the real table. A plan that names the method and not the command has the vocabulary and not the instrument.
- **What says it is done?** A test that fails before and passes after, a measured number against a stated target, a dataset the result predicts, an external tool's verdict, or the user's own check. When the answer is "the crewmate confirms", nothing outside the agent can disagree, so nothing is proved. Set a target the field would call ambitious and say it is reasonable.

Depth changes those three answers and nothing else.
A plan that answers them by adding a deliverable, such as a second report, another component or one more question beside the first, has gone wider.
That is breadth, however useful, and it is a row of its own, queued as `templates/a-fault-outside.md` says.
To tell the two apart, look at what is delivered: deeper work keeps the deliverable and changes where it starts, what it measures with and what judges it, and wider work adds a deliverable.

`/sharpen` asks these three of a task or a draft brief, after a first question on what a top professional would do that is not asked, and rewrites the prompt to ask for the answers.

It is not for mechanical work.
A rename, a typo, a version bump, a moved file or a fix whose cause is already proven has nothing under it for an expert's instruments to find: do it by the direct path, per the [Laziness Protocol](../principle-laziness-protocol/SKILL.md).
Nor is it for a task whose "Done when" already names its data, its instruments and its outside judge.
There the three questions are answered, and asking them again only delays the work.

It works with [Prove It Works](../principle-prove-it-works/SKILL.md), which checks the real artifact once the work is done; [Explain the Number](../principle-explain-the-number/SKILL.md), which asks what limits a measured number; [Build the Lever](../principle-build-the-lever/SKILL.md), which turns the outside judge into a script anyone can rerun; and [Attack the Premise](../principle-attack-the-premise/SKILL.md), which suspects the shared assumption when the deeper look contradicts it.

<!-- card: Prove it | 6 | In research, perf, analysis and outcome work, go deeper, not wider: raw data over summaries, the expert's instruments over their words, an outside judge over self-assessment. | `sharpen` -->
