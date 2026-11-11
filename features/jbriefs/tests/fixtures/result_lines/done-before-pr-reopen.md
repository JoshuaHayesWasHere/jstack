# done-before-pr-reopen: the done-before-pr rule judges a row as it ends, and never reopens one already done
Green main: 2d2058022f123cae9c860196437f7626b57f6f89
Follows: done-before-pr

Task: #741 (done-before-pr, "a row whose brief asks for a pull request is not done while its Result names none") went live when jbus restarted at 2026-10-29 14:59 EDT, and its first pass, 18:59:50Z, moved 16 finished rows from done back to queued (transitions.jsonl, all at that second): browser-red-2026-10-27-2, browser-red-2026-10-27-3, stack-carry-fork, token-wakes-cooldown, simplify-one-hometree, cleanup-bot-feed, cleanup-fl-msg-review-notice, cleanup-fl-s11-shown-why, cleanup-jv-wait-reason, cleanup-mv-21-why, cleanup-mv-25-skill-library, cleanup-product-lands, cleanup-project-skills-at-install, cleanup-statechart-tmp-cleanup, nn-limit-carry-on, nn-scout-page-settle. Each ended rightly with no pull request: there was nothing to change (token-wakes-cooldown found #731 had already landed it). The T3 tree now shows them as "asks you". The root home held all 16 (`jbus queue hold`) so none relaunches. Fix the rule so it is judged once, on a row's move to done, and only refuses done when the row's branch has commits that are not on main (the real case: token-reload-by-role, a commit left unpushed); a Result with Pull request: none and no commits of its own is done. Then put the 16 rows back to done, with their held approvals as they were before 18:59:50Z, by the code path the fix adds or by `jbus done`, and say which.
Done when:
- a row already done is never moved back by a pass, shown by a test that loads a done row and runs a pass
- a row that ends with Pull request: none and no commits ahead of main is done; one with commits ahead and no pull request is not, both shown by tests
- the 16 rows above are done again in queue.json and none shows in `jbus queue show`
- `make check-fast BASE=origin/main` passes
Proves it: the tests, and `jbus queue show` after it lands listing none of the 16
Size: S
Where: `features/jbus/src/jbus/`, `features/jbus/tests/`
Do not touch: `~/.config/jbus`; the 16 rows' briefs
Design: none, it narrows one rule #741 added
Pull request: open one when done
Review: review
Playbook: bug-fix
Thread: mcp:thread-3

