# workflow-red-release-aaaaaaaaaaaa: release.yml is red on main since 2026-10-12
Task: "release.yml: GitHub started no job in 8 runs on main since 2026-10-12" (jbus, from .github/workflows/release.yml)
Done when:
- GitHub runs a job of release.yml on main again: its file is one GitHub can read, or, where nothing needs the workflow, it is removed (it is a candidate for removal, and jbus removes no workflow)
- the Result says which, and why GitHub could not run the file
Proves it: `gh run list --workflow release.yml --branch main` shows a run that passed after the fix merged, or the workflow is gone from main
Size: S
Where: `.github/workflows/release.yml`
Do not touch: the ruleset
Decisions: none, jbus filed this from a red workflow on main and the user has not seen it
Design: none, a fix to what the red runs name
Pull request: open one when done
Review: review
Playbook: bug-fix
Read:
- the run https://example.test/o/r/actions/runs/107, from push, at hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh
- the run https://example.test/o/r/actions/runs/106, from push, at gggggggggggggggggggggggggggggggggggggggg
- the run https://example.test/o/r/actions/runs/105, from push, at ffffffffffffffffffffffffffffffffffffffff
- the run https://example.test/o/r/actions/runs/104, from push, at eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
- the run https://example.test/o/r/actions/runs/103, from push, at dddddddddddddddddddddddddddddddddddddddd
- the run https://example.test/o/r/actions/runs/102, from push, at cccccccccccccccccccccccccccccccccccccccc
- the run https://example.test/o/r/actions/runs/101, from push, at bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- the run https://example.test/o/r/actions/runs/100, from push, at aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Thread: mcp:thread-1
