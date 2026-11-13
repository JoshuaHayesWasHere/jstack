#!/bin/sh

# Each line this hook appends to CLAUDE_ENV_FILE runs at the head of every Bash command:
# the gh shim on PATH, and `jgauge cap-shell $$`, which caps the command's shell at a full
# slot's workers (features/jgauge/src/jgauge/slotlog.py, `cap_shell`). The cap's line is
# written only where cgroup v2 is mounted and jgauge is on PATH, and only once.

[ -n "$CLAUDE_ENV_FILE" ] || exit 0
here=$(realpath "$0") || exit 0
bin=${here%/hooks/gh-logged.sh}/bin
[ -x "$bin/gh" ] && printf "export PATH='%s':\"\$PATH\"\n" "$bin" >>"$CLAUDE_ENV_FILE"
[ -f /sys/fs/cgroup/cgroup.controllers ] || exit 0
jgauge=$(command -v jgauge) || exit 0
line="'$jgauge' cap-shell \$\$ 2>/dev/null"
grep -qxF "$line" "$CLAUDE_ENV_FILE" 2>/dev/null || printf '%s\n' "$line" >>"$CLAUDE_ENV_FILE"
exit 0
