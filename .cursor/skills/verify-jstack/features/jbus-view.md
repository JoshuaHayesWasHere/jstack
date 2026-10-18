# jbus view

`jbus view` is a local web page over what the passes left: the queue, the threads, the questions, the checks, the room and the usage, in panels. Its one write is the user's answer to a question. The page is driven in a headless browser at a desk's size and a phone's, with axe (`tests/fixtures/jbus-view/axe-run.js`).

Paths: `src/jbus/view/`, `templates/jbus-view.service`
Tests: `tests/test_jbus.py`, `tests/test_jbus_approval.py`, `tests/test_jbus_approve_by_page.py`, `tests/test_jbus_approve_by_rule.py`, `tests/test_jbus_blocking.py`, `tests/test_jbus_fresh_head.py`, `tests/test_jbus_leftover.py`, `tests/test_jbus_merge.py`, `tests/test_jbus_questions.py`, `tests/test_jbus_queue_remove.py`, `tests/test_jbus_row_ends.py`, `tests/test_jbus_steps.py`, `tests/test_jbus_top_level_webhook.py`, `tests/test_jbus_view.py`, `tests/test_jbus_view_page.py`, `tests/test_jbus_view_usage.py`, `tests/test_view_tokens.py`

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
