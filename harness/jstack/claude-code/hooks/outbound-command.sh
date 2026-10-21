#!/bin/sh

input=$(cat)
case $input in
*gh*pr* | *push*) ;;
*) exit 0 ;;
esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")") || exit 2
repo=${repo%/harness/jstack/claude-code}
pythonpath=$repo/harness/jstack/pythonpath
[ -f "$pythonpath" ] || {
  echo "jleak: $pythonpath is missing, so the command is refused" >&2
  exit 2
}
path=
while IFS= read -r folder; do path=${path:+$path:}$repo/$folder; done < "$pythonpath"
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    printf '%s' "$input" |
      PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path \
        "$python" -m jleak --strict --command
    code=$?
    [ "$code" -eq 0 ] || exit 2
    exit 0
  fi
done
echo "jleak: no python 3.12 or newer to check the command with, so it is refused" >&2
exit 2
