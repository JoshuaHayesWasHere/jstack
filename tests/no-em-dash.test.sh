#!/usr/bin/env bash
set -u

hook="$(cd "$(dirname "$0")/.." && pwd)/hooks/no-em-dash"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export HOME="$work"
dash=$(printf '\xe2\x80\x94')
printf 'Fixed it %s for good.\n' "$dash" >"$work/dashed.md"
printf 'Fixed it, for good.\n' >"$work/clean.md"

fails=0
pre() {
    jq -n --arg c "$1" --arg cwd "$work" \
        '{hook_event_name: "PreToolUse", tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}' |
        "$hook" claude >/dev/null 2>&1
}
blocks() { if pre "$2"; then echo "FAIL $1"; fails=$((fails + 1)); else echo "ok   $1"; fi; }
allows() { if pre "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }

blocks "a dash in a gh command" "gh pr create --title 'a $dash b'"
blocks "a dash in a --body-file" "gh pr create --title t --body-file dashed.md"
blocks "a dash in a --body-file=" "gh pr edit 5 --body-file=$work/dashed.md"
blocks "a dash in a gh api body=@file" "gh api repos/o/r/pulls -f title=t -F body=@dashed.md"
blocks "a dash in a git commit -F file" "git commit -F \"$work/dashed.md\""
blocks "a dash in a ~/ body file" "gh pr create --body-file ~/dashed.md"
allows "a clean --body-file" "gh pr create --title t --body-file clean.md"
allows "a gh api field that is not a file" "gh api repos/o/r/pulls -F draft=false -F body=@clean.md"
allows "a dash outside git and gh" "echo 'a $dash b'"
allows "a missing body file" "gh pr create --body-file nowhere.md"

echo "$fails failed"
[ "$fails" -eq 0 ]
