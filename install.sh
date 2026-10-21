#!/bin/sh

version=
github=https://github.com/JoshuaHayesWasHere/jstack

if [ -n "$version" ]; then
  release=${JSTACK_RELEASE_URL:-$github/releases/download/v$version}
  command -v uv >/dev/null 2>&1 || {
    curl -fsSL "${JSTACK_UV_INSTALLER:-https://astral.sh/uv/install.sh}" | sh || {
      echo "missing hard uv -> https://docs.astral.sh/uv/getting-started/installation/"
      exit 1
    }
    PATH=${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH
  }
  uv tool install --reinstall "$release/jstack-$version-py3-none-any.whl" || exit 1
  bin=$(uv tool dir --bin) || exit 1
  [ "$#" -gt 0 ] || set -- --setup
  exec "$bin/jinstall" "$@"
fi

here=$(dirname "$0")
[ -f "$0" ] && [ -f "$here/features/jinstall/src/jinstall/__main__.py" ] || {
  echo "missing hard a checkout of jstack around $0 -> curl -fsSL $github/releases/latest/download/install.sh | sh"
  exit 1
}
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
