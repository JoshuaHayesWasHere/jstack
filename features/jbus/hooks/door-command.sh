#!/bin/sh

input=$(cat)
lower=$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')
case $lower in
*prod* | *deploy* | *push* | *filter-repo* | *drop* | *s3* | *delete* | *branch* | *worktree* | \
  *tailscale* | *tailnet* | *tag:* | *auth\ key* | *record* | *_api_* | *release* | \
  *publish* | *upload* | *apply* | *pulumi*) ;;
*) exit 0 ;;
esac
here=$(realpath "$0") || {
  echo "door-command: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/jbus/hooks/*}
hook=door-command
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "door-command: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
judge jbus.door
