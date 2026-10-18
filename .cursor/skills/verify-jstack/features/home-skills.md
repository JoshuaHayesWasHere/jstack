# A home and its handoff

The home skill makes a thread the home of a repo: it plans with the user, queues briefs, and hands off to a fresh home before its context grows. `new-home` adds a repo, `nohome` opts out, `handoff` writes the short note and starts the next home, and `hooks/home-start.sh` starts a home in a new thread by itself. An agent runs these skills in a thread; the tests lift each shell block and run it.

Paths: `skills/home/`, `skills/new-home/`, `skills/nohome/`, `skills/handoff/`, `hooks/home-start.sh`, `templates/handoff.md`, `templates/handoff-seed.md`, `templates/hook-message.md`, `templates/plan-entry.md`
Tests: `tests/test_briefs.py`, `tests/test_claims.py`, `tests/test_crew_skill.py`, `tests/test_eval_skill_cut.py`, `tests/test_expert_skill.py`, `tests/test_gates.py`, `tests/test_grilling.py`, `tests/test_handoff_mail.py`, `tests/test_handoff_next.py`, `tests/test_handoff_pin.py`, `tests/test_home_deeper.py`, `tests/test_home_gauge.py`, `tests/test_home_guarded_list.py`, `tests/test_home_line.py`, `tests/test_home_merge.py`, `tests/test_home_no_jmerge.py`, `tests/test_home_on_bus.py`, `tests/test_home_start.py`, `tests/test_home_thread.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_leftover.py`, `tests/test_jbus_word.py`, `tests/test_jmerge_fresh.py`, `tests/test_jmerge_guarded.py`, `tests/test_lessons.py`, `tests/test_limits.py`, `tests/test_messages.py`, `tests/test_new_home_skill.py`, `tests/test_party_handoff.py`, `tests/test_pr_review_skill.py`, `tests/test_protected.py`, `tests/test_queue.py`, `tests/test_quiet_home.py`, `tests/test_roles.py`, `tests/test_room.py`, `tests/test_scope_root.py`, `tests/test_scoped_handoff.py`, `tests/test_scoped_home.py`, `tests/test_slot.py`, `tests/test_sweep.py`, `tests/test_templates.py`, `tests/test_titles.py`, `tests/test_understanding_skills.py`, `tests/test_verify_jstack.py`

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
