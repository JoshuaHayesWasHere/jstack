# What the replay and the home start run share. Sourced, never run.

# The limits ledger of every instance, from the real HOME: run it outside a sandbox's env.sh.
ledger() {
  limits=${LIMITS:-$HOME/.local/state/claude/limits}
  echo "limits ledger $1:"
  found=
  for file in "$limits" "$limits".*; do
    [ -f "$file" ] || continue
    found=yes
    sed "s/^/  ${file##*/} /" "$file"
  done
  [ -n "$found" ] || echo "  none at $limits"
}

# A throwaway Claude config dir whose sign-in is the one in the given home (a link, so a refresh
# writes the shared file as any other session on that account does). No CLAUDE.md, skills, hooks,
# plugins or memory. It prints the directory.
throwaway_config() {
  conf=$(mktemp -d "${TMPDIR:-/tmp}/benchmark-claude.XXXXXX")
  ln -s "$1/.credentials.json" "$conf/.credentials.json"
  account=$1/.claude.json
  [ -f "$account" ] || account=$1/../.claude.json
  jq '{hasCompletedOnboarding: true, oauthAccount, userID}' "$account" > "$conf/.claude.json"
  echo "$conf"
}
