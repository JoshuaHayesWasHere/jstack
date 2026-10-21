# Fixtures

`findings/two-reviewers.md` is written by hand for `features/jbriefs/tests/test_jbriefs_findings.py`, after the brief of dual-reviewer (pull request 129), whose review was by one reviewer: a brief two reviewers reviewed at one head, in the shape `templates/review.md` gives since the buckets. Both name one place in `src/jmerge/ready.py`, which is one finding, and one dismisses what the other raised, which is printed beside it. `uv run jbriefs --findings features/jbriefs/tests/fixtures/findings/two-reviewers.md` shows the list.
