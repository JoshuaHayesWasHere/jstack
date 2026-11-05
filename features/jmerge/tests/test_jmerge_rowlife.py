"""The user's word lifts what jbus shows as Needs you (simplify-4's RowLife rule WordLiftsHold),
replayed against the real `jmerge` (`jmerge.cli`) in the kitchen of `test_jmerge_accept_act` (a
real origin, a fake `gh`, a jbus config whose project is the kitchen's main checkout).

A reason on the `hold` step is one `jmerge` prints as `hold`, so `jmerge --accept` takes it:
`Review: none` was printed as `wait`, and the accept refused it as not held. jmerge marks no
draft ready, so the accept of a held draft lifts its hold and names the draft it still waits on.
"""

import json

import test_jmerge_accept_act as accept_act
from jmerge import ready
from test_jmerge_accept_act import PROOF, accept, held, last
from test_jmerge_fresh import LINES, url

kitchen = accept_act.kitchen


def test_review_none_is_held_and_the_users_accept_merges_it(kitchen):
    held(kitchen, "gamma", 8, {"a.txt": "ours\n" + LINES}, mode="none")
    out = accept(kitchen, 8)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 8 {url(8)}: its brief says Review: none"), out
    assert [call.split()[2] for call in kitchen.calls()] == ["8"]
    assert last(kitchen) == ("accept", "home", "typed", "done")


def test_the_users_accept_merges_a_review_none_brief_that_has_no_review(kitchen):
    """A `Review: none` brief has no review, so no `## Review` section and no proof in one:
    the user's word is all it waits on, and the accept merges it."""
    unreviewed(kitchen)
    out = accept(kitchen, 8)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 8 {url(8)}: its brief says Review: none"), out
    assert [call.split()[2] for call in kitchen.calls()] == ["8"]


def test_merge_off_stops_the_accept_of_a_review_none_brief_that_has_no_review(kitchen):
    unreviewed(kitchen)
    (kitchen.home.state / "merge-off").write_text("")
    out = accept(kitchen, 8)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out[-1] == f"wait 8 {url(8)}: {ready.MERGE_OFF}", out
    assert kitchen.calls() == []


def unreviewed(kitchen):
    """Gamma's pull request 8, held for the user's word: its brief says `Review: none` and has
    no `## Review` section."""
    kitchen.crew("gamma", 8, {"a.txt": "ours\n" + LINES})
    task = kitchen.home.tasks / "gamma.md"
    task.write_text(
        '# gamma: a task\nReview: none\nTask: "do it"\nPull request: open one when done\n\n'
        f"## Result\nStatus: done\nBranch: gamma   Pull request: {url(8)}\n"
    )
    (said,) = kitchen.run()
    assert said.startswith(f"hold 8 {url(8)}: {ready.REVIEW_NONE}"), said


def listed(kitchen):
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))


def test_an_accept_of_a_held_draft_lifts_its_hold_and_still_waits_on_the_draft(kitchen):
    """Beta, a draft someone opened by hand, held because GitHub listed 1 of its 3 files. The
    user's accept lifts the hold, and the draft is all it then waits on: jmerge names that wait,
    merges nothing and marks nothing ready, and keeps no record of the accept. The next pass holds
    it again."""
    kitchen.crew("beta", 7, {"a.txt": "ours\n" + LINES})
    kitchen.pulls["beta"] |= {"changedFiles": 3, "isDraft": True}
    kitchen.brief("beta", kitchen.pulls["beta"]["headRefOid"])
    with (kitchen.home.tasks / "beta.md").open("a") as brief:
        brief.write(PROOF)
    (said,) = kitchen.run()
    assert said.startswith("hold 7 ") and "GitHub listed 1 of the 3 files" in said, said

    out = accept(kitchen, 7)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out == [f"wait 7 {url(7)}: {ready.HAND_DRAFT}"], out
    assert not kitchen.calls() and not kitchen.calls("pr ready")
    listed(kitchen)
    (said,) = kitchen.run()
    assert said.startswith("hold 7 ") and "GitHub listed 1 of the 3 files" in said, said
    assert sorted(path.name for path in kitchen.home.state.glob("accept*")) == []


def holds(kitchen):
    """The pull requests `holds.json` keeps a head for."""
    path = kitchen.home.state / "holds.json"
    return sorted(json.loads(path.read_text())) if path.exists() else []


def gone_and_held(kitchen, slug):
    """Take `slug`'s pull request off GitHub's open list, open gamma's as 8 with `Review: none`,
    and run a pass, which holds gamma."""
    del kitchen.pulls[slug]
    kitchen.crew("gamma", 8, {"b.txt": "theirs\n"})
    task = kitchen.home.tasks / "gamma.md"
    task.write_text(task.read_text().replace("Task:", "Review: none\nTask:", 1) + PROOF)
    listed(kitchen)
    (said,) = kitchen.run()
    assert said.startswith("hold 8 "), said


def test_a_pass_drops_the_hold_of_a_pull_request_closed_unmerged_and_keeps_an_open_ones(kitchen):
    held(kitchen, "alpha", 6, {"a.txt": "ours\n" + LINES}, mode="none")
    assert holds(kitchen) == ["6"]
    gone_and_held(kitchen, "alpha")
    assert holds(kitchen) == ["8"]


def test_a_pass_drops_the_hold_of_a_pull_request_that_merged_and_keeps_an_open_ones(kitchen):
    held(kitchen, "alpha", 6, {"a.txt": "ours\n" + LINES}, mode="none")
    out = accept(kitchen, 6)
    assert out[0].startswith(f"accepted 6 {url(6)}"), (out, kitchen.home.stderr)
    gone_and_held(kitchen, "alpha")
    assert holds(kitchen) == ["8"]
