# main-red-<sha12>: main's check failed at <sha12>, with no briefed merge in the day before it
Task: "main check failed at <sha12>, 1 merges since the last green" (jbus, the retro of main's tip)
Done when:
- each failed test named under Read passes on main, and the failed job passes at the commit that merges the fix
- the Result names the cause: the merge that broke main, or a flake with its evidence
Proves it: CI's check on main passes at the commit that merges the fix
Size: S
Where: `.` (the whole repo: the merges since the last green changed files nobody listed)
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red main and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one when done
Review: review
Playbook: bug-fix
Home: root
Read:
- the job `check`, with no URL: its log names no failed test, read it
- the merge <sha12> chore: a hand merge
