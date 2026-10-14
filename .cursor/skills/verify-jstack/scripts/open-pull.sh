#!/bin/sh
# Give the sandbox's GitHub one open pull request, number 7, for the branch <slug>.
#   open-pull.sh <slug> <path it changes> [<conclusion of the check named check>]
# The conclusion is SUCCESS unless told (FAILURE, or any other GitHub gives). It writes
# $VERIFY_JSTACK_SANDBOX/gh/open.json and prints the head commit the pull request is at,
# which a brief's Review section names on its `Head:` line.
slug=${1:?usage: open-pull.sh <slug> <path> [<conclusion>]}
path=${2:?usage: open-pull.sh <slug> <path> [<conclusion>]}
head=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
jq -n --arg slug "$slug" --arg path "$path" --arg head "$head" --arg said "${3:-SUCCESS}" '[{
  number: 7, url: "https://example.test/pull/7", title: "feat: \($slug)",
  headRefName: $slug, headRefOid: $head, baseRefName: "main",
  mergeable: "MERGEABLE", isDraft: false, changedFiles: 1,
  files: [{path: $path, additions: 1, deletions: 0, changeType: "MODIFIED"}],
  statusCheckRollup: [{__typename: "CheckRun", name: "check", status: "COMPLETED", conclusion: $said}]
}]' >"${VERIFY_JSTACK_SANDBOX:?source the sandbox env.sh first}/gh/open.json"
echo "$head"
