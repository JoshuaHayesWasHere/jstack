#!/bin/sh

input=$(cat)
case $input in
*commit* | *gh*pr*) ;;
*) exit 0 ;;
esac
here=$(readlink -f "$0") || exit 2
source=${here%/features/jleak/hooks/*}
if [ ! -d "$source/features/jleak/src/jleak" ]; then
  python=${source%/share/jstack}/bin/python
  [ "$python" != "$source/bin/python" ] && [ -x "$python" ] || {
    echo "jleak: $source is no checkout and no release, so the command is refused" >&2
    exit 2
  }
  printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jleak --trailers
  [ "$?" -eq 0 ] || exit 2
  exit 0
fi
path=
for folder in "$source"/src "$source"/features/*/src; do
  [ -d "$folder" ] && path=${path:+$path:}$folder
done
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    printf '%s' "$input" |
      PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path \
        "$python" -m jleak --trailers
    code=$?
    [ "$code" -eq 0 ] || exit 2
    exit 0
  fi
done
echo "jleak: no python 3.12 or newer to check the command with, so it is refused" >&2
exit 2
