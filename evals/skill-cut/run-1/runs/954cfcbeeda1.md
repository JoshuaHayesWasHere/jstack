I don't run the suite. Under **Research**, a scout's calls only read, and "if a question needs such a run to answer, say so in the report and leave the run to a crewmate." A test run starts processes and writes caches and build output.

First I find, read-only, the exact command the repo uses: the README, the CI config, the `package.json` or `Makefile` scripts. I also note the places I checked that gave no recent number (docs, logs, `git log`) as ruled out.

Then, under **Write it down**, I add this to the report's Findings: `Q<n> (suite duration): not answered. It needs a test run, which a scout may not do. To answer: a crewmate runs \`time <the repo's test command>\` in a clean worktree on this machine. Ruled out: docs, CI logs, git history, none of which has a recent number.`

If a brief is asked for, I put that timed run in its "Done when" list. It is not a gate, because the user can't answer it either, and I can't run anything here.
