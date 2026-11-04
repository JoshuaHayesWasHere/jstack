#!/bin/sh

input=$(cat)
case $input in
*commit* | *gh*pr*) ;;
*) exit 0 ;;
esac
here=$(realpath "$0") || {
  echo "ai-trailer: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/jleak/hooks/*}
hook=ai-trailer
withheld=1
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "ai-trailer: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
judge jleak --trailers
