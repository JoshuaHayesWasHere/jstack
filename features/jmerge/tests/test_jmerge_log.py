"""`jmerge` logs each line it prints in `merge.log`, but a pull request that waits or is held
says so on every pass. So `jmerge` logs such a line only when it is not the last one logged
for that pull request, and still prints every line, as before.

The tests run the command against the fake `gh` and real origin of `test_home_merge`."""

import json

import test_home_merge as merge


def test_a_wait_is_logged_once_and_again_when_its_reason_changes(merged):
    waits = f"wait 7 {merge.URL}: {merge.NOT_PASSED}"
    merged.home.open_pull_request(merged.head, checks=(merge.PASSED, merge.FAILED))
    assert merged.run() == [waits] and merged.run() == [waits]
    assert [line[17:] for line in merged.log()] == [waits]
    last = merged.home.state / "merge.log.last"
    assert json.loads(last.read_text()) == {"7": waits}
    merged.home.open_pull_request(merged.head)
    (merged.home.tasks / "alpha.md").write_text(merge.brief())
    unreviewed = f"wait 7 {merge.URL}: it has no review yet"
    assert merged.run() == [unreviewed] and merged.run() == [unreviewed]
    assert [line[17:] for line in merged.log()] == [waits, unreviewed]
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
    assert [line[17:] for line in merged.log()] == [waits, unreviewed, said]
