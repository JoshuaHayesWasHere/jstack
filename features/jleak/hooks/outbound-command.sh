#!/bin/sh

input=$(cat)
case $input in
*gh*pr* | *push*) ;;
*) exit 0 ;;
esac
here=$(realpath "$0") || {
  echo "outbound-command: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/jleak/hooks/*}
hook=outbound-command
withheld=1
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "outbound-command: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
judge jleak --strict --command
