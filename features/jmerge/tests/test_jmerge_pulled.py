"""After a merge, `jmerge` brings the main checkout up to the merged commit. Another fetch in that
checkout can write FETCH_HEAD between the pull's own fetch and its merge, naming several branches,
as a fetch of two branches does. The tests run `jmerge` as `tests/test_home_merge.py` runs it,
against its fake `gh` and a temporary origin."""

from test_home_merge import git, merged_as, merged_line

OTHER_FETCH = """\
#!/bin/sh
[ "$1" = committed ] || exit 0
dir=$(git rev-parse --absolute-git-dir)
while read -r old new ref; do
    [ "$ref" = refs/remotes/origin/main ] && [ "$new" != {start} ] || continue
    if [ ! -e "$dir/other-fetch" ]; then
        : > "$dir/other-fetch"
        printf '%s\\t\\tbranch main of origin\\n%s\\t\\tbranch alpha of origin\\n' \\
            "$new" {head} > "$dir/FETCH_HEAD"
    fi
done
"""


def test_a_fetch_head_of_two_branches_written_mid_pull_still_leaves_main_pulled(merged):
    """A `reference-transaction` hook stands in for the other fetch: when the post-merge fetch
    moves `origin/main` to the merged commit, it writes a FETCH_HEAD of two branches for merge,
    once. `git pull --ff-only` then fails with "Cannot fast-forward to multiple branches", or with
    "Cannot rebase onto multiple branches" where `pull.rebase` is set."""
    hooks = merged.home.main / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "reference-transaction"
    hook.write_text(OTHER_FETCH.format(start=merged.start, head=merged.head))
    hook.chmod(0o755)
    said = merged.run()
    commit, pulled = merged.on_main()
    assert (merged.home.main / ".git" / "other-fetch").exists()
    assert said == [merged_line(commit)]
    assert pulled == commit
    assert git(merged.home.main, "rev-parse", "--abbrev-ref", "HEAD") == "main"


OTHER_FETCH_MOVES_THE_REF = """\
#!/bin/sh
[ "$1" = preparing ] || exit 0
dir=$(git rev-parse --absolute-git-dir)
[ -e "$dir/other-fetch" ] && exit 0
while read -r old new ref; do
    [ "$ref" = refs/remotes/origin/main ] && [ "$new" != {start} ] || continue
    : > "$dir/other-fetch"
    git update-ref refs/remotes/origin/main {head}
done
"""

REFUSED_EACH_TIME = """\
#!/bin/sh
[ "$1" = prepared ] || exit 0
dir=$(git rev-parse --absolute-git-dir)
while read -r old new ref; do
    [ "$ref" = refs/remotes/origin/main ] && [ "$new" != {start} ] || continue
    echo refused >> "$dir/refused"
    exit 1
done
"""


def _hook(merged, text):
    hooks = merged.home.main / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "reference-transaction"
    hook.write_text(text.format(start=merged.start, head=merged.head))
    hook.chmod(0o755)


def test_a_fetch_that_moves_origin_main_mid_pull_is_waited_out_and_main_is_pulled(merged):
    """The hook stands in for another fetch in the main checkout: before the post-merge fetch
    locks `origin/main`, it moves that ref, once, so git refuses the update with "cannot lock ref
    'refs/remotes/origin/main': is at <new> but expected <old>". `jmerge` fetches again and pulls,
    and the merged line carries no not-pulled note."""
    _hook(merged, OTHER_FETCH_MOVES_THE_REF)
    said = merged.run()
    commit, pulled = merged.on_main()
    assert (merged.home.main / ".git" / "other-fetch").exists()
    assert said == [merged_line(commit)]
    assert pulled == commit


def test_a_fetch_that_fails_for_another_reason_gives_the_not_pulled_note_at_once(merged):
    """The hook refuses every update of `origin/main` to the merged commit. That is no lock
    another fetch holds, so `jmerge` tries the fetch once and writes the not-pulled note."""
    _hook(merged, REFUSED_EACH_TIME)
    (said,) = merged.run()
    commit, pulled = merged.on_main()
    assert (merged.home.main / ".git" / "refused").read_text() == "refused\n"
    assert pulled == merged.start
    note = "the main checkout was not pulled after the merge ("
    assert said.startswith(f"{merged_as(commit)}, {note}")
    assert "cannot lock ref" not in said
