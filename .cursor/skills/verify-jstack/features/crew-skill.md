# A crewmate does one task

The crew skill makes a thread a crewmate: it does the one task of a brief in its own worktree, writes the Result into the brief, opens the pull request and stays on it until it merges. Its blocks decide whom to tell, when to rebase and when a review is owed; the tests lift each block and run it.

Paths: `skills/crew/`, `templates/brief.md`, `templates/result.md`, `templates/gates.md`, `playbooks/pause-safely.md`
Tests: `tests/test_briefs.py`, `tests/test_crew_skill.py`, `tests/test_deeper_skill.py`, `tests/test_eval_skill_cut.py`, `tests/test_gates.py`, `tests/test_home_line.py`, `tests/test_home_thread.py`, `tests/test_install.py`, `tests/test_jbriefs_pick.py`, `tests/test_jbus_approval.py`, `tests/test_jbus_brief_meaning.py`, `tests/test_jbus_digest.py`, `tests/test_jbus_gate_silence.py`, `tests/test_jbus_mirror.py`, `tests/test_jbus_questions.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_view.py`, `tests/test_jbus_view_page.py`, `tests/test_messages.py`, `tests/test_playbooks.py`, `tests/test_pr_review_skill.py`, `tests/test_pull_request_words.py`, `tests/test_quiet_home.py`, `tests/test_roles.py`, `tests/test_scoped_home.py`, `tests/test_show_me_your_work.py`, `tests/test_templates.py`, `tests/test_titles.py`, `tests/test_understanding_skills.py`, `tests/test_work.py`

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
