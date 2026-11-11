# po-scout-model-doc: what-a-pass-launches.md says a request's Model: line sets its scout's model
Stacked on: po-scout-request-model main at dc676a4cb82e9820b7a677075873d203b6206121
Task: "Go on all the rows" (the user, 2026-11-10, in the polish home). The jbus doc on scout launches still says a scout's model is the role map's `scout` line, while po-scout-request-model made a request's `Model:` line set it, the role map's line giving only the provider, pool and options. Fix: say so in the doc.
Done when:
- the scout launch section says a request's `Model:` line sets the scout's model over the role map's `scout` line, which gives the provider, pool and options, that a request without it launches on the role map's model, and that a request naming a model with no `scout` line in the role map is a condition and launches nothing (in `features/jbus/docs/jbus/what-a-pass-launches.md`)
Proves it: the doc's line matches `features/jbus/src/jbus/scouts.py`'s docstring, and the repo's check passes
Size: S
Where: `features/jbus/docs/jbus/what-a-pass-launches.md`
Do not touch: the role map itself
Decisions: noticed in po-scout-request-model, from its review's finding F1. The role map stays as it is, on the user's word of 2026-11-09 ("don't switch role map to fable yet").
Follows: po-scout-request-model
Skills: technical-writing
Pull request: open one when done
Review: review
Playbook: bug-fix
Builds on: po-scout-request-model: the `Model:` line of a scout request that `jbus.scouts` and `jbus.queue.model` read
Home: polish
Thread: mcp:thread-1
Checked: make check-fast BASE=852731dca25a8354c6516ad1248bdc768b75e328 PART=touched exit 0 at 4c1e812abd28b97f67f1fd24c11b0c705ed1c634

## Result
Status: done
Done when: the scout launch section says a request's `Model:` line sets the scout's model over the role map's `scout` line (provider, pool and options), that a request without it launches on the role map's model, and that a request naming a model with no `scout` line is a condition and launches nothing: holds
Proof:
- the doc's line matches `scouts.py`'s docstring: `features/jbus/docs/jbus/what-a-pass-launches.md:174-177` read beside `features/jbus/src/jbus/scouts.py:21-25`, the condition text quoted from `scouts.py:141`
- the repo's check: touched: 0 test files, then 19 guard tests of features/repo-guards/tests; lint: exit 0, each of the 19 guard tests exit 0, short lane; Checked: make check-fast BASE=852731dca25a8354c6516ad1248bdc768b75e328 PART=touched exit 0 at 4c1e812abd28b97f67f1fd24c11b0c705ed1c634
Proved: none, docs
Branch: po-scout-model-doc   Pull request: after the review
Stacked on: po-scout-request-model po-scout-request-model
Changed: the scout launch line of `what-a-pass-launches.md` now says the request's `Model:` line sets the model, on the role map's `scout` line's provider, pool and options, the role map's model with no `Model:` line, and the condition where the role map has no `scout` line.
Playbook: playbooks/bug-fix.md; 1 done; 2 skip: a doc line has no test path and the docs guard tests cover it; 3 skip: the brief names the cause, the stale line at what-a-pass-launches.md:174; 4 done; 5 done; 6 skip: no failing repro to commit for a doc line; 7 skip: the pull request opens after its review
Skills run:
- technical-writing: split the one stale sentence into three one-thought reference sentences, named the real symbols (`jbus.queue.model`, the role map's `scout` line) and the condition text as code prints it
Steers: none
Left: none
Reviewer: mcp:thread-6 #1

## Review
claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: clean
Head: 4c1e812abd28b97f67f1fd24c11b0c705ed1c634   Unchanged by the review: yes
Patch-id: 64dcc8f82de4687223bc05ccb09e3c6c7ca95ee6
Reviewers: 1, 0   Proof: sh /tmp/pr-review-po-scout-model-doc.gawVsI/proof.sh, exit 0, ok: the request names a model and the role map has no scout line; 5 passed, 36 deselected, not run: the repo's check command, CI runs it
Meets the brief: yes, 1 of 1
In flight: none
Outside Where: none
Findings:
- none
Dropped: 0
Noted: 0
Dismissed: 0
Sent to: not sent, jbus tells the crew when it owes a line

## Result, follow-up (2026-11-09, the pull request opened after its review)
Status: done
Done when: the scout launch section says a request's `Model:` line sets the scout's model over the role map's `scout` line (provider, pool and options), that a request without it launches on the role map's model, and that a request naming a model with no `scout` line is a condition and launches nothing: holds
Proof:
- the doc's line matches `scouts.py`'s docstring: `features/jbus/docs/jbus/what-a-pass-launches.md:174-177` read beside `features/jbus/src/jbus/scouts.py:21-25`, the condition text from `scouts.py:141`
- the repo's check: lint exit 0 and 19 guard tests exit 0, short lane; Checked: make check-fast BASE=852731dca25a8354c6516ad1248bdc768b75e328 PART=touched exit 0 at 4c1e812abd28b97f67f1fd24c11b0c705ed1c634; CI's check runs on the pull request
Proved: none, docs
Branch: po-scout-model-doc   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/1553
Stacked on: po-scout-request-model po-scout-request-model, https://github.com/JoshuaHayesWasHere/jstack/pull/1547
Changed: the scout launch line of `what-a-pass-launches.md` now says the request's `Model:` line sets the model on the role map's `scout` line's provider, pool and options, the role map's model with no `Model:` line, and the condition where the role map has no `scout` line.
Playbook: playbooks/bug-fix.md; 1 done; 2 skip: a doc line has no test path and the docs guard tests cover it; 3 skip: the brief names the cause, the stale line at what-a-pass-launches.md:174; 4 done; 5 done; 6 skip: no failing repro to commit for a doc line; 7 done
Skills run:
- technical-writing: split the one stale sentence into three one-thought reference sentences, named the real symbols (`jbus.queue.model`, the role map's `scout` line) and the condition text as code prints it
Scoped review: none, one round: the fix merges on its checks
Fixed: none needed, the review is clean with no findings
Steers: none
Left: none