## Result
Status: done
Done when: a done row is never moved back by a pass, holds; Pull request: none with no commits of its own is done and one with commits ahead is not, holds; the 16 rows done again in queue.json and none in `jbus queue show`, holds for 14 once this lands, and the brief's finding is wrong for 2 (gate question 137); `make check-fast BASE=origin/main` passes, lint passes and the selected run hit the short lane's limit, so CI's check is the proof
Proof:
- done row not reopened: `test_a_done_row_whose_result_names_no_pull_request_its_brief_asks_for_is_not_reopened` loads a done row whose branch has a commit, runs two passes, and finds it still done with no transition; red at 468f15383 (it moved to running), green at 7358eff05afb78dfcbf0c1a085b7662eb7dd3a32
- no commits of its own is done: `test_a_done_result_naming_no_pull_request_with_no_commit_of_its_own_is_done[no branch|from main|from its base]`, red at 468f15383, green after; commits ahead is not done: `test_a_done_result_naming_no_pull_request_its_brief_asks_for_leaves_the_row_running` now makes a branch with one commit and still holds
- targeted: `pytest test_jbus_row_ends.py test_work.py test_jbus_resume.py test_jbus_archived.py` in the short lane, 116 passed
- the 16 rows: read-only on the live checkout, `watch.owes_pull` with this branch's code is false for 14 and true for stack-carry-fork (4 commits on neither main nor its start, Result says Pull request: pending) and simplify-one-hometree (2 commits, and main still has features~/HomeTreeDesign.tla, which they delete); `test_a_held_row_that_ended_with_no_commit_of_its_own_comes_back_to_done` shows a held row comes back to done and leaves `jbus queue show`
- the check: ruff check and ruff format pass on features/jbus; `make check-fast BASE=2d2058022f123cae9c860196437f7626b57f6f89` selected 261 test files and was stopped at the short lane's 120 s limit at 47%, with no failure before it stopped; CI's check on #748 is the proof
Branch: done-before-pr-reopen   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/748
Changed: `watch.owes_pull` owes nothing for a row the table had at done when the pass began (`Pass.done`), and otherwise only when `watch.own` finds a commit of the Result's branch on neither origin/main nor the branch's start point (the oldest line of its reflog), so a branch stacked on a squash-merged base counts none of the base's commits as its own.
Restore path: the code path the fix adds, not `jbus done` (that verb only queues a finding and never touches a row): the first pass after this lands derives done for the 14 rows with no commit of their own, held or not. Their approvals stay empty: `jbus queue hold` cleared approved and brief_sha, and only `jbus queue approve` with the user's evidence writes them back, which neither named path does; a done row needs no go. Their earlier gos are in items.jsonl ("row <slug> has a go: ...").
Playbook: features/crew/playbooks/bug-fix.md; 1 done: transitions.jsonl at 18:59:50Z, and the queue rows and branches read live; 2 done: four cases in test_jbus_row_ends.py, red for the intended reason; 3 done: the rule ran every pass on done rows, and a plain ahead-of-main test would also have kept the cleanup-* rows, since the repo squash-merges; 4 done; 5 done: the tests, and the rule run read-only on the live rows; 6 done: test commit 468f15383 before the fix; 7 done: #748
Skills run: none
Gate: question 137
Steers: none
Left: none
Checked: make check-fast BASE=2d2058022f123cae9c860196437f7626b57f6f89 exit 124 at 7358eff05afb78dfcbf0c1a085b7662eb7dd3a32
Reviewer: mcp:thread-10 #1

## Review
By: claudeAgent claude-sonnet-5-5 high #1
Verdict: findings
Head: 7358eff05afb78dfcbf0c1a085b7662eb7dd3a32   Unchanged by the review: yes
Patch-id: fd68c6477b1abbd0bae7c6b629d944ad9640ad74
Reviewers: 1, 4   Proof: sh /tmp/pr-review-done-before-pr-reopen.bpS1u4/proof.sh (pytest test_jbus_row_ends.py on the four new and changed row-end tests, then watch.own on a throwaway git repo with a squash-merged base), exit 0, 6 passed, 39 deselected; {'empty-child': False, 'own-child': True, 'base': True, 'gone': False}
Meets the brief: yes for the fix and three of four Done when lines; the third (the 16 rows done again, none in `jbus queue show`) cannot hold before this lands and holds for 14 of 16 after it, the crew's gate question 137 carries the other two (stack-carry-fork, simplify-one-hometree, whose branches have commits of their own)
In flight: none
Findings:
- info features/jbus/tests/test_jbus_row_ends.py:109 the "from its base" case proves a branch stacked on a squash-merged base with no commit of its own is done, but no test has a stacked branch with a commit of its own on top of that base owing its pull request, the case the start-point exclusion in `watch.own` exists to keep apart (principle: principle-test-behavior-not-implementation) (bucket: Consider)
Dropped: 0
Noted: 2
Dismissed: 0
Sent to: not sent, jbus tells the crew when it owes a line
Finding F1: not fixed, no test of a stacked branch with a commit of its own on its base owing its pull request, because consider: left for a follow-up
Woke: jbus, the review of #748 at 7358eff05afb with one finding, F1 [Consider], declined
Scoped review: none, nothing was pushed for the findings
Fixed: none needed, the one finding is a Consider left for a follow-up
Stale base: at 7358eff05afb78dfcbf0c1a085b7662eb7dd3a32, check 2 of 4 (test_view_server.py::test_a_build_that_does_not_end_behind_a_finished_one_serves_the_finished_answer[/state.json], a build race this diff does not touch; the file passes here, 47 passed)
