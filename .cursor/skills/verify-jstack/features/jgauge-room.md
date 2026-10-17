# jgauge room

`jgauge room` says whether the machine and the plan have room for one more thread: `go`, or `wait: ` and the first reading that has none. jbus asks it before every launch, so a row with no room waits and is launched on a later pass.

Paths: `src/jgauge/`, `hooks/limits.sh`, `docs/jgauge.md`
Tests: `tests/test_briefs.py`, `tests/test_claims.py`, `tests/test_crew_skill.py`, `tests/test_deeper_skill.py`, `tests/test_doctor.py`, `tests/test_expert_skill.py`, `tests/test_gate_skills.py`, `tests/test_gates.py`, `tests/test_handoff_mail.py`, `tests/test_handoff_next.py`, `tests/test_handoff_pin.py`, `tests/test_home_gauge.py`, `tests/test_home_guarded_list.py`, `tests/test_home_line.py`, `tests/test_home_merge.py`, `tests/test_home_no_jmerge.py`, `tests/test_home_on_bus.py`, `tests/test_home_start.py`, `tests/test_home_thread.py`, `tests/test_install.py`, `tests/test_item.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus.py`, `tests/test_jbus_alive.py`, `tests/test_jbus_approval.py`, `tests/test_jbus_approve_by_page.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_blocking.py`, `tests/test_jbus_brief_meaning.py`, `tests/test_jbus_default_webhook.py`, `tests/test_jbus_digest.py`, `tests/test_jbus_dispatch.py`, `tests/test_jbus_events.py`, `tests/test_jbus_expedite.py`, `tests/test_jbus_fresh_head.py`, `tests/test_jbus_gate_silence.py`, `tests/test_jbus_github.py`, `tests/test_jbus_guarded_ask.py`, `tests/test_jbus_jmerge_line.py`, `tests/test_jbus_kitchen.py`, `tests/test_jbus_leftover.py`, `tests/test_jbus_live.py`, `tests/test_jbus_main_moved.py`, `tests/test_jbus_merge.py`, `tests/test_jbus_mirror.py`, `tests/test_jbus_noticed.py`, `tests/test_jbus_one_wake.py`, `tests/test_jbus_pass_record.py`, `tests/test_jbus_plan.py`, `tests/test_jbus_project.py`, `tests/test_jbus_questions.py`, `tests/test_jbus_queue.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_relay.py`, `tests/test_jbus_remarks.py`, `tests/test_jbus_rereview.py`, `tests/test_jbus_resume.py`, `tests/test_jbus_row_ends.py`, `tests/test_jbus_row_history.py`, `tests/test_jbus_sign_in.py`, `tests/test_jbus_signal.py`, `tests/test_jbus_slot_wake.py`, `tests/test_jbus_snapshot.py`, `tests/test_jbus_steps.py`, `tests/test_jbus_t3.py`, `tests/test_jbus_threads.py`, `tests/test_jbus_top_level_webhook.py`, `tests/test_jbus_unlock.py`, `tests/test_jbus_verbs.py`, `tests/test_jbus_view.py`, `tests/test_jbus_view_page.py`, `tests/test_jbus_view_usage.py`, `tests/test_jbus_wake.py`, `tests/test_jbus_watch.py`, `tests/test_jbus_word.py`, `tests/test_jmerge_callers.py`, `tests/test_jmerge_drops.py`, `tests/test_jmerge_fresh.py`, `tests/test_jmerge_guarded.py`, `tests/test_jmerge_log.py`, `tests/test_jmerge_rangediff.py`, `tests/test_limits.py`, `tests/test_messages.py`, `tests/test_new_home_skill.py`, `tests/test_party_handoff.py`, `tests/test_pr_review_skill.py`, `tests/test_probes.py`, `tests/test_protected.py`, `tests/test_pull_request_words.py`, `tests/test_queue.py`, `tests/test_quiet_home.py`, `tests/test_roles.py`, `tests/test_room.py`, `tests/test_scope_root.py`, `tests/test_scoped_handoff.py`, `tests/test_scoped_home.py`, `tests/test_scoped_review.py`, `tests/test_scout_page.py`, `tests/test_session.py`, `tests/test_settings.py`, `tests/test_setup.py`, `tests/test_slot.py`, `tests/test_slot_waiters.py`, `tests/test_stall.py`, `tests/test_sweep.py`, `tests/test_templates.py`, `tests/test_titles.py`, `tests/test_transcript.py`, `tests/test_verify_jstack.py`, `tests/test_work.py`

## Sub-features

- `room-go` prints `go` on an idle machine under its plan limits.
- `room-load` prints `wait:` when the one-minute load is at or over 85% of the cores.
- `room-limit` prints `wait:` when the five-hour or weekly limit is at or over 85% used.
- `room-unknown` prints `go` and a `note:` on stderr when the plan's limits are not known.
- `room-holds-launch` keeps an approved row from launching while there is no room.

## How to get to it (user POV)

- Run `jgauge room`.
- Run `jbus poll` with an approved row in the queue, and read its `wait <slug>: no room: ...` line.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`, `machine/proc`, `machine/limits`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- `$PROC` is `$VERIFY_JSTACK_SANDBOX/machine/proc` and `$LIMITS` is `$VERIFY_JSTACK_SANDBOX/machine/limits`: the load starts at `0.10` and both limits at 10.

- **Idle.** Run `record jgauge-room jgauge room`. It prints `go`.
- **Load.** Run `echo "999.00 9.99 9.99 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"`, then `record jgauge-room jgauge room`. It prints `wait: load 999.00 is at or over 85% of <n> cores`, and exits 0.
- **A row waits.** Run `printf '# alpha: a demo task\nWhere: `src/alpha/`\nPull request: none\n' | record jgauge-room jbus queue add alpha --priority 1`, then `record jgauge-room jbus queue approve alpha --by user --at "2026-10-12 00:30 $(date -d '2026-10-12 00:30' +%Z)" --sha "$(sha256sum "$JBUS_STATE_DIR/demo/briefs/alpha.md" | cut -c1-12)"`, then `record jgauge-room jbus poll`. The pass prints `wait alpha: no room: load 999.00 is at or over 85% of <n> cores` and no `launched` line.
- **Room again.** Run `echo "0.10 0.10 0.10 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"`, then `record jgauge-room jbus poll`. It prints `launched alpha: mcp:sandbox-thread-1`.
- **Plan limit.** Run `printf 'five_hour 91 %s\nseven_day 10 %s\n' "$(($(date +%s) + 3600))" "$(($(date +%s) + 3600))" > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"`, then `record jgauge-room jgauge room`. It prints `wait: the five-hour limit is 91% used, at or over 85%, and resets in 1 h 0 min` (or `0 h 59 min`).
- **Limits not known.** Run `: > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"`, then `record jgauge-room jgauge room`. It prints `note: the plan's five-hour and weekly limits are not known: <path> does not give them` and `go`.
- **Proof.** Copy `t3/calls.jsonl` into `$VERIFY_JSTACK_EVIDENCE`: its one `t3_thread_launch` is from the pass after the load fell.

## Gotchas

- `jgauge room` exits 0 for `go` and for `wait:`. Read the line.
- The core count is the real machine's (`nproc`). Use a load no machine has room for, like `999.00`, so the recipe holds everywhere.
- Without `PROC` and `LIMITS` set, `jgauge room` reads the real machine and the real plan. Doctor checks both point into the sandbox.
- A limit whose reset time has passed counts as not known. Write the reset as a time ahead of now, as `launch.sh` does.
- `record` keeps stdout and stderr together, so the `note:` line is in the evidence beside `go`.
