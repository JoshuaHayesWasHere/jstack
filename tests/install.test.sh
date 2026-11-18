#!/usr/bin/env bash
# Runs ./install and the hooks against a throwaway $HOME, so nothing real changes.
# Usage: bash tests/install.test.sh
set -u

repo=$(cd "$(dirname "$0")/.." && pwd -P)
home=$(mktemp -d)
had_settings=0; [ -e "$repo/settings.json" ] && had_settings=1
cleanup() { rm -rf "$home"; [ "$had_settings" -eq 1 ] || rm -f "$repo/settings.json"; }
trap cleanup EXIT
export HOME="$home"
mkdir -p "$HOME/.codex" "$HOME/.cursor"
touch "$HOME/.codex/config.toml"
echo '{"version": 1, "hooks": {"stop": [{"command": "mine"}]}}' >"$HOME/.cursor/hooks.json"

fails=0
check() { # check <description> <command...>
    local desc=$1; shift
    if "$@" >/dev/null 2>&1; then echo "ok   $desc"; else echo "FAIL $desc"; fails=$((fails + 1)); fi
}
not() { ! "$@"; }
install() { "$repo/install" "$@" 2>&1; }
only_would() { ! grep -v '^would: ' <<<"$1" | grep -q .; }
hook_count() { jq "[.. | objects | select(.command? // \"\" | test(\"/hooks/no-em-dash \"))] | length" "$1"; }
has_codex() { command -v codex >/dev/null; }

out=$(install --dry-run)
check "a dry run only says what it would do" only_would "$out"
check "a dry run creates nothing" not test -e "$HOME/.claude"
[ "$had_settings" -eq 1 ] || check "a dry run copies no settings" not test -e "$repo/settings.json"

install >/dev/null
check "skills are linked" test -L "$HOME/.claude/skills/full-send"
check "Claude gets both hooks" test "$(hook_count "$HOME/.claude/settings.json")" = 2
check "Codex gets both hooks" test "$(hook_count "$HOME/.codex/hooks.json")" = 2
check "Cursor gets both hooks" test "$(hook_count "$HOME/.cursor/hooks.json")" = 2
check "a Cursor hook that is not ours survives" grep -q '"mine"' "$HOME/.cursor/hooks.json"
if has_codex; then
    check "Codex trusts both hooks" test "$(grep -c trusted_hash "$HOME/.codex/config.toml")" = 2
fi
check "a second run prints nothing" test -z "$(install)"

if has_codex; then
    sed -i '0,/trusted_hash = "[^"]*"/s//trusted_hash = "sha256:0"/' "$HOME/.codex/config.toml"
    check "a stale Codex trust is renewed" grep -q '^codex   trusted ' <<<"$(install)"
    check "and the run after is quiet again" test -z "$(install)"
fi

dash=$'\u2014'
hook() { "$repo/hooks/no-em-dash" "$1" <<<"$2" >/dev/null 2>&1; }
blocked() { not hook "$@"; }
says() { "$repo/hooks/no-em-dash" "$1" <<<"$2" 2>/dev/null | grep -q "$3"; }
edit() { jq -nc --arg e "$1" --arg t "$2" --arg o "$3" --arg n "$4" \
    '{hook_event_name: $e, tool_name: $t, tool_input: {file_path: "/f", old_string: $o, new_string: $n}}'; }
shell() { jq -nc --arg e "$1" --arg c "$2" '{hook_event_name: $e, tool_name: "Bash", tool_input: {command: $c}}'; }
patch() { jq -nc --arg p "$1" '{hook_event_name: "PostToolUse", tool_name: "apply_patch", tool_input: {command: $p}}'; }

check "an edit that writes an em dash is flagged" blocked claude "$(edit PostToolUse Edit a "a $dash b")"
check "an edit that removes one passes" hook claude "$(edit PostToolUse Edit "a $dash b" "a, b")"
check "a commit message with one is blocked" blocked claude "$(shell PreToolUse "git commit -m 'a $dash b'")"
check "a search for one is allowed" hook claude "$(shell PreToolUse "grep '$dash' f")"
check "a Codex patch adding one is flagged" blocked codex "$(patch "*** Begin Patch
+a $dash b
*** End Patch")"
check "a Codex patch removing one passes" hook codex "$(patch "*** Begin Patch
-a $dash b
+a, b
*** End Patch")"
check "Cursor hears about an edit through additional_context" \
    says cursor "$(edit postToolUse StrReplace a "a $dash b" | jq -c '.cursor_version = "3"')" additional_context
check "Cursor is denied a commit with one" \
    says cursor "$(shell preToolUse "git commit -m '$dash'" | jq -c '.cursor_version = "3"')" '"deny"'
check "the Claude entry steps aside inside Cursor" \
    hook claude "$(edit postToolUse Write a "a $dash b" | jq -c '.cursor_version = "3"')"

if [ "$fails" -ne 0 ]; then echo "$fails failed"; exit 1; fi
echo "all passed"
