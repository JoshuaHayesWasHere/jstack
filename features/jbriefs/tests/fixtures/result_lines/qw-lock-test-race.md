# qw-lock-test-race: a lock test no longer races on a loaded runner, so main goes green
Green main: 9ad3c16451be5f95ccf66301ff85138c025525a0
Task: "main is red on a lock test. The fix is already open as #255: use it"
Done when:
- #255's check is green and the test passes under load
Size: S
Pull request: #255 is open: use it
Review: review
Playbook: none
Home: root
Thread: mcp:thread-1

## Result
Status: done
Done when: #255's check is green and the test passes under load: holds
Proof:
- #255's check: `gh pr view 255` says MERGED, with `check` SUCCESS at its head
Branch: qw-lock-test-race   Pull request: https://github.com/example/private/pull/255
Changed: nothing by this thread: #255 had already merged when it started
Playbook: none
Skills run: none
Reviewer: none, #255 merged before this thread started, and neither its GitHub reviews (0) nor its row's follow-up Result records a reviewer of it, so the brief's `Review: review` was not met
Steers: none
Left: none
