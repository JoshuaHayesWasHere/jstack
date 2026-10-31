#!/usr/bin/env bash
# One /home start, with the skills at a commit, in a verify-jstack sandbox.
#
#   home-start.sh <jstack checkout> <out dir> <label> <commit> [--spend] [--model <id>] [--claude-home <dir>]
#
# The skills, templates and source are exported from <commit> with `git archive`, and laid out
# as the install lays them. With no --spend that is all it does: it prints what it would run, and
# no model runs. With --spend, `claude -p /home` runs on them with a config dir that has no
# CLAUDE.md, hooks or memory, HOME the sandbox, and T3 Code's tools absent, the same on each side.
# --max-budget-usd caps one run. --claude-home is the sign-in it uses, by default $HOME/.claude.
# It prints the limits ledger before and after.
# Run it from a shell that has sourced no sandbox env.sh.
set -euo pipefail
usage='usage: home-start.sh <jstack checkout> <out dir> <label> <commit> [--spend] [--model <id>] [--claude-home <dir>]'
[ $# -ge 4 ] || { echo "$usage" >&2; exit 2; }
repo=$(cd "$1" && pwd) out=$2 label=$3 commit=$4
shift 4
spend= model=claude-opus-5-5 claude_home=$HOME/.claude
while [ $# -gt 0 ]; do
  case $1 in
    --spend) spend=yes; shift ;;
    --model) model=$2; shift 2 ;;
    --claude-home) claude_home=$2; shift 2 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done
mkdir -p "$out"
out=$(cd "$out" && pwd)
. "$(dirname "$0")/common.sh"

tree= L= bconf=
finish() {
  ledger after
  rm -rf "$tree" "$L" "$bconf"
}
ledger before
trap finish EXIT

tree=$(mktemp -d "${TMPDIR:-/tmp}/benchmark-tree.XXXXXX")
git -C "$repo" archive "$commit" | tar -x -C "$tree"
L=$(mktemp -d "${TMPDIR:-/tmp}/benchmark-layout.XXXXXX")
mkdir -p "$L/skills" "$L/templates" "$L/playbooks" "$L/principles"
for s in "$tree"/features/*/skills/*/; do cp -r "$s" "$L/skills/"; done
for t in "$tree"/features/*/templates/*; do [ -e "$t" ] && cp -r "$t" "$L/templates/"; done
ln -s "$tree" "$L/source"

if [ -z "$spend" ]; then
  echo "no model: pass --spend to run claude -p /home on $model over $(ls "$L/skills" | wc -l | tr -d ' ') skills at $commit"
  exit 0
fi

bconf=$(throwaway_config "$claude_home")
ln -s "$L/skills" "$bconf/skills"
real_claude=$(command -v claude)
ready=$(env -u VERIFY_JSTACK_SANDBOX "$repo/features/verify-jstack/project-skill/scripts/launch.sh")
(
  . "${ready#ready: . }"
  trap '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh" > /dev/null' EXIT
  mkdir -p "$HOME/.claude"
  ln -s "$L/skills" "$HOME/.claude/skills"
  CLAUDE_CONFIG_DIR=$bconf timeout 540 "$real_claude" -p "/home" \
    --model "$model" --output-format json --max-budget-usd 3 \
    --allowedTools Bash Read Write Edit \
    --no-session-persistence < /dev/null > "$out/$label.json" 2> "$out/$label.err" || true
)
if ! row=$(jq -ce --arg l "$label" --arg c "$commit" '{label: $l, commit: $c, usd: .total_cost_usd, turns: .num_turns, ms: .duration_ms,
  in: .usage.input_tokens, out: .usage.output_tokens, cw: .usage.cache_creation_input_tokens, cr: .usage.cache_read_input_tokens,
  end: (.result // .subtype | .[-300:])}' "$out/$label.json"); then
  jq -cn --arg l "$label" --arg c "$commit" '{label: $l, commit: $c, error: true}' >> "$out/c.jsonl"
  echo "home-start.sh: claude gave no answer: see $out/$label.err" >&2
  exit 1
fi
printf '%s\n' "$row" | tee -a "$out/c.jsonl"
