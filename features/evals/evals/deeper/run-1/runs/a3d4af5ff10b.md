# thread-cap-by-load: Replace the fixed thread cap with a limit set by real machine load and past runs

Task: "I was just warned that I hit an arbitrary thread limit despite being at 3.5 of 12 cores used address this, I want to push my machine as hard as I can without going over the edge" and "is the cap relevant? Can we go higher based off the past runs we've done?"
Done when:
- The brief's author finds the code that issues the thread-limit warning and the fixed cap behind it, and records both by path and line in the PR.
- Past run records (logs, run history, telemetry) are read for peak CPU, memory and thread counts. The PR states what they show and whether the old cap was ever the real constraint.
- The cap is raised or replaced with a limit computed from the machine's cores and memory, the live load, and a stated safety margin. The margin and its basis are written in the PR.
- At about 3.5 of 12 cores in use, starting another thread no longer triggers the warning or a block.
- A guard still refuses or queues new threads when CPU or memory gets near the margin, and a test covers this case.
- The existing tests pass, and the new tests cover both the computed limit and the guard.

Where: the code that counts or caps concurrent threads (home, scouts, crewmates, reviewers) and emits the limit warning; any config or defaults that set the cap; the past run logs and history used to justify the new limit.
Do not touch: unrelated skills and playbooks. Do not delete or rewrite past run records; only read them.
Decisions: "I want to push my machine as hard as I can without going over the edge"
Design: none, this retunes one existing limit and its guard, with no new component or interface
Pull request: open one when done
Review: review
Playbook: none
