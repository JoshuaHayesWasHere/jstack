# main-red-dddddddddddd: main's check failed at dddddddddddd, after alpha merged
Task: "main check failed at dddddddddddd, 1 merges since the last green" (jbus, the retro of alpha). jbus reverts nothing: jbus reverted this row before, and a row is never reverted twice
Done when:
- each failed test named under Read passes on main, and the failed job passes at the commit that merges the fix
- the Result names the cause: the merge that broke main, or a flake with its evidence
- the fix is in a pull request of its own, or in another open pull request only where that one waits on no other open pull request: no `merge_after` row still open (jmerge's `merges after` or `carries ... which merges after`) and not stacked on an open base (`it is stacked on`); otherwise the crew opens its own pull request with the fix, and whichever of the two merges second rebases
Proves it: CI's check on main passes at the commit that merges the fix
Size: S
Where: `src/alpha/a.py`, `tests/test_a.py`, `tests/test_b.py`
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red main and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one when done
Review: review
Playbook: bug-fix
Home: root
Follows: alpha
Read:
- the job `full`, https://example.test/o/r/actions/runs/77/job/901: `tests/test_a.py::test_one`, `tests/test_b.py::test_two[x]`
- the merge dddddddddddd feat: alpha (#7)
