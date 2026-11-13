#!/bin/sh

[ -n "$CLAUDE_ENV_FILE" ] || exit 0
here=$(realpath "$0") || exit 0
bin=${here%/hooks/gh-logged.sh}/bin
[ -x "$bin/gh" ] || exit 0
printf "export PATH='%s':\"\$PATH\"\n" "$bin" >>"$CLAUDE_ENV_FILE"
