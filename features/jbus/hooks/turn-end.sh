#!/bin/sh

input=$(cat)
here=$(realpath "$0") || exit 0
source=${here%/features/jbus/hooks/*}
hook=turn-end
[ -r "$source/features/jbus/hooks/judge.sh" ] || exit 0
. "$source/features/jbus/hooks/judge.sh"
refuse() { exit 1; }
JSTACK_HOOK_SECONDS=4
said=$(judge jbus.crewend 2>/dev/null) && printf '%s\n' "$said"
exit 0
