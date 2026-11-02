"""After a merge, `jmerge` brings the main checkout up to the merged commit. Another fetch in that
checkout can write FETCH_HEAD between the pull's own fetch and its merge, naming several branches,
as a fetch of two branches does. The tests run `jmerge` as `tests/test_home_merge.py` runs it,
against its fake `gh` and a temporary origin."""

from test_home_merge import git, merged_line

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
