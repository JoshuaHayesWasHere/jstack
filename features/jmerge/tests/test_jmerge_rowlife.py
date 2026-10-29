"""The user's word lifts what jbus shows as Needs you (simplify-4's RowLife rule WordLiftsHold),
replayed against the real `jmerge` in the kitchen of `test_jmerge_accept_act` (a real origin, a
fake `gh`, a jbus config whose project is the kitchen's main checkout).

A reason on the `hold` step is one `jmerge` prints as `hold`, so `jmerge --accept` takes it:
`Review: none` and a repo whose auto-merge is off were printed as `wait`, and the accept refused
them as not held. A held draft was never marked ready, so its accept waited on `draft` for good:
the accept now lifts its hold and marks it ready, and it merges once its check passed.
"""

import json

from test_jmerge_accept_act import PROOF, accept, held, kitchen, last  # noqa: F401  (the fixture)
from test_jmerge_fresh import LINES, url


def test_review_none_is_held_and_the_users_accept_merges_it(kitchen):  # noqa: F811
    held(kitchen, "gamma", 8, {"a.txt": "ours\n" + LINES}, mode="none")
    out = accept(kitchen, 8)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 8 {url(8)}: its brief says Review: none"), out
    assert [call.split()[2] for call in kitchen.calls()] == ["8"]
    assert last(kitchen) == ("accept", "home", "typed", "done")


def test_a_repo_whose_auto_merge_is_off_holds_and_the_users_accept_merges(kitchen):  # noqa: F811
    (kitchen.home.state / "merge-off").write_text("")
    held(kitchen, "delta", 9, {"a.txt": "ours\n" + LINES})
    out = accept(kitchen, 9)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert [call.split()[2] for call in kitchen.calls()] == ["9"]


def test_an_accept_of_a_held_draft_lifts_its_hold_and_readies_it(kitchen):  # noqa: F811
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
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    (said,) = kitchen.run()
    assert said.startswith("merged 7 "), said
    assert [call.split()[2] for call in kitchen.calls()] == ["7"]
