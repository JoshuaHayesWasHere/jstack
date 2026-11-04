#!/bin/sh

input=$(cat)
here=$(realpath "$0") || {
  echo "agent-sends: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/home/hooks/*}
hook=agent-sends
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "agent-sends: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
judge jbriefs.sends
