#!/bin/sh

repo=$(dirname "$(dirname "$(readlink -f "$0")")") || exit 1
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH="$repo/src" \
      exec "$python" -m jleak --strict --push "${2:-${1:-.}}"
  fi
done
echo "jleak: no python 3.12 or newer to check the push with, so it is refused" >&2
exit 1
