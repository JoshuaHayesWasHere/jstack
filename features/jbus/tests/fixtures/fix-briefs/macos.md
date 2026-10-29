# macos-red-2026-10-12: the macOS suite failed on 2026-10-12
Task: "the macOS nightly run 77 failed on 2026-10-12, 0 tests named" (jbus, from macos-nightly.yml)
Done when:
- each failed test named under Read passes on macOS, in a manual run of macos-nightly.yml with `ref` set to the fix's branch
- the Result names the cause: the merge that broke it, or a flake with its evidence
Proves it: `make check-fast BASE=origin/main` passes, and so does a manual run of macos-nightly.yml (`gh workflow run macos-nightly.yml -f ref=<the fix's branch>`)
Size: S
Where: the tests the macOS nightly runs on main, under `features/` and `testing/`
Do not touch: .github/workflows/, the ruleset
Decisions: none, jbus filed this from a red nightly run and the user has not seen it
Design: none, a fix to what the failed run names
Pull request: open one when done
Review: review
Playbook: bug-fix
Home: macos
Read:
- the job `macos`, https://example.test/o/r/actions/runs/77/job/712: its log names no failed test, read it
- the run https://example.test/o/r/actions/runs/77, from schedule, at cccccccccccccccccccccccccccccccccccccccc
Thread: mcp:thread-1
