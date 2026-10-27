"""`jmerge` writes the squash commit's message itself: the pull request's title and its
number as the subject, and the branch's commit messages as GitHub's default lists them as the
body, with every AI co-author trailer line taken out and every human co-author line kept. Left
to GitHub, the body is every commit message as it is, trailers and all.

The landing of an integration branch is a merge commit, whose body is the pull request's
title, as GitHub's default has it. In a repo that allows only squashes it is a squash, whose
message `jmerge` writes as it writes any squash's.

The tests run the command against a real origin and a fake `gh` whose merge writes the subject
and the body it was given, read from standard input as `--body-file -` says, as the merged
commit's message."""

import pytest

from jmerge import trailers
from test_jmerge_fresh import LINES, Kitchen, git, url
from test_jmerge_integration import BRANCH, allows, integration

CLAUDE = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HUMAN = "Co-authored-by: Ada Lovelace <ada@example.com>"
AI = [
    CLAUDE,
    "co-authored-by: claude <claude@example.com>",
    "Co-authored-by: Someone <someone@anthropic.com>",
    "Co-authored-by: Codex <codex@example.com>",
    "Co-authored-by: OpenAI <noreply@openai.com>",
    "Co-authored-by: Cursor Agent <cursoragent@cursor.com>",
    "Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>",
    "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    "Generated with Claude Code",
]

GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
case "$1 $2" in
    "pr list")
        if [ "$3" = "--base" ]; then echo "[]"; else cat "$STUB/list.json"; fi ;;
    "repo view") echo main ;;
    "api repos/{owner}/{repo}") cat "$STUB/repo.json" ;;
    "api repos/{owner}/{repo}/commits/"*) echo '{"check_runs": []}' ;;
    "pr merge")
        base=$(jq -r --argjson n "$3" \
            '.[] | select(.number == $n) | .baseRefName' "$STUB/list.json")
        tree=$(git -C "$ORIGIN" merge-tree --write-tree "refs/heads/$base" "$6") || exit 1
        case "$4 $5" in
            "--squash --match-head-commit") parents="-p refs/heads/$base" ;;
            "--merge --match-head-commit") parents="-p refs/heads/$base -p $6" ;;
            *) exit 64 ;;
        esac
        subject="Merge pull request #$3"
        if [ "$7" = "--subject" ]; then subject=$8; shift 2; fi
        [ "$7 $8" = "--body-file -" ] || exit 64
        commit=$({ printf '%s\\n\\n' "$subject"; cat; } \
            | git -C "$ORIGIN" commit-tree "$tree" $parents)
        git -C "$ORIGIN" update-ref "refs/heads/$base" "$commit"
        echo "$commit" > "$STUB/merged-$3" ;;
    "pr view") cat "$STUB/merged-$3" ;;
    *) exit 64 ;;
esac
"""


@pytest.mark.parametrize("line", AI)
def test_each_ai_trailer_is_found_and_taken_out(line):
    message = f"feat: a change\n\nWhy it changed.\n\n{line}\n"
    assert trailers.found(message) == [(5, line)]
    assert trailers.strip(message) == "feat: a change\n\nWhy it changed."


@pytest.mark.parametrize(
    "message",
    [
        "feat: a change\n\nWhy it changed.\n",
        f"feat: a change\n\n{HUMAN}\n",
        "feat: the cursor moves with the copilot of the plane\n",
        "docs: say claude code generated nothing here\n",
        'feat: refuse the footer\n\nA line "Generated with Claude Code" is refused.\n',
        "Co-authored-by: Clauderia Smith <clauderia@example.com>\n",
    ],
)
def test_a_message_with_no_ai_trailer_is_found_clean_and_kept(message):
    assert trailers.found(message) == []
    assert trailers.strip(message) == message.rstrip()


def test_only_the_ai_lines_go_and_a_human_co_author_stays_where_it_was():
    message = f"fix: two\n\n{HUMAN}\n{CLAUDE}\n\n{AI[-2]}\n"
    assert trailers.found(message) == [(4, CLAUDE), (6, AI[-2])]
    assert trailers.strip(message) == f"fix: two\n\n{HUMAN}"


@pytest.fixture
def kitchen(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})
    (kitchen.home.stub / "gh").write_text(GH)
    allows(kitchen, merge=True, squash=True, rebase=True)
    return kitchen


def commit(kitchen, slug, files, message):
    """Another commit on the crewmate's branch, pushed, and the pull request at it."""
    tree = kitchen.tmp / "trees" / slug
    for path, text in files.items():
        (tree / path).write_text(text)
    git(tree, "commit", "-q", "-a", "-m", message)
    git(tree, "push", "-q", "origin", slug)
    head = git(tree, "rev-parse", "HEAD")
    kitchen.pulls[slug]["headRefOid"] = head
    kitchen.brief(slug, head)
    return head


