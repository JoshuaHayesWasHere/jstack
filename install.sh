#!/bin/sh

version=
github=https://github.com/JoshuaHayesWasHere/jstack

here=$(dirname "$0")
from=
if [ -n "$version" ]; then
  from=${JSTACK_RELEASE_URL:-$github/releases/download/v$version}/jstack-$version-py3-none-any.whl
elif ! { [ -f "$0" ] && [ -f "$here/features/jinstall/src/jinstall/__main__.py" ]; }; then
  from=${JSTACK_GIT_URL:-git+$github@main}
fi
if [ -n "$from" ]; then
  command -v uv >/dev/null 2>&1 || {
    curl -fsSL "${JSTACK_UV_INSTALLER:-https://astral.sh/uv/install.sh}" | sh || {
      echo "missing hard uv -> https://docs.astral.sh/uv/getting-started/installation/"
      exit 1
    }
    PATH=${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH
  }
  uv tool install --reinstall "$from" || exit 1
  bin=$(uv tool dir --bin) || exit 1
  [ "$#" -gt 0 ] || set -- --setup
  exec "$bin/jinstall" "$@"
fi

repo=$(cd "$here" && pwd -P) || exit 1

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

path=
for folder in "$repo"/src "$repo"/features/*/src; do
  [ -d "$folder" ] && path=${path:+$path:}$folder
done
python=$(python_312) || {
  echo "$python"
  exit 1
}
PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 PYTHONPATH=$path exec $python -m jinstall "$repo" "$@"
