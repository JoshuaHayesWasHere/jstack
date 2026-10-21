#!/bin/sh

skills=$(cd "$(dirname "$0")/../skills" 2>/dev/null && pwd) || exit 0
state=$HOME/.local/state/skill-tips
[ ! -e "$state/off" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0

input=$(cat)
fields=$(printf '%s' "$input" | jq -r '
  select(type == "object")
  | [.session_id, .cwd, .prompt]
  | select(all(type == "string") and (.[:2] | all(contains("\n") | not)))
  | .[2] |= .[:4000]
  | .[]' 2>/dev/null) || exit 0
{
  read -r session
  read -r cwd
  prompt=$(cat)
} <<END
$fields
END

case $session in
"" | off | *[!A-Za-z0-9_-]*) exit 0 ;;
esac
case ${prompt#"${prompt%%[![:space:]]*}"} in
"" | /* | "$"*) exit 0 ;;
esac

cd "$cwd" 2>/dev/null || exit 0
if git_dir=$(git rev-parse --path-format=absolute --git-dir 2>/dev/null); then
  [ "$git_dir" = "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" ] || exit 0
fi

found=$(prompt=$prompt seen=$state/$session awk '
function words(text) {
  text = tolower(text)
  gsub(/[^a-z0-9*]+/, " ", text)
  gsub(/^ | $/, "", text)
  return text
}
BEGIN {
  while ((getline name < ENVIRON["seen"]) > 0) had[name]
  typed = tolower(ENVIRON["prompt"])
  gsub(/[^a-z0-9\/$_-]+/, " ", typed)
  named = " " typed " "
  typed = " " words(typed) " "
}
FNR == 1 {
  head = ($0 == "---")
  name = tip = ""
  next
}
!head { next }
$0 == "---" {
  head = 0
  if (name == "" || tip == "" || name in had) next
  if (index(named, " /" name " ") || index(named, " $" name " ")) next
  count = split(tip, part, "|")
  what = part[1]
  gsub(/^ +| +$/, "", what)
  if (what == "") next
  for (i = 2; i <= count; i++) {
    size = split(words(part[i]), word, " ")
    pattern = ""
    said = 0
    for (j = 1; j <= size; j++) {
      if (word[j] == "*") word[j] = "[a-z0-9]+( [a-z0-9]+)?( [a-z0-9]+)?( [a-z0-9]+)?"
      else said++
      pattern = pattern " " word[j]
    }
    if (said > most && typed ~ (pattern " ")) {
      most = said
      best = name "\t" what
    }
  }
  next
}
/^name: / { name = substr($0, 7) }
/^tip: / { tip = substr($0, 6) }
END { if (most) print best }' "$skills"/*/SKILL.md 2>/dev/null) || exit 0
[ -n "$found" ] || exit 0

IFS=$(printf '\t') read -r name what <<END
$found
END
if [ -n "$T3_CODE_MCP_AUTHORIZATION$T3_MCP_BEARER_TOKEN" ]; then
  say='{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: (
    "The user has a skill that fits what they just typed. Start your reply with this one line for them, as written: `"
    + $line + "`. It is for the user to type. Do not invoke that skill yourself and do not act on the line: "
    + "after it, answer the message as you would have with no tip.")}}'
else
  say='{systemMessage: $line}'
fi
out=$(jq -cn --arg line "tip: /$name $what" "$say" 2>/dev/null) || exit 0
mkdir -p "$state" 2>/dev/null || exit 0
echo "$name" 2>/dev/null >>"$state/$session" || exit 0
printf '%s' "$out"
exit 0
