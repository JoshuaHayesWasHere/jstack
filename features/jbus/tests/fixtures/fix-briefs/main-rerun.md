# main-red-<sha12>: main's check failed at <sha12>, after alpha merged
Task: "main check failed at <sha12>, 1 merges since the last green" (jbus, the retro of alpha). jbus reverts nothing: jbus reverted this row before, and a row is never reverted twice
Why: while main's check is red jmerge merges no pull request, so every approved row waits on this fix, and each merge on a red main hides the next fault behind this one
Done when:
- each failed test named under Read passes on main, and the failed job passes at the commit that merges the fix
- the Result names the cause: the merge that broke main, or a flake with its evidence
- the fix is in a pull request of its own, or in another open pull request only where that one waits on no other open pull request: no `merge_after` row still open (jmerge's `merges after` or `carries ... which merges after`) and not stacked on an open base (`it is stacked on`); otherwise the crew opens its own pull request with the fix, and whichever of the two merges second rebases
Proves it: CI's check on main passes at the commit that merges the fix
Size: S
Where: `.` (the whole repo: the merges since the last green changed files nobody listed)
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red main and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one when done
Review: review
Playbook: bug-fix
Skills: tdd
Home: uncategorized
Follows: alpha
Read:
- the job `?`, with no URL: its log names no failed test, read it
- the push run `check` failed at its first attempt, https://example.test/o/r/actions/runs/501/attempts/1, and again when it ran again, https://example.test/o/r/actions/runs/501/attempts/2
- the merge <sha12> a change