def message(kitchen, branch="main"):
    return git(kitchen.origin, "log", "-1", "--format=%B", f"refs/heads/{branch}")


def test_the_squash_lands_the_title_and_the_branchs_messages_with_no_ai_trailer(kitchen):
    kitchen.crew("alpha", 7, {"a.txt": "ours\n" + LINES})
    commit(kitchen, "alpha", {"b.txt": "one\n"}, f"feat: one\n\nWhy one.\n\n{CLAUDE}")
    two = f"fix: two\n\n{HUMAN}\nCo-authored-by: Codex <codex@openai.com>\n\n{AI[-2]}"
    head = commit(kitchen, "alpha", {"b.txt": "two\n"}, two)
    (said,) = kitchen.run()
    assert said.startswith("merged 7 alpha ")
    assert kitchen.calls() == [
        f"pr merge 7 --squash --match-head-commit {head} --subject feat: alpha (#7)"
        f" --body-file - --repo {kitchen.origin}"
    ]
    assert message(kitchen) == (
        f"feat: alpha (#7)\n\n* alpha\n\n* feat: one\n\nWhy one.\n\n* fix: two\n\n{HUMAN}"
    )
    assert trailers.found(message(kitchen)) == []


def test_the_landing_of_a_branch_is_a_merge_commit_whose_body_is_the_title(kitchen):
    git(kitchen.home.main, "push", "-q", "origin", f"main:{BRANCH}")
    kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    head = commit(kitchen, BRANCH, {"b.txt": "one\n"}, f"feat: one\n\n{CLAUDE}")
    integration(kitchen, BRANCH)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 9 {BRANCH} ")
    assert kitchen.calls() == [
        f"pr merge 9 --merge --match-head-commit {head} --body-file - --repo {kitchen.origin}"
    ]
    assert message(kitchen) == f"Merge pull request #9\n\nfeat: {BRANCH}"


def test_the_squash_landing_of_a_branch_lands_the_title_and_its_messages_with_no_ai_trailer(
    kitchen,
):
    git(kitchen.home.main, "push", "-q", "origin", f"main:{BRANCH}")
    kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    head = commit(kitchen, BRANCH, {"b.txt": "one\n"}, f"feat: one (#6)\n\n{HUMAN}\n{CLAUDE}")
    integration(kitchen, BRANCH)
    allows(kitchen, merge=False, squash=True, rebase=False)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 9 {BRANCH} ")
    assert kitchen.calls() == [
        f"pr merge 9 --squash --match-head-commit {head} --subject feat: {BRANCH} (#9)"
        f" --body-file - --repo {kitchen.origin}"
    ]
    assert message(kitchen) == f"feat: {BRANCH} (#9)\n\n* {BRANCH}\n\n* feat: one (#6)\n\n{HUMAN}"
    assert trailers.found(message(kitchen)) == []


def test_a_branch_whose_messages_cannot_be_read_waits_and_is_never_merged(kitchen):
    kitchen.crew("alpha", 7, {"a.txt": "ours\n" + LINES})
    gone = "f" * 40
    kitchen.pulls["alpha"]["headRefOid"] = gone
    kitchen.brief("alpha", gone)
    (said,) = kitchen.run()
    assert said == f"wait 7 {url(7)}: its commit messages could not be read for the squash"
    assert kitchen.calls() == []
