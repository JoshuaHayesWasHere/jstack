#!/bin/sh

repo=$(dirname "$(dirname "$(readlink -f "$0")")") || exit 1
[ -d "$repo/src/jleak" ] || {
  echo "jleak: $repo is no checkout of jstack, so the push is refused" >&2
  exit 1
}
path=
for folder in "$repo"/src "$repo"/features/*/src; do
  [ -d "$folder" ] && path=${path:+$path:}$folder
done
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path \
      exec "$python" -m jleak --strict --push "${2:-${1:-.}}"
  fi
done
echo "jleak: no python 3.12 or newer to check the push with, so it is refused" >&2
exit 1
