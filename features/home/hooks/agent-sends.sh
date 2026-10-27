#!/bin/sh

input=$(cat)
here=$(realpath "$0") || exit 0
source=${here%/features/home/hooks/*}
if [ ! -d "$source/features/jbriefs/src/jbriefs" ]; then
  python=${source%/share/jstack}/bin/python
  [ "$python" != "$source/bin/python" ] && [ -x "$python" ] || exit 0
  printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jbriefs.sends
  [ "$?" -eq 2 ] && exit 2
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
        "$python" -m jbriefs.sends
    [ "$?" -eq 2 ] && exit 2
    exit 0
  fi
done
exit 0
