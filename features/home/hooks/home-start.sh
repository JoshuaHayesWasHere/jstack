#!/bin/sh

checkout=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)
template=$checkout/templates/hook-message.md

input=$(cat)
[ "$(printf '%s' "$input" | jq -r '.source // empty')" = startup ] || exit 0
[ -n "$T3_CODE_MCP_AUTHORIZATION$T3_MCP_BEARER_TOKEN" ] || exit 0

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || exit 0

scratch=$(cd "$HOME/.t3/scratch" 2>/dev/null && pwd -P)
case $(pwd -P)/ in
"${scratch:-/nowhere}"/*) exit 0 ;;
esac

git_dir=$(git rev-parse --path-format=absolute --git-dir 2>/dev/null) || exit 0
common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
[ "$git_dir" = "$common_dir" ] || exit 0
[ "$(git rev-parse --is-bare-repository 2>/dev/null)" = false ] || exit 0
[ -z "$(git rev-parse --show-superproject-working-tree 2>/dev/null)" ] || exit 0

repo=$(basename "$(dirname "$common_dir")")
home_dir=${JBUS_HOME_DIR:-$HOME/.local/state/home}/$repo
[ ! -e "$home_dir/off" ] || exit 0
first=
[ -f "$home_dir/plan.md" ] || first=1

[ -f "$template" ] || exit 0
repo=$repo home_dir=$home_dir skills=$checkout/skills first=$first awk '
skip {
  skip = 0
  next
}
{
  line = $0
  if (index(line, "$first") == 1) {
    if (!ENVIRON["first"]) next
    line = substr(line, 7)
    skip = 1
  }
  out = ""
  while (match(line, /\$(repo|home_dir|skills)/)) {
    out = out substr(line, 1, RSTART - 1) ENVIRON[substr(line, RSTART + 1, RLENGTH - 1)]
    line = substr(line, RSTART + RLENGTH)
  }
  print out line
}' "$template"
