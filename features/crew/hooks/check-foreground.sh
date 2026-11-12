#!/bin/sh

input=$(cat)
printf '%s' "$input" | grep -Eq '"run_in_background"[[:space:]]*:[[:space:]]*true' || exit 0
case $input in
*'jgauge test-slot'* | *'jgauge check'* | */proved.sh*) ;;
*) exit 0 ;;
esac
echo "check-foreground: refused: a test slot can keep this call waiting past the 30 minutes Claude Code gives a background command, which then stops it: run it in the foreground with \`timeout: 600000\`" >&2
exit 2
