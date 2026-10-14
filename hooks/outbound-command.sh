#!/bin/sh

input=$(cat)
case $input in
*gh*pr* | *push*) ;;
*) exit 0 ;;
esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")") || exit 2
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    printf '%s' "$input" |
      PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH="$repo/src" \
        "$python" -m jleak --strict --command
    code=$?
    [ "$code" -eq 0 ] || exit 2
    exit 0
  fi
done
echo "jleak: no python 3.12 or newer to check the command with, so it is refused" >&2
exit 2
