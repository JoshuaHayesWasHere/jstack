# Depth over Breadth

Apply when scoping research, perf, analysis or outcome work: before a brief goes out, and before you plan how to do one. Choose depth over extra scope. Go one level under the task to the data, the instruments and the judge a field-leading expert would use, instead of adding a second task beside it.

Ask for the deeper version of the task, not a bigger one. A bigger task covers more ground with the same digested inputs. A deeper one covers the same ground from the raw material, with the expert's own tools, and is proved right by something other than the agent.

**Why:** A summary, a remembered number or a scout's paraphrase is the conclusion of someone else's analysis, with its errors baked in. An agent that starts from it can only restate it. An agent that judges its own result agrees with itself. The raw data and an outside judge are where a finding that was not already known comes from.

- **Raw data over summaries.** Start from the logs, the transcripts, the traces, the profile, the database, the CI run's own log and the machine's counters, not from the note that describes them. Name each by its path, command or query. Try to reproduce a known number from the raw data before you build on it.
- **An expert's instruments over their words.** Use the tools the best in the field use (a profiler, a bisect, a benchmark harness with a run count and a spread, a query over the real table), not the vocabulary that describes them. Naming a method without the command that runs it here is still words.
- **An outside judge over self-assessment.** The proof is a test that fails before and passes after, a measured number against a stated target, a dataset the result predicts, an external tool's verdict, or the user's own check. Not "the crewmate confirms", and not a reviewer of the same model as the only judge. Set a target the field would call ambitious and say it is reasonable.
- **Deeper, not wider.** What depth adds is where to start, what to measure with and what decides it is done. A new deliverable is breadth: it goes under "Noticed" for the home to plan.

`/deeper` asks these as four questions of a task or a draft brief and rewrites the prompt to ask for the answers.

**Boundary:** not for mechanical fixes. A rename, a typo, a version bump, a moved file or a fix whose cause is already proven needs no expert's instruments: do it by the direct path ([Laziness Protocol](laziness-protocol.md)). Nor for a task whose "Done when" already names its data, its instruments and its outside judge.

Pairs with [Prove It Works](prove-it-works.md), which checks the real artifact once the work is done; [Explain the Number](explain-the-number.md), which asks what limits a measured number; [Build the Lever](build-the-lever.md), which turns the outside judge into a script anyone can rerun; and [Attack the Premise](attack-the-premise.md), which suspects the shared assumption when the deeper look contradicts it.

<!-- card: Prove it | 6 | In research, perf, analysis and outcome work, go deeper, not wider: raw data over summaries, the expert's instruments over their words, an outside judge over self-assessment. | `deeper`; `perf-issue`; `investigation` -->
