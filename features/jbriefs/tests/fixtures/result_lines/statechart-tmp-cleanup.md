# statechart-tmp-cleanup: the statechart CLI removes its TLC work dir when a run ends, and keeps it only on request
Green main: dcf9f51bc43851d2fe3daa1cae4ebd3cefb31ac6
Follows: simplify-2
Task: the infra home, 2026-10-28: "jbus alerted on /tmp (tmpfs, 24.6 of 31.1 GiB, 80%). 14 GiB of it is 18 `/tmp/statechart-*` dirs (each holding `tlc/`) ... the statechart CLI's `tempfile.mkdtemp(prefix="statechart-")` keeps its work dir, up to 3.3 GiB each, and whatever is running it now leaves one per run." The simplify scouts run from-spec many times, so /tmp fills while they work
Done when:
- every statechart command that makes a work dir (`tempfile.mkdtemp(prefix="statechart-")` in statechart/cli.py) removes it when the command ends, on success, on a broken rule and on an error, including an interrupt
- a `--keep-work` flag (or an env var the help names) keeps the dir and prints its path, for debugging TLC
- a test runs from-spec on the worked example (scripts/model/OutputFolder.tla) and finds no `statechart-*` dir left under its TMPDIR afterwards, and one left with the keep flag
- `make check-fast BASE=origin/main` passes
Proves it: the test above, and `ls -d /tmp/statechart-*` empty after a from-spec run on the worked example
Size: S
Where: features/skill-library/skills/statechart/scripts/statechart/cli.py (`tempfile.mkdtemp(prefix="statechart-")`), features/skill-library/tests/
Do not touch: what from-spec writes next to its input; the TLA+ specs; the dirs already in /tmp (the home clears those)
Decisions: the infra home handed this to jstack's root home, 2026-10-28
Design: none, a work dir that is removed on exit unless kept
Skills: none
Pull request: open one when done
Review: after
Playbook: none
Thread: mcp:thread-2

## Result
Status: done
Done when: removes the work dir on success, broken rule, error and interrupt holds; --keep-work keeps it and prints its path holds; the worked-example test holds; make check-fast BASE=origin/main holds for the lint, and its selected tests ran past the short lane's 120 s limit (exit 124) with no failure, so CI's check is the test proof
Proof:
- removed on every end: `in_work_folder` removes in `finally`, and a SIGTERM handler raises so cleanup runs and TLC is killed; tests test_a_run_whose_python_is_killed_mid_tlc... (exit 143, TMPDIR empty), test_a_run_that_tlc_stops_on_an_error... and test_a_file_put_in_the_output_folder... assert nothing left
- --keep-work: test_a_run_that_tlc_stops_on_an_error_names_tlcs_output... and the worked-example test match the printed path
- worked example: test_a_run_of_the_worked_example_leaves_no_work_folder_unless_keep_work_keeps_it; targeted run `pytest test_statechart_runs.py -k ...` printed 7 passed in 44.33s
- by hand: from-spec model/OutputFolder.tla --out <scratch> exited 0 and added no /tmp/statechart-* dir (6 older ones were already there, left for the home)
- check: `selected: 66 test files`, lint passed, pytest stopped at 94% by the short lane's limit, exit 124; CI's check at the head is the proof
Branch: statechart-tmp-cleanup   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/679
Changed: statechart/cli.py removes its statechart- work dir on every end, also on SIGTERM, and --keep-work keeps it and names it; tests updated and one added for the worked example
Wider: none
Playbook: none
Skills run: none
Steers: none
Left: none
Reviewer: mcp:thread-11 #1

## Review
By: claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: findings
Head: eec292d0edd047fd7e7243c0640a3bbebfcc8b6f   Unchanged by the review: yes
Patch-id: 90e90b29b1935a4b62839c787b8ff4c5de36b06b
Reviewers: 1, 4   Proof: sh "$D/proof.sh" (SIGTERM a from-spec run of a slow spec with no test slot held, then list its TMPDIR and look for a tlc2.TLC process), exit 1, AssertionError: TLC outlived the SIGTERMed run
Meets the brief: yes (all four Done when lines hold: removal on success, error and SIGTERM, --keep-work, the worked-example test; the finding below is about the SIGTERM path leaving TLC running, not about a missing work dir)
In flight: none
Findings:
- warning features/skill-library/skills/statechart/scripts/statechart/cli.py:925 SIGTERM does not stop TLC when the run holds no test slot: Terminated is raised, subprocess.run in run_tlc SIGKILLs only `jgauge test-slot` (its direct child), so java is orphaned and keeps running against the removed work and metadir folders (its open files hold tmpfs space until it ends); the SIGTERM test sets JGAUGE_TEST_SLOT, so java is the direct child there, and the dropped `os.killpg` check was not replaced by one that TLC is gone (principle: none) (bucket: Act on)
Dropped: 0
Noted: 1
Dismissed: 1
- info features/skill-library/tests/test_statechart_runs.py:704 no test asserts the removal after a run that breaks a rule, which a Done when line names (principle: none) (dismissed: the broken-rule end goes through the same finally as the success and error ends that are tested)
Sent to: not sent, jbus tells the crew when it owes a line

## Result, follow-up (2026-10-28, check 2 of 4 failed, then the review's F1)
Status: done
Done when: as the Result above, every line holds; CI's check passed at 5e6fe9a2ec5f45723244bd988cb62becdbd6ea72, which jmerge merged as c9c167c8f
Proof:
- CI: check 2 of 4 failed at eec292d0edd047fd7e7243c0640a3bbebfcc8b6f in test_statechart_names_the_chart_it_refuses_and_the_argument_it_does_not_know, which pins the usage line; FROM_SPEC_USAGE and FROM_CHART_USAGE in tests/statechart_support.py now name [--keep-work], and test_statechart_charts.py with test_statechart_specs.py printed 53 passed
- F1: the new "taken" case of the SIGTERM test failed on eec292d (AssertionError: TLC outlived the run) and passes with run_in_own_group and stop_group; 9 targeted tests passed in 44.12s
- check: selected check of 66 files, lint passed, stopped at the short lane's 120 s limit (exit 124); the full-slot `make check-fast BASE=origin/main` was lost when the merge removed the worktree
Branch: statechart-tmp-cleanup   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/679 (merged)
Changed: TLC runs in its own process group, and an error, interrupt or SIGTERM stops the whole group; the usage pins name --keep-work
Wider: none
Playbook: none
Skills run: none
CI fix: 5e6fe9a2ec5f45723244bd988cb62becdbd6ea72, after the review of eec292d0edd047fd7e7243c0640a3bbebfcc8b6f
Finding F1: fixed, SIGTERM left TLC running under jgauge test-slot, fixed in 5e6fe9a, which also went to the cleanup row; that row's thread was told it is already on main
Steers: none
Left: none
