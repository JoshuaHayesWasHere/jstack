# A pull request is reviewed

The pr-review skill reviews a finished pull request in a fresh thread: it reads the diff, judges what it found, proves the one safety fact by running code, and sends the findings to the crewmate. `blast-radius` and `interrogate` are the questions it asks.

Paths: `skills/pr-review/`, `skills/blast-radius/`, `skills/interrogate/`, `templates/review.md`
Tests: `tests/test_crew_skill.py`, `tests/test_eval_skill_cut.py`, `tests/test_flow_doc.py`, `tests/test_gate_skills.py`, `tests/test_home_line.py`, `tests/test_home_thread.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus_dispatch.py`, `tests/test_messages.py`, `tests/test_pr_review_skill.py`, `tests/test_scoped_review.py`, `tests/test_skill_tips.py`, `tests/test_templates.py`, `tests/test_understanding_skills.py`, `tests/test_understanding_skills_2.py`

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
