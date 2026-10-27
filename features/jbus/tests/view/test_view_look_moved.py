"""The rule of the view's shot test for a browser that moved (`test_view_page_look.drawn_by`),
with a browser's `--version` line in place of a browser: a run that is not a pull request's
fails, with the line jbus reads for its fix row, and any other run skips."""

import pytest

from jbus import watch
from view.page.test_view_page_look import drawn_by

KEPT = "Google Chrome 155.0.8059.39"
THIS = "Google Chrome 156.0.8078.47"
MOVED = f"the shots were drawn by {KEPT}, and this is {THIS}"


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch", "push", "release"])
def test_a_browser_that_moved_fails_a_ci_run_that_is_not_a_pull_requests(monkeypatch, event):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    with pytest.raises(pytest.fail.Exception) as failed:
        drawn_by(KEPT, THIS)
    assert str(failed.value) == f"{MOVED}: {watch.BROWSER.moved}"


def test_a_browser_that_moved_skips_a_pull_requests_run_with_the_line_a_desk_skips_with(
    monkeypatch,
):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    with pytest.raises(pytest.skip.Exception) as skipped:
        drawn_by(KEPT, THIS)
    assert str(skipped.value) == MOVED
    monkeypatch.delenv("CI")
    monkeypatch.delenv("GITHUB_EVENT_NAME")
    with pytest.raises(pytest.skip.Exception) as on_a_desk:
        drawn_by(KEPT, THIS)
    assert str(on_a_desk.value) == MOVED


def test_the_browser_that_drew_the_shots_compares_them_on_any_run(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    assert drawn_by(THIS, THIS) is None
