#!/bin/sh

here=$(readlink -f "$0") || exit 0
repo=${here%/features/jleak/hooks/*}
[ -d "$repo/features/jleak/src/jleak" ] || exit 0
path=
for folder in "$repo"/src "$repo"/features/*/src; do
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
