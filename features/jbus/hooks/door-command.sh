#!/bin/sh

input=$(cat)
lower=$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')
case $lower in
*prod* | *deploy* | *push* | *filter-repo* | *drop* | *s3* | *delete* | *branch* | *worktree* | \
  *tailscale* | *tailnet* | *tag:* | *auth\ key* | *record* | *_api_* | *release* | \
  *publish* | *upload* | *apply* | *pulumi*) ;;
*) exit 0 ;;
esac
here=$(realpath "$0") || exit 0
source=${here%/features/jbus/hooks/*}
if [ ! -d "$source/features/jbus/src/jbus" ]; then
  python=${source%/share/jstack}/bin/python
  [ "$python" != "$source/bin/python" ] && [ -x "$python" ] || exit 0
  printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$python" -I -m jbus.door
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
        "$python" -m jbus.door
    [ "$?" -eq 2 ] && exit 2
    exit 0
  fi
done
exit 0
