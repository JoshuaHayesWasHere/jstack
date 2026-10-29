"""The user's word lifts what jbus shows as Needs you (simplify-4's RowLife rule WordLiftsHold),
replayed against the real `jmerge` in the kitchen of `test_jmerge_accept_act` (a real origin, a
fake `gh`, a jbus config whose project is the kitchen's main checkout).

A reason on the `hold` step is one `jmerge` prints as `hold`, so `jmerge --accept` takes it:
`Review: none` was printed as `wait`, and the accept refused it as not held. A held draft was
never marked ready, so its accept waited on `draft` for good: the accept now lifts its hold and
marks it ready, and it merges once its check passed.
"""

import json

import test_jmerge_accept_act as accept_act
from test_jmerge_accept_act import PROOF, accept, held, last
from test_jmerge_fresh import LINES, git, url, write

kitchen = accept_act.kitchen


def test_review_none_is_held_and_the_users_accept_merges_it(kitchen):
    held(kitchen, "gamma", 8, {"a.txt": "ours\n" + LINES}, mode="none")
    out = accept(kitchen, 8)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 8 {url(8)}: its brief says Review: none"), out
    assert [call.split()[2] for call in kitchen.calls()] == ["8"]
    assert last(kitchen) == ("accept", "home", "typed", "done")


def accepted_draft(kitchen):
    """Beta, a draft held because GitHub listed 1 of its 3 files, which the user accepted: it is
    marked ready and its accept is kept at its head, and it has not merged."""
    gh = kitchen.home.stub / "gh"
    gh.write_text(
        gh.read_text().replace("    *) exit 64 ;;\n", '    "pr ready") ;;\n    *) exit 64 ;;\n')
    )
    kitchen.crew("beta", 7, {"a.txt": "ours\n" + LINES})
    kitchen.pulls["beta"] |= {"changedFiles": 3, "isDraft": True}
    kitchen.brief("beta", kitchen.pulls["beta"]["headRefOid"])
    with (kitchen.home.tasks / "beta.md").open("a") as brief:
        brief.write(PROOF)
    (said,) = kitchen.run()
    assert said.startswith("hold 7 ") and "GitHub listed 1 of the 3 files" in said, said
    assert not kitchen.calls("pr ready")

    out = accept(kitchen, 7)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert kitchen.calls("pr ready"), out
    assert not kitchen.calls(), "it merged before its check ran"
    assert last(kitchen) == ("accept", "home", "typed", "done")
    kitchen.pulls["beta"]["isDraft"] = False


def listed(kitchen):
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))


def kept(kitchen):
    """The pull requests whose accept is kept."""
    path = kitchen.home.state / "accepted.json"
    return sorted(json.loads(path.read_text())) if path.exists() else []


def test_an_accept_of_a_held_draft_lifts_its_hold_and_readies_it(kitchen):
    accepted_draft(kitchen)
    assert kept(kitchen) == ["7"]
    listed(kitchen)
    (said,) = kitchen.run()
    assert said.startswith("merged 7 "), said
    assert [call.split()[2] for call in kitchen.calls()] == ["7"]
    assert kept(kitchen) == []


def test_a_hold_that_comes_after_a_drafts_accept_at_the_same_head_still_holds(kitchen):
    accepted_draft(kitchen)
    task = kitchen.home.tasks / "beta.md"
    task.write_text(task.read_text().replace("Task:", "Review: none\nTask:", 1))
    listed(kitchen)
    (said,) = kitchen.run()
    assert said.startswith("hold 7 ") and "Review: none" in said, said
    assert not kitchen.calls()


def test_a_push_after_a_drafts_accept_holds_it_again_and_drops_the_accept(kitchen):
    accepted_draft(kitchen)
    tree = kitchen.tmp / "trees" / "beta"
    write(tree, {"a.txt": "ours, again\n" + LINES})
    git(tree, "commit", "-q", "-am", "again")
    git(tree, "push", "-q", "origin", "beta")
    head = git(tree, "rev-parse", "HEAD")
    kitchen.pulls["beta"]["headRefOid"] = head
    kitchen.brief("beta", head)
    with (kitchen.home.tasks / "beta.md").open("a") as brief:
        brief.write(PROOF)
    (said,) = kitchen.run()
    assert said.startswith("hold 7 ") and "GitHub listed 1 of the 3 files" in said, said
    assert not kitchen.calls()
    assert kept(kitchen) == []


def test_a_drafts_accept_goes_when_its_pull_request_closes_unmerged(kitchen):
    accepted_draft(kitchen)
    kitchen.crew("gamma", 8, {"b.txt": "theirs\n"})
    del kitchen.pulls["beta"]
    listed(kitchen)
    kitchen.run()
    assert kept(kitchen) == []
