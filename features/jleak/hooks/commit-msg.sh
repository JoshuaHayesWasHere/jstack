#!/bin/sh

here=$(readlink -f "$0") || exit 0
source=${here%/features/jleak/hooks/*}
if [ ! -d "$source/features/jleak/src/jleak" ]; then
  python=${source%/share/jstack}/bin/python
  [ "$python" != "$source/bin/python" ] && [ -x "$python" ] || exit 0
  PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jleak --commit-msg "$1"
  exit 0
fi
path=
for folder in "$source"/src "$source"/features/*/src; do
  [ -d "$folder" ] && path=${path:+$path:}$folder
done
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path \
      "$python" -m jleak --commit-msg "$1"
    exit 0
  fi
done
echo "jleak: no python 3.12 or newer, so the commit message is not cleaned" >&2
exit 0
