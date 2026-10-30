#!/bin/sh

LIMITS=${LIMITS:-$HOME/.local/state/claude/limits}

seen=$(jq -r '
  .rate_limits | objects | to_entries[]
  | select(.key == "five_hour" or .key == "seven_day")
  | select(.value | objects | [.used_percentage, .resets_at] | all(type == "number" and . >= 0))
  | "\(.key) \(.value.used_percentage * 100 | round / 100) \(.value.resets_at | floor)"' 2>/dev/null) || exit 0
[ -n "$seen" ] || exit 0

home=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
while [ "${home%/}" != "$home" ]; do home=${home%/}; done
settings=${T3CODE_HOME:-$HOME/.t3}/userdata/settings.json
instance=$(jq -r --arg home "$home" --arg user "$HOME" '
  def plain: (if . == "~" then $user elif startswith("~/") then $user + .[1:] else . end) | sub("/+$"; "");
  [.providerInstances | objects | to_entries[] | select(.value.driver == "claudeAgent")
    | select((.value.config.homePath // ($user + "/.claude") | plain) == $home) | .key] | first // empty
' "$settings" 2>/dev/null)
if [ -z "$instance" ] && [ "$home" = "$HOME/.claude" ]; then instance=claudeAgent; fi
case $instance in
claudeAgent) ;;
"" | *[!A-Za-z0-9_-]*) exit 0 ;;
*) LIMITS=$LIMITS.$instance ;;
esac
[ ! -d "$LIMITS" ] || exit 0

kept=$(cat "$LIMITS" 2>/dev/null)
merged=$(printf '%s\n%s\n' "$kept" "$seen" | awk '
  NF == 3 && ($1 == "five_hour" || $1 == "seven_day") && $2 ~ /^[0-9]+(\.[0-9]+)?$/ && $3 ~ /^[0-9]+$/ {
    if (!($1 in resets) || $3 - resets[$1] >= 300) {
      used[$1] = $2
      resets[$1] = $3
    } else if ($3 - resets[$1] > -300) {
      if ($2 + 0 > used[$1] + 0) used[$1] = $2
      if ($3 + 0 > resets[$1] + 0) resets[$1] = $3
    }
  }
  END {
    if ("five_hour" in resets) print "five_hour", used["five_hour"], resets["five_hour"]
    if ("seven_day" in resets) print "seven_day", used["seven_day"], resets["seven_day"]
  }' 2>/dev/null) || exit 0
[ -n "$merged" ] && [ "$merged" != "$kept" ] || exit 0

mkdir -p "$(dirname "$LIMITS")" 2>/dev/null || exit 0
next=$LIMITS.$$
trap 'rm -f "$next" 2>/dev/null' EXIT
trap 'exit 0' HUP INT TERM
{ printf '%s\n' "$merged" >"$next" && mv -f "$next" "$LIMITS"; } 2>/dev/null
exit 0
