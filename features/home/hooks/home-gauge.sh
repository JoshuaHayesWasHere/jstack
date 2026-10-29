#!/bin/sh

[ -n "$T3_CODE_MCP_AUTHORIZATION$T3_MCP_BEARER_TOKEN" ] || exit 0

state=${JBUS_HOME_DIR:-$HOME/.local/state/home}
checkout=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd -P)
fields=$(jq -r --arg state "$state/" --arg checkout "${checkout:-/nowhere}/" '
  def t3: IN("t3_thread_configuration", "list_scheduled_tasks", "update_scheduled_task",
    "delete_scheduled_task", "t3_thread_list", "t3_thread_send", "t3_thread_update",
    "t3_thread_organize");
  def whole:
    select(startswith("/")) | split("/")
    | reduce .[] as $part ([];
        if $part == ".." then .[:-1] elif $part | IN("", ".") then . else . + [$part] end)
    | "/" + join("/");
  def handoff:
    (.tool_name | strings) as $tool
    | (.tool_input | objects) as $input
    | if $tool | IN("Bash", "ToolSearch") then true
      elif $tool == "Skill" then $input.skill == "handoff"
      elif $tool | IN("Read", "Write", "Edit") then
        $input.file_path | strings | whole as $path
        | any(
            $state, (select($tool == "Read") | $checkout + ("templates/", "skills/"));
            . as $root | $path | startswith($root)
          )
      elif $tool | test("^mcp__t3[-_]code__") | not then false
      elif $tool | endswith("__t3_thread_launch") then
        any(
          ($input.message | strings | test("^/home(\\s|$)")),
          ($input.title | strings | startswith("home: "));
          .
        )
      else $tool | sub("^mcp__t3[-_]code__"; "") | t3 end;
  select(type == "object" and .agent_id == null)
  | [.cwd, .transcript_path, .session_id, .hook_event_name, (first(handoff) // false | tostring)]
  | select(all(type == "string" and (contains("\n") | not)))
  | .[]' 2>/dev/null) || exit 0
{
  IFS= read -r cwd
  IFS= read -r transcript
  IFS= read -r session
  IFS= read -r event
  IFS= read -r handoff
} <<END
$fields
END

case $session in
"" | *[!A-Za-z0-9_-]*) exit 0 ;;
esac
cwd=${CLAUDE_PROJECT_DIR:-$cwd}
[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || exit 0
[ ! -e CHARTER.md ] || exit 0

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
home_dir=$state/$repo
[ ! -e "$home_dir/off" ] || exit 0

limit=
ceiling=
if [ -r "$home_dir/limit" ]; then
  {
    IFS= read -r limit
    IFS= read -r ceiling
  } <"$home_dir/limit"
fi
case $limit in
"" | *[!0-9]*) limit=300000 ;;
esac
case $ceiling in
"" | *[!0-9]*) ceiling=350000 ;;
esac
[ "$ceiling" -ge "$limit" ] || ceiling=$limit

[ -r "$transcript" ] || exit 0
call='def call: select(.type == "assistant") | .message | objects
  | select((.id | strings) != "" and (.usage | type) == "object")
  | select((.model | strings) != "<synthetic>")
  | [.usage["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]
      | numbers | select(. >= 0)]
  | add // 0;'
count=$(tail -c 262144 "$transcript" 2>/dev/null |
  jq -Rn "$call"'input | last(inputs | fromjson? | objects | call) // empty' 2>/dev/null)
case $count in
"")
  count=$(jq -Rn "$call"'[inputs | select(test("\\S"))] as $lines
    | [$lines[] | fromjson? | objects] as $entries
    | select($lines == [] or $entries != [])
    | last($entries[] | call) // 0' "$transcript" 2>/dev/null) || exit 0
  ;;
esac
case $count in
"" | *[!0-9]*) exit 0 ;;
esac

if mkdir -p "$home_dir" 2>/dev/null; then
  echo "$count $limit $session $(date +%s)" 2>/dev/null >"$home_dir/gauge.$$" &&
    mv "$home_dir/gauge.$$" "$home_dir/gauge" 2>/dev/null
fi

if [ "$event" = PreToolUse ]; then
  [ "$count" -ge "$ceiling" ] && [ "$handoff" != true ] || exit 0
  line="context: $count tokens, over this home's ceiling of $ceiling."
  line="$line Only the handoff runs now: read $checkout/skills/handoff/SKILL.md and do its steps."
  jq -cn --arg event "$event" --arg line "$line" '{hookSpecificOutput: {
    hookEventName: $event, permissionDecision: "deny", permissionDecisionReason: $line}}' 2>/dev/null
  exit 0
fi

[ "$count" -ge "$limit" ] || exit 0
line="context: $count tokens, over this home's limit of $limit."
line="$line Finish the step in hand, then read $checkout/skills/handoff/SKILL.md and do its steps. Start nothing new."
jq -cn --arg event "$event" --arg line "$line" \
  '{hookSpecificOutput: {hookEventName: $event, additionalContext: $line}}' 2>/dev/null
exit 0
