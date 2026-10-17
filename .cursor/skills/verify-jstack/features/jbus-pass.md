# A jbus pass

`jbus poll` is one pass over every project: it reads the queue, the briefs, T3 Code and GitHub, launches what is approved and has room, tells each thread what it must act on, runs `jmerge`, and writes what it saw to the state directory. Every other `jbus` verb reads or writes that state. This feature is the whole `jbus` package and what it imports, so its tests are every test that runs a pass or a `jbus` verb.

Paths: `src/jbus/*.py`, `src/jbus/view/*.py`, `src/jbus/view/panels/__init__.py`, `src/jbriefs/`, `src/jgauge/`, `src/jmerge/`, `src/jsettings/`, `docs/jbus.md`, `docs/chef.md`, `docs/configuration.md`, `docs/state.md`, `docs/troubleshooting.md`, `templates/jbus.service`, `templates/jbus.timer`, `templates/jbus-failed.service`, `templates/jbus-relay.service`, `templates/jbus-snapshot.service`, `templates/jbus-snapshot.timer`, `templates/jbus-snapshot-failed.service`, `templates/jbus-view.service`
Tests: `tests/test_claims.py`, `tests/test_crew_skill.py`, `tests/test_deeper_skill.py`, `tests/test_doctor.py`, `tests/test_expert_skill.py`, `tests/test_flow_doc.py`, `tests/test_gate_skills.py`, `tests/test_gates.py`, `tests/test_handoff_mail.py`, `tests/test_handoff_next.py`, `tests/test_handoff_pin.py`, `tests/test_home_line.py`, `tests/test_home_merge.py`, `tests/test_home_no_jmerge.py`, `tests/test_home_on_bus.py`, `tests/test_home_start.py`, `tests/test_home_thread.py`, `tests/test_install.py`, `tests/test_item.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus.py`, `tests/test_jbus_alive.py`, `tests/test_jbus_approval.py`, `tests/test_jbus_approve_by_page.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_blocking.py`, `tests/test_jbus_brief_meaning.py`, `tests/test_jbus_default_webhook.py`, `tests/test_jbus_digest.py`, `tests/test_jbus_dispatch.py`, `tests/test_jbus_events.py`, `tests/test_jbus_expedite.py`, `tests/test_jbus_fresh_head.py`, `tests/test_jbus_gate_silence.py`, `tests/test_jbus_github.py`, `tests/test_jbus_guarded_ask.py`, `tests/test_jbus_jmerge_line.py`, `tests/test_jbus_kitchen.py`, `tests/test_jbus_leftover.py`, `tests/test_jbus_live.py`, `tests/test_jbus_main_moved.py`, `tests/test_jbus_merge.py`, `tests/test_jbus_mirror.py`, `tests/test_jbus_noticed.py`, `tests/test_jbus_one_wake.py`, `tests/test_jbus_pass_record.py`, `tests/test_jbus_plan.py`, `tests/test_jbus_project.py`, `tests/test_jbus_questions.py`, `tests/test_jbus_queue.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_relay.py`, `tests/test_jbus_remarks.py`, `tests/test_jbus_rereview.py`, `tests/test_jbus_resume.py`, `tests/test_jbus_row_ends.py`, `tests/test_jbus_row_history.py`, `tests/test_jbus_sign_in.py`, `tests/test_jbus_signal.py`, `tests/test_jbus_slot_wake.py`, `tests/test_jbus_snapshot.py`, `tests/test_jbus_steps.py`, `tests/test_jbus_t3.py`, `tests/test_jbus_threads.py`, `tests/test_jbus_top_level_webhook.py`, `tests/test_jbus_unlock.py`, `tests/test_jbus_verbs.py`, `tests/test_jbus_view.py`, `tests/test_jbus_view_page.py`, `tests/test_jbus_view_usage.py`, `tests/test_jbus_wake.py`, `tests/test_jbus_watch.py`, `tests/test_jbus_word.py`, `tests/test_jmerge_callers.py`, `tests/test_jmerge_drops.py`, `tests/test_jmerge_fresh.py`, `tests/test_jmerge_guarded.py`, `tests/test_jmerge_log.py`, `tests/test_jmerge_order.py`, `tests/test_jmerge_rangediff.py`, `tests/test_messages.py`, `tests/test_new_home_skill.py`, `tests/test_party_handoff.py`, `tests/test_pr_review_skill.py`, `tests/test_protected.py`, `tests/test_pull_request_words.py`, `tests/test_queue.py`, `tests/test_quiet_home.py`, `tests/test_roles.py`, `tests/test_scope_root.py`, `tests/test_scoped_handoff.py`, `tests/test_scoped_home.py`, `tests/test_scoped_review.py`, `tests/test_scout_page.py`, `tests/test_settings.py`, `tests/test_setup.py`, `tests/test_skills_named.py`, `tests/test_slot_waiters.py`, `tests/test_stall.py`, `tests/test_sweep.py`, `tests/test_templates.py`, `tests/test_titles.py`, `tests/test_verify_jstack.py`, `tests/test_view_tokens.py`, `tests/test_work.py`

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
