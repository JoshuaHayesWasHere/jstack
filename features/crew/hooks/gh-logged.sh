#!/bin/sh
# At a Claude Code session's start, put the crew's gh (bin/gh) first on the PATH of the session's
# Bash shells, through the file Claude Code sources before each command, so an agent's own gh
# call writes its line to jbus's gh-calls.jsonl as jbus's calls do.

[ -n "$CLAUDE_ENV_FILE" ] || exit 0
here=$(realpath "$0") || exit 0
bin=${here%/hooks/gh-logged.sh}/bin
[ -x "$bin/gh" ] || exit 0
printf "export PATH='%s':\"\$PATH\"\n" "$bin" >>"$CLAUDE_ENV_FILE"
