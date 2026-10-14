#!/bin/sh

repo=$(cd "$(dirname "$0")" && pwd -P) || exit 1

python_312() {
  for python in python3 python; do
    if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
      echo "$python"
      return
    fi
  done
  if command -v uv >/dev/null 2>&1; then
    echo "uv run --no-project --python 3.12 python"
    return
  fi
  echo "missing hard python -> 3.12 or newer, or uv, which brings one"
  return 1
}

python=$(python_312) || {
  echo "$python"
  exit 1
}
PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH="$repo/src" exec $python -m jinstall "$repo" "$@"
