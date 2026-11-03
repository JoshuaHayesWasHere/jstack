# The one way a refusing hook judges a tool call. Such a hook sets `hook` (its name), `input`
# (what the harness gave it on stdin) and `source` (jstack's source tree), sources this file, and
# calls `judge <module> [<argument>...]`, which ends the hook.
#
# The module reads the call on stdin and ends 0 to let it through, or 2 to refuse it with its
# reason on stderr. A hook that cannot judge refuses: a module that ends any other way, one that
# runs past JSTACK_HOOK_SECONDS (25 by default, inside the 30 the harness gives the hook), and a
# machine with no python 3.12 or newer each refuse the call too.
#
# Each refusal adds one quiet `hook` event (`jbus.door.EVENTS`) to the jbus log of the repo the
# call ran in, where jbus keeps one: the hook, the head of the call and the reason. It is written
# here and not in Python, so a refusal for want of Python is logged too, and it is plain ASCII,
# since jbus reads the log as UTF-8 and a cut could split a character.

refuse() {
  printf '%s: refused: %s\n' "$hook" "$1" >&2
  logged "$1"
  exit 2
}

judge() {
  seconds=${JSTACK_HOOK_SECONDS:-25}
  module=$1
  release=1
  for folder in "$source"/features/*/src/"${module%%.*}"; do
    [ -d "$folder" ] && release=
  done
  if [ -n "$release" ]; then
    python=${source%/share/jstack}/bin/python
    [ "$python" != "$source/bin/python" ] && [ -x "$python" ] ||
      refuse "$source is no checkout and no release, so it cannot judge the call"
    set -- "$python" -I -m "$@"
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
    set -- env PYTHONSAFEPATH=1 "PYTHONPATH=$path" "$python" -m "$@"
  fi
  if command -v timeout >/dev/null 2>&1; then
    set -- timeout -k 2 "$seconds" "$@"
  fi
  said=$(mktemp) || refuse "no temporary file to keep what $module says"
  printf '%s' "$input" | PYTHONDONTWRITEBYTECODE=1 "$@" 2>"$said"
  code=$?
  cat "$said" >&2
  reason=$(cat "$said")
  last=$(tail -n 1 "$said")
  rm -f "$said"
  case $code in
  0) exit 0 ;;
  2)
    logged "$reason"
    exit 2
    ;;
  124 | 137) refuse "$module ran past $seconds seconds, so it judged nothing" ;;
  *) refuse "$module ended $code${last:+: $last}" ;;
  esac
}

# The value of `"<key>": "<value>"` in the call, its first, with its escapes read.
field() {
  printf '%s' "$input" |
    sed -n -E "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"(([^\"\\\\]|\\\\.)*)\".*/\\1/p" |
    head -n 1 |
    sed -e 's/\\[nrt]/ /g' -e 's/\\\(.\)/\1/g'
}

# `$1` as the inside of a JSON string, printable ASCII only, cut to `$2` characters.
plain() {
  printf '%s' "$1" | LC_ALL=C tr -c '\040-\176' ' ' | LC_ALL=C cut -c "1-$2" |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

logged() {
  cwd=$(field cwd)
  common=$(git -C "${cwd:-.}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) ||
    return 0
  bus=${JBUS_STATE_DIR:-$HOME/.local/state/jbus}/$(basename "$(dirname "$common")")
  [ -d "$bus" ] || return 0
  head=$(field command)
  [ -n "$head" ] || head=$(field file_path)
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
