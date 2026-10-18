# jmerge says ready, wait or hold

`jmerge` prints one line for each open pull request: `ready` when it is reviewed, fixed and green, `wait` with the reason when it is short of that, and `hold` when it touches a path only the user merges. With `--check` it prints the decision and merges nothing. `jmerge --claims` prints the files each brief still out holds.

Paths: `src/jmerge/`, `src/jsettings/`, `docs/jmerge.md`
Tests: `tests/test_claims.py`, `tests/test_crew_skill.py`, `tests/test_deeper_skill.py`, `tests/test_doctor.py`, `tests/test_expert_skill.py`, `tests/test_flow_doc.py`, `tests/test_gate_skills.py`, `tests/test_gates.py`, `tests/test_handoff_mail.py`, `tests/test_handoff_next.py`, `tests/test_handoff_pin.py`, `tests/test_home_guarded_list.py`, `tests/test_home_line.py`, `tests/test_home_merge.py`, `tests/test_home_no_jmerge.py`, `tests/test_home_on_bus.py`, `tests/test_home_start.py`, `tests/test_home_thread.py`, `tests/test_install.py`, `tests/test_item.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus.py`, `tests/test_jbus_alive.py`, `tests/test_jbus_approval.py`, `tests/test_jbus_approve_by_page.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_blocking.py`, `tests/test_jbus_brief_meaning.py`, `tests/test_jbus_cli.py`, `tests/test_jbus_default_webhook.py`, `tests/test_jbus_digest.py`, `tests/test_jbus_dispatch.py`, `tests/test_jbus_events.py`, `tests/test_jbus_expedite.py`, `tests/test_jbus_fresh_head.py`, `tests/test_jbus_gate_silence.py`, `tests/test_jbus_github.py`, `tests/test_jbus_guarded_ask.py`, `tests/test_jbus_jmerge_line.py`, `tests/test_jbus_kitchen.py`, `tests/test_jbus_leftover.py`, `tests/test_jbus_live.py`, `tests/test_jbus_main_moved.py`, `tests/test_jbus_merge.py`, `tests/test_jbus_mirror.py`, `tests/test_jbus_noticed.py`, `tests/test_jbus_one_wake.py`, `tests/test_jbus_pass_record.py`, `tests/test_jbus_plan.py`, `tests/test_jbus_project.py`, `tests/test_jbus_questions.py`, `tests/test_jbus_queue.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_relay.py`, `tests/test_jbus_remarks.py`, `tests/test_jbus_rereview.py`, `tests/test_jbus_resume.py`, `tests/test_jbus_row_ends.py`, `tests/test_jbus_row_history.py`, `tests/test_jbus_sign_in.py`, `tests/test_jbus_signal.py`, `tests/test_jbus_snapshot.py`, `tests/test_jbus_steps.py`, `tests/test_jbus_t3.py`, `tests/test_jbus_threads.py`, `tests/test_jbus_top_level_webhook.py`, `tests/test_jbus_unlock.py`, `tests/test_jbus_verbs.py`, `tests/test_jbus_view.py`, `tests/test_jbus_view_page.py`, `tests/test_jbus_view_usage.py`, `tests/test_jbus_wake.py`, `tests/test_jbus_watch.py`, `tests/test_jbus_word.py`, `tests/test_jmerge_callers.py`, `tests/test_jmerge_drops.py`, `tests/test_jmerge_fresh.py`, `tests/test_jmerge_guarded.py`, `tests/test_jmerge_log.py`, `tests/test_jmerge_rangediff.py`, `tests/test_messages.py`, `tests/test_new_home_skill.py`, `tests/test_party_handoff.py`, `tests/test_pr_review_skill.py`, `tests/test_protected.py`, `tests/test_pull_request_words.py`, `tests/test_queue.py`, `tests/test_quiet_home.py`, `tests/test_roles.py`, `tests/test_scope_root.py`, `tests/test_scoped_handoff.py`, `tests/test_scoped_home.py`, `tests/test_scoped_review.py`, `tests/test_scout_page.py`, `tests/test_settings.py`, `tests/test_setup.py`, `tests/test_stall.py`, `tests/test_sweep.py`, `tests/test_templates.py`, `tests/test_titles.py`, `tests/test_verify_jstack.py`, `tests/test_work.py`

## Sub-features

- `decision-no-review` waits on a green pull request whose brief has no review.
- `decision-ready` is ready at the head a clean review names.
- `decision-hold` holds a pull request that changes a protected path, for the user.
- `decision-red` waits while the check named `check` has not passed.
- `decision-claims` lists the briefs that still hold files.
- `decision-check-merges-nothing` asks GitHub and merges nothing.

## How to get to it (user POV)

- Run `jmerge --check` in the repo's main checkout.
- Run `jmerge --claims` there.
- Run `jmerge` there to merge what is ready (not reachable from a sandbox: the stand-in `gh` refuses a merge).
- Read the `jmerge` and `gate` lines a `jbus poll` sends, which runs `jmerge` where the repo's home is off.

## Driving it with verify-jstack

Needs: `demo`, `tasks`, `gh/open.json`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- The shell is in `$VERIFY_JSTACK_SANDBOX/demo`, and `gh/open.json` is `[]`.

- **Open a pull request.** Run `head=$("$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py)`. `gh/open.json` has pull request 7 on the branch `beta`, green, changing `src/beta/a.py`.
- **Write its brief.** Run `printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n' > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`. The brief has a Result and no review.
- **Ask, unreviewed.** Run `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: it has no review yet`.
- **Add a clean review.** Run `printf '## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `ready 7 <the head> beta beta`.
- **Touch a protected path.** Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta secrets/a.key`, then `record jmerge-decision jmerge --check`. It prints `hold 7 https://example.test/pull/7: needs user, touches secrets/a.key`.
- **Fail the check.** Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py FAILURE`, then `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: check has not passed`.
- **List the claims.** Run `record jmerge-decision jmerge --claims`. It prints `beta pull request 7 root Where: `src/beta/``.
- **Check nothing merged.** Run `record jmerge-decision grep -c "pr merge" "$VERIFY_JSTACK_SANDBOX/gh/calls.log"`. It prints `0` (and exits 1, as `grep -c` does with no match). The demo checkout's `git log --oneline` still has the one commit `start`.
- **Proof.** Copy `gh/calls.log` and the brief into `$VERIFY_JSTACK_EVIDENCE`.

## Gotchas

- `jmerge` reads the briefs from `$HOME/.local/state/home/<the main checkout's directory name>`, not from `JBUS_HOME_DIR`. In a sandbox both are the same directory, because `env.sh` sets HOME.
- The recipe writes the brief through `${VERIFY_JSTACK_SANDBOX:?}`, so a shell that sourced no `env.sh` stops and writes nothing into the live briefs.
- The review's `Head:` must be the pull request's head commit, whole. `open-pull.sh` prints it.
- Only the check named `check` decides green. Another check's name in `statusCheckRollup` changes nothing.
- A plain `jmerge` on a ready pull request reaches `gh pr merge`, which the stand-in refuses with exit 64. That is the harness ending, not a jmerge failure, and it is not proof of a merge.
- Every line of `jmerge --check` exits 0, `wait` and `hold` included. Assert on the line, not the exit code.
- `jmerge` without `--check` appends each line to `merge.log` in the repo's state. `--check` writes nothing.
