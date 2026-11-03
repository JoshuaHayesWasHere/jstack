#!/bin/sh

input=$(cat)
here=$(realpath "$0") || {
  echo "infra-files: refused: the hook cannot find itself, so it cannot judge the call" >&2
  exit 2
}
source=${here%/features/jleak/hooks/*}
hook=infra-files
[ -r "$source/features/jbus/hooks/judge.sh" ] || {
  echo "infra-files: refused: $source has no features/jbus/hooks/judge.sh to judge the call with" >&2
  exit 2
}
. "$source/features/jbus/hooks/judge.sh"
judge jleak --infra
