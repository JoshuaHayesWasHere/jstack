# make-check-runner-flip: what changes for `make check` when it moves to GitHub's runners
Task: "figure out what is slowing down make check and why"
Done when:
- A written answer covers only the runner flip: each part of `make check` whose speed or behavior differs on GitHub-hosted runners compared with this machine
- For each difference, the answer names the cause, such as cores, disk, caching, network fetches, tool installs or parallelism, and gives the evidence for it (a measurement, a log line, or a doc reference)
- Each point says whether it adds to the slowdown, removes part of it, or leaves it unchanged
- Anything that could not be confirmed without a run on GitHub is listed as open, not guessed
Where: the `check` target in the `Makefile` and everything it calls, `.github/workflows/`, and any setup or caching steps those workflows run
Do not touch: the other half of the task, which is what slows `make check` on this machine (a separate brief covers it). Do not edit the `Makefile`, the workflows or the tests. Do not push, and do not start runs on GitHub without asking first.
Decisions: none
Design: none, it is an investigation that ends in a written answer, not a change to build
Pull request: ask first
Review: none
Playbook: none
