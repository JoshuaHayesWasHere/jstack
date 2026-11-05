refuse() {
  printf '%s: refused: %s\n' "$hook" "$1" >&2
  logged "$1"
  exit 2
}

judge() {
  seconds=${JSTACK_HOOK_SECONDS:-25}
  module=$1
  run='import os, runpy, signal, sys
def gone(*_):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.killpg(0, signal.SIGTERM)
    os._exit(142)
os.setpgid(0, 0)
signal.signal(signal.SIGALRM, gone)
signal.alarm(int(sys.argv[1]))
sys.argv = sys.argv[2:]
runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)'
  release=1
  for folder in "$source"/features/*/src/"${module%%.*}"; do
    [ -d "$folder" ] && release=
  done
  if [ -n "$release" ]; then
    python=${source%/share/jstack}/bin/python
    [ "$python" != "$source/bin/python" ] && [ -x "$python" ] ||
      refuse "$source is no checkout and no release, so it cannot judge the call"
    set -- "$python" -I -c "$run" "$seconds" "$@"
  else
    path=
    for folder in "$source"/src "$source"/features/*/src; do
      [ -d "$folder" ] && path=${path:+$path:}$folder
    done
    python=
    for one in python3 python; do
      if "$one" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
        python=$one
        break
      fi
    done
    [ -n "$python" ] || refuse "no python 3.12 or newer to judge the call with"
    set -- env PYTHONSAFEPATH=1 "PYTHONPATH=$path" "$python" -c "$run" "$seconds" "$@"
  fi
  exec 3>&1
  said=$(printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$@" 2>&1 >&3)
  code=$?
  exec 3>&-
  [ -z "$said" ] || printf '%s\n' "$said" >&2
  last=${said##*
}
  case $code in
  0) exit 0 ;;
  2)
    logged "$said"
    exit 2
    ;;
  142) refuse "$module ran past $seconds seconds, so it judged nothing" ;;
  *) refuse "$module ended $code${last:+: $last}" ;;
  esac
}

field() {
  printf '%s' "$input" |
    sed -n -E "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"(([^\"\\\\]|\\\\.)*)\".*/\\1/p" |
    head -n 1 |
    sed -e 's/\\[nrt]/ /g' -e 's/\\\(.\)/\1/g'
}

plain() {
  printf '%s' "$1" | LC_ALL=C tr -c '\040-\176' ' ' | LC_ALL=C cut -c "1-$2" |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

logged() {
  for tool in git sed head tr cut date dirname basename; do
    command -v "$tool" >/dev/null 2>&1 || return 0
  done
  cwd=$(field cwd)
  common=$(git -C "${cwd:-.}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) ||
    return 0
  bus=${JBUS_STATE_DIR:-$HOME/.local/state/jbus}/$(basename "$(dirname "$common")")
  [ -d "$bus" ] || return 0
  head=
  if [ -z "$withheld" ]; then
    head=$(field command)
    [ -n "$head" ] || head=$(field file_path)
  fi
  [ -n "$head" ] || head=$(field tool_name)
  head=$(plain "$head" 120)
  reason=$(plain "$1" 2000)
  line=$(printf '{"at": "%s", "event": "hook", "head": "%s", "hook": "%s", "line": "%s refused: %s", "loud": "quiet", "reason": "%s", "slug": "", "text": ""}' \
    "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$head" "$hook" "$hook" "$head" "$reason")
  (
    umask 077
    if command -v flock >/dev/null 2>&1; then flock 9; fi
    printf '%s\n' "$line" >>"$bus/events.jsonl"
  ) 9>>"$bus/outbox.lock" 2>/dev/null
  return 0
}
