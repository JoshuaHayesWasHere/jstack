#!/bin/sh

here=$(realpath "$0") || exit 1
lint=${here%/*}/pre-push-lint.sh
refs=
while IFS= read -r line; do
  refs="$refs$line
"
done
given() { printf '%s' "$refs"; }
source=${here%/features/jleak/hooks/*}
if [ ! -d "$source/features/jleak/src/jleak" ]; then
  python=${source%/share/jstack}/bin/python
  [ "$python" != "$source/bin/python" ] && [ -x "$python" ] || {
    echo "jleak: $source is no checkout and no release, so the push is refused" >&2
    exit 1
  }
  given | PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jleak --strict --push "${2:-${1:-.}}" || exit 1
  given | sh "$lint"
  exit
fi
path=
for folder in "$source"/src "$source"/features/*/src; do
  [ -d "$folder" ] && path=${path:+$path:}$folder
done
for python in python3 python; do
  if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    given | PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path \
      "$python" -m jleak --strict --push "${2:-${1:-.}}" || exit 1
    given | sh "$lint"
    exit
  fi
done
echo "jleak: no python 3.12 or newer to check the push with, so it is refused" >&2
exit 1
