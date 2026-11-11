# Fixtures

`findings/two-reviewers.md` is written by hand for `features/jbriefs/tests/test_jbriefs_findings.py`, after the brief of dual-reviewer (pull request 129), whose review was by one reviewer: a brief two reviewers reviewed at one head, in the shape `templates/review.md` gives since the buckets.
Both name one place in `src/jmerge/ready.py`, which is one finding, and one dismisses what the other raised, which is printed beside it.
`uv run jbriefs --findings features/jbriefs/tests/fixtures/findings/two-reviewers.md` shows the list.

`propose_replay.json` is the replay corpus of `features/jbriefs/tests/test_propose.py::test_replay`: 30 `Done when:` items of merged rows, each with its row's slug, its pull request, the commit that merged it on main, its brief's `Where:` line, and the check `jbriefs --propose` gave it when the corpus was made.
It was made by a fixed rule, not by hand: walk the merged rows of jstack's queue from the newest pull request down, propose for each item of each stored brief that runs nothing, run each `grep` and `test` proposal at the merge and at its parent, and keep the first 30 that exit 0 at the merge and not 0 at the parent.
On 2026-11-04 that tried 1101 proposals: 30 of 476 grep proposals and none of 625 test proposals passed, since a test proposal names a test the crew is still to write.

`result_lines/` holds the six briefs of `features/jbriefs/tests/test_result_lines.py`, the ones on which the st-implicit-pkgs scout found the Python and the skills' awk reading a Result line differently.
Five are copies of jstack's own briefs as they stood on 2026-11-11, with each thread id made `mcp:thread-<n>` and each home path made `~/`.
`qw-lock-test-race.md` is cut from a private repo's brief to the lines the readers read, with its pull request's address made `https://github.com/example/private/pull/255`.
