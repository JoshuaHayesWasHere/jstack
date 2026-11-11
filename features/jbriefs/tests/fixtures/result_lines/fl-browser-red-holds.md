# fl-browser-red-holds: a pull request whose own browser run failed does not merge, and its crew is told what it owes, as for a failed check
Green main: b0b1d4b6e4bb06767cb477cdb3e03d2a656594f5
Task: #557 (fl-sub-no-steer) merged with its own browser run red and turned main red on the browser tests; #563 then merged red on the same tests. browser.yml runs on a pull request that changes the view and is no required check, so jmerge does not wait on it, and since browser-red-main-only (#538) jbus files no `browser-red-` row for a pull request's run (`watch.Nightly`, `_nightly_red`). A pull request's browser red is then nobody's. Josh's word, 2026-10-27, root thread: "if there is a solution to the issue, then it should be done ... YOU CAN FIX THESE YOURSELF".
Done when:
- jmerge holds a pull request whose head has a completed browser.yml run that failed, with one reason (a new `Reason` in `ready.py`, the word `check`), and does not hold one whose head has no browser run (a pull request that does not touch the view) or a run still going (it waits as for any pending run of the head)
- a red that main's own browser run already has at the pull request's base is not the pull request's: jmerge holds it with the main-red rule it uses for check.yml (`jmerge.rows.red`, main.json), so a pull request is not blocked by a red it did not make
- `expedite.TABLE` has the row for the new reason, so jbus tells the crew it is short (through the outbox) and the crew fixes its own red, as for a failed check
- tests: a head with a failed browser run is held with the reason; a head with none merges; a red that main has at the base is the main-red wait; the crew gets one short-of message
Proves it: the tests above under `jgauge test-slot --short` fail on main and pass on the branch; replayed through the kitchen's fakes with #557's runs at c05d32d4, jmerge holds it
Size: M
Where: `features/jmerge/src/jmerge/{ready,checks,rows}.py`, `features/jbus/src/jbus/expedite.py` (`TABLE`), their tests, `features/jmerge/docs/jmerge.md`
Do not touch: browser.yml and every other workflow, the ruleset (the run stays no required check), `watch.Nightly`'s rule for main's nightly run, .github/workflows/
Decisions: Josh, 2026-10-27, root thread: agents fix these themselves
Design: none, the browser run of a head joins the runs jmerge already reads, and the crew's short-of path already exists
Skills: none
Pull request: open one when done
Review: twice
Playbook: bug-fix
Home: flow
Read:
- .github/workflows/browser.yml:1-30 (its triggers; its comment that a pull request's red run is filed is stale since #538, so say so in Noticed)
- features/jbus/src/jbus/watch.py:1110-1170 (`Nightly`, `BROWSER`), `_nightly_red`
- features/jmerge/src/jmerge/ready.py (`Reason`s), checks.py, rows.py (`red`)
- features/jbus/src/jbus/expedite.py:300-350 (`TABLE`, `short_of`)
Change:
- as above
Rests on:
- the root home's report, 2026-10-27: #557 merged with browser red; first bad commit c05d32d4 by bisect; #563 merged red at 24ba4950
Sources: features/jmerge, features/jbus/src/jbus/expedite.py, watch.py
Ruled out: making browser a required check (the ruleset is out of reach, and every pull request that does not touch the view would wait on a run it never has); filing a `browser-red-` row for a pull request's run again (#538 took that out: the crew of the pull request owns its red)
Thread: mcp:thread-8

## Result
Status: done
Done when:
- jmerge holds a head whose browser run failed with one reason, `BROWSER_RED` (step `check`), and not a head with no browser run; a run still going waits as a pending run: holds
- a red that main's own browser run already has is the main-red wait (`MAIN_RED`): holds, but read from GitHub's browser.yml runs on main, not from main.json (see Noticed)
- `expedite.TABLE` has the `browser` row, and the crew gets one short-of message: holds
- tests for each of the above: holds
Proof:
- red first: at 939896c3 (tests, plus the bare `BROWSER_RED` and `BROWSER_FIX` names), `jgauge test-slot --short -- uv run pytest features/jmerge/tests/test_jmerge_browser.py features/jbus/tests/test_jbus_expedite.py::test_the_third_pass_of_one_reason_at_one_head_tells_the_crew_once` printed `7 failed, 9 passed`. The #557 replay printed `merged 557 sub-no-steer ...` where `wait 557 ...: its browser run failed at <head12>` was expected, and the crew got no message.
- green: at b392a617, the same tests plus the whole of test_jbus_expedite, test_jmerge_required, test_jmerge_no_run and test_jmerge_rejudge printed `110 passed`.
- replay of #557: `test_the_replay_of_557_its_own_browser_red_holds_it` uses #557's rollup (a draft run skipped, then a failed run, with check passed), through `test_jmerge_rejudge.Replay`, the kitchen's fakes. jmerge holds it.
- the check: `make check-fast BASE=<merge-base>`, selected `all`, so it ran lint only. ruff check, ruff format and the docs checks all passed. CI's check on #575 is still the gate.
Branch: fl-browser-red-holds   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/575
Changed: jmerge reads the head's `browser` check (`ready.browser`). A failed run holds the pull request as `its browser run failed at <head12>`, or as `main is red at <sha12>` when main's last browser run on main also failed (`rows.browser_red`, `cli.Repo.browser_red`). A run still going waits as `browser has not passed`. `expedite.TABLE` has the `browser` row, and jmerge.md documents the rule.
Wider: features/jmerge/src/jmerge/cli.py: the judge order and the GitHub call for main's browser runs live in `Repo`, and ready and rows make no calls
Wider: features/jmerge/tests/test_jmerge_browser.py: the new tests, among "their tests"
Wider: features/jbus/tests/test_jbus_expedite.py: the test of expedite.TABLE's new row, among "their tests"
Playbook: features/crew/playbooks/bug-fix.md; 1 done; 2 done; 3 done; 4 done; 5 done; 6 done; 7 done
Skills run: none
Steers: none
Noticed:
- The brief's premise is partly off: main.json records check.yml alone, never main's browser run. So "main's red at the base" is read from GitHub: the latest completed browser.yml run on main whose event is not pull_request, ignoring cancelled and skipped runs. If it failed, its commit is the red. The fix row `browser-red-*` is not held by it.
- The comment at the top of .github/workflows/browser.yml ("so a pull request's red run is filed too") has been stale since #538. Out of bounds here, so it stays as it is.
- The go check printed `go: your go for the plan entry fl-message-census` for this slug. It names another entry, which may be a jbus quirk worth a look.
- A browser run that went red only because main was red when it ran, with main green since, is still held as the pull request's own. Its crew is told and reruns it.
Left: none
Reviewer: mcp:thread-5 #1

## Review
By: claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: findings
Head: b392a61782420e9998ffd33dd7bc3d5c734020cd   Unchanged by the review: yes
Patch-id: fac14ae58193637f69c22d77327806f27c96caee
Reviewers: 1, 3   Proof: sh /tmp/pr-review-fl-browser-red-holds.az0MVd/proof.sh (uv run pytest of test_jmerge_browser.py, test_jmerge_no_run.py and the expedite once-per-head test), exit 0, 20 passed in 13.27s
Meets the brief: yes
In flight: pull request 571: features/jbus/tests/test_jbus_expedite.py; pull request 570: features/jbus/tests/test_jbus_expedite.py; pull request 569: features/jmerge/docs/jmerge.md, features/jmerge/src/jmerge/ready.py, features/jmerge/src/jmerge/rows.py
Findings:
- warning features/jmerge/src/jmerge/rows.py:107 main_browser_red reads main's last browser.yml run as the red of every pull request, but browser.yml never runs on a push to main (nightly, release tag and manual runs only), so that run is up to a day old and is not tied to the pull request's base as the brief's second Done-when line says. After the fix of a nightly red merges, a pull request whose own browser run fails is held as `main is red at <sha12>, its fix merges first` until the next nightly goes green, and jbus tells its crew nothing for that window (MAIN_RED has no TABLE row); a red that main has for a different reason hides the pull request's own red the same way (principle: principle-attack-the-premise) (bucket: Consider)
- info features/jmerge/tests/test_jmerge_browser.py:143 the test of a pull request short of its review asserts only that some line was said and that it does not carry BROWSER_RED, so it does not say what the pull request waits on (principle: principle-test-behavior-not-implementation) (bucket: Consider)
- info features/jmerge/src/jmerge/cli.py:1040 browser_red repeats the gh api call, the returncode check and the json parse with its fallback of Repo.red, fifteen lines apiece; one helper that returns the list for a path and key would hold both (principle: principle-laziness-protocol) (bucket: Consider)
Dropped: 0
Noted: 0
Dismissed: 0
Sent to: mcp:thread-8
Woke: review #1 at b392a61782420e9998ffd33dd7bc3d5c734020cd, 3 Consider findings; fixed F2, declined F1 and F3 as follow-ups, pushed 530519cd2c0e540fa6c3fb5fee0152def6247ca0
Finding F1: not fixed, main_browser_red reads a day-old nightly as main's red for every pull request, because consider: left for a follow-up
Finding F2: fixed, the short-of-review test now asserts the exact wait, `it has no review yet`
Finding F3: not fixed, browser_red repeats Repo.red's gh api call and parse, because consider: left for a follow-up
Noticed: follow-up: main_browser_red reads main's last browser.yml run as the red of every pull request, but browser.yml never runs on a push to main, so that run can be up to a day old and is not tied to the pull request's base. After the fix of a nightly red merges, a pull request whose own browser run fails is held as main-red until the next nightly goes green, and jbus tells its crew nothing in that window. One remedy is to count main's red only while a non-final `browser-red-` row is in the queue (features/jmerge/src/jmerge/rows.py:107).
Noticed: follow-up: browser_red repeats the gh api call, the returncode check and the json parse with the fallback of Repo.red; one helper returning the list for a path and key would hold both (features/jmerge/src/jmerge/cli.py:1040)
Checked: make check-fast BASE=origin/main exit 0 at 530519cd2c0e540fa6c3fb5fee0152def6247ca0
Fixed: 04d7539a11dcba48fd99e5e8e7b8b70304530b44
Second reviewer: mcp:thread-9 #1

## Review
By: claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: findings
Head: 530519cd2c0e540fa6c3fb5fee0152def6247ca0   Unchanged by the review: yes
Patch-id: a06862aa0cb83ba11821008c4b5723720c02e7a4
Reviewers: 1, 4   Proof: sh /tmp/pr-review-fl-browser-red-holds.cHBAg3/proof.sh (uv run pytest of test_jmerge_browser.py, test_jmerge_no_run.py, test_jmerge_required.py and the expedite once-per-head test), exit 0, 27 passed in 20.14s
Meets the brief: yes
In flight: pull request 571: features/jbus/tests/test_jbus_expedite.py; pull request 570: features/jbus/tests/test_jbus_expedite.py; pull request 569: features/jmerge/docs/jmerge.md, features/jmerge/src/jmerge/ready.py, features/jmerge/src/jmerge/rows.py
Findings:
- warning features/jmerge/src/jmerge/rows.py:107 main_browser_red reads main's last browser.yml run as the red of every pull request, but browser.yml never runs on a push to main (nightly, release tag and manual runs only), so that run is up to a day old and is not tied to the pull request's base as the brief's second Done-when line says; after the fix of a nightly red merges, a pull request whose own browser run fails is held as `main is red at <sha12>, its fix merges first` until the next nightly goes green, and jbus tells its crew nothing for that window (MAIN_RED has no TABLE row) (principle: principle-attack-the-premise) (bucket: Consider)
- warning features/jmerge/src/jmerge/cli.py:950 judged blanks `browser` for a draft (line 918) so a draft's browser state is waived as its failed checks are, but browser_red reads the unblanked `one`, so a draft pull request whose browser run failed is held as `its browser run failed at <head12>` (which jbus tells its crew) and asks GitHub for main's runs, where a draft with a failed check says `draft` (principle: none) (bucket: Consider)
Dropped: 0
Noted: 2
Dismissed: 0
Sent to: mcp:thread-8
Second review: 2 warning or error findings filed as cleanup-fl-browser-red-holds, 0 info dropped
Woke: jbus, check 3 of 4 failed at 530519cd2c0e: test_flow_spec and test_home_tree_spec found the models' line cites of cli.py, rows.py and ready.py moved, and test_jbus_merge found ready.browser returning bare words. The new code now sits after every cited line (the end of ready.py, rows.py and cli.py, with in-place edits at cli.py:1014 and :1879), and the browser states are named constants. Merged GitHub's merge of main into it (5a2bce4b), no force, pushed 04d7539a11dcba48fd99e5e8e7b8b70304530b44, and Fixed moved to it.
Checked: make check-fast BASE=origin/main exit 0 at afcccc09f3a3dfe65c777a0eb21492d20e1878a9, and after merging the branch's merge of main the guards and feature tests passed (117) at 04d7539a11dcba48fd99e5e8e7b8b70304530b44
Wider: features/jbus/tests/test_jbus_merge.py: its WORDS set lists the strings of ready.py that are no reason, and now holds BROWSER, BROWSER_FAILED and BROWSER_PENDING
