# dual-reviewer: one pull request reviewed by two reviewers at once
Task: "a fixture of a brief reviewed by two reviewers, with ids, buckets and answers"
Review: review

## Result
Status: done
Branch: dual-reviewer   Pull request: https://example.test/pull/129
Reviewer: mcp:codex-1
Reviewer: mcp:cursor-2
Finding F1: fixed, a re-run at one head reads as no verdict forever
Finding F2: not fixed, Codex's home has no jstack skills, because `ls ~/.codex/skills` is the home's install.sh to fill, and the brief puts that link in providers-as-code
Finding F3: not fixed, the intro sentence points at the By: block, because consider: left for a follow-up
Finding F4: fixed, By: now comes from t3_thread_configuration
Fixed: 1e16fb7dd82ea2dae3209f561f5273e559b46b4a

## Review
By: codex gpt-6-sol xhigh
Verdict: findings
Head: 45c6ac9b92b540da131b8dc6b17eb39666ab5b77   Unchanged by the review: yes
Findings:
- error src/jmerge/ready.py:433 a not-run section and a clean re-run at one head read as no verdict forever (principle: principle-model-the-domain) (bucket: Act on)
- warning - a Done when line is not met: Codex's home has jstack's skills (principle: principle-prove-it-works) (bucket: Act on)
- info skills/pr-review/SKILL.md:89 the intro sentence points at the By: block, not the decision (principle: none) (bucket: Consider)
- warning skills/pr-review/SKILL.md:92 the By: line is read from jroles review at Start, a proxy for the thread's model (principle: principle-prove-it-works) (bucket: Act on)
Dropped: 0
Noted: 0
Dismissed: none
Sent to: mcp:crew

## Review
By: cursor grok-4.7 xhigh
Verdict: findings
Head: 45c6ac9b92b540da131b8dc6b17eb39666ab5b77   Unchanged by the review: yes
Findings:
- warning src/jmerge/ready.py:437 the round's verdict is the worst of every section, so one reviewer's re-run never replaces its not-run section (principle: principle-model-the-domain) (bucket: Act on)
Dropped: 0
Noted: 1
Dismissed: 1
- warning skills/pr-review/SKILL.md:94 By: read from jroles is a proxy (principle: principle-prove-it-works) (dismissed: Start now asks t3_thread_configuration, jroles only where it is missing)
Sent to: mcp:crew
