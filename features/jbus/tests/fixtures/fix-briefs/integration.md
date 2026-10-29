# integration-red-release-demo-111111111111: release/demo's check failed at 111111111111
Task: "release/demo check failed at 111111111111, and jmerge holds #4, #5 on it" (jbus, from release/demo's tip)
Done when:
- each failed test named under Read passes on release/demo, and the failed job passes at the commit that merges the fix
- the Result names the cause: the merge that broke release/demo, or a flake with its evidence
Proves it: CI's check on release/demo passes at the commit that merges the fix
Size: S
Where: `.` (the whole repo: the failed check's log names no test, read it on release/demo)
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red integration branch and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one against release/demo when done
Review: review
Playbook: bug-fix
Home: releases
Follows: one
Read:
- the job `check`, with no URL: its log names no failed test, read it
