# workflow-red-pstack-drift-cccccccccccc: pstack-drift.yml is red on main since 2026-10-12
Task: "pstack-drift.yml: 1 runs failed on main since 2026-10-12, 1 test named" (jbus, from .github/workflows/pstack-drift.yml)
Done when:
- each failed job named under Read passes in a run of pstack-drift.yml on main
- the Result names the cause: the merge that broke it, or a flake with its evidence
Proves it: `gh run list --workflow pstack-drift.yml --branch main` shows a run that passed after the fix merged, or the workflow is gone from main
Size: S
Where: `.github/workflows/pstack-drift.yml`, `tests/test_drift.py`
Do not touch: the ruleset
Decisions: none, jbus filed this from a red workflow on main and the user has not seen it
Design: none, a fix to what the red runs name
Pull request: open one when done
Review: review
Playbook: bug-fix
Read:
- the job `drift`, https://example.test/job/931: `tests/test_drift.py::test_pinned`
- the run https://example.test/o/r/actions/runs/300, from schedule, at cccccccccccccccccccccccccccccccccccccccc
