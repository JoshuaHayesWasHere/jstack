#!/bin/sh

input=$(cat)
case $input in
*merge* | *Merge*) ;;
*) exit 0 ;;
esac
here=$(realpath "$0") || {
  echo "merge-command: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/jbus/hooks/*}
hook=merge-command
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "merge-command: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
case $(field command) in
*gh*merge* | *gh*Merge*) ;;
*) exit 0 ;;
esac
judge jbus.mergecall
