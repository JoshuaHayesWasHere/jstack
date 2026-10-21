#!/bin/sh

input=$(cat)
case $input in
*gh*pr* | *push*) ;;
*) exit 0 ;;
esac
copy=$(dirname "$(dirname "$(readlink -f "$0")")") || exit 2
repo=${copy%/harness/jstack/claude-code}
pythonpath=$repo/harness/jstack/pythonpath
if [ ! -f "$pythonpath" ]; then
  python=${copy%/share/jstack/claude-code}/bin/python
  [ "$python" != "$copy/bin/python" ] && [ -x "$python" ] || {
    echo "jleak: $copy is no checkout's copy and no release's, so the command is refused" >&2
    exit 2
  }
  printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jleak --strict --command
  [ "$?" -eq 0 ] || exit 2
  exit 0
fi
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
