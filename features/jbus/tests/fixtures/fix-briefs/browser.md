# browser-red-2026-10-12: the browser tests failed on 2026-10-12
Task: "the browser run 88 failed on 2026-10-12, 1 test named" (jbus, from browser.yml)
Done when:
- each failed test named under Read passes under `make check-browser`
- the Result names the cause: the merge that broke it, or a flake with its evidence
Proves it: `make check-browser` passes, and so does a manual run of browser.yml (workflow_dispatch) on the fix's branch
Size: S
Where: `tests/test_jbus_view_page.py`
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red nightly run and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one when done
Review: review
Playbook: bug-fix
Home: root
Read:
- the job `browser`, https://example.test/o/r/actions/runs/88/job/911: `tests/test_jbus_view_page.py::test_one`
- the run https://example.test/o/r/actions/runs/88, from schedule, at cccccccccccccccccccccccccccccccccccccccc
