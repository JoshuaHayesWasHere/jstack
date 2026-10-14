#!/bin/sh
# Is this sandbox worth driving? Read-only: one `ok` or `bad` line for each thing a drive
# leans on and for each feature's seed, then `doctor: ok`, or `doctor: not ok` and exit 1.
#   doctor.sh        in a shell that sourced the sandbox's env.sh
S=${VERIFY_JSTACK_SANDBOX-}
bad=0
say() {
  if [ "$1" = ok ]; then echo "ok   $2"; else
    echo "bad  $2"
    bad=1
  fi
}
is() { if eval "$2" >/dev/null 2>&1; then say ok "$1"; else say bad "$1"; fi; }
inside() { case $1 in "$S"/*) return 0 ;; *) return 1 ;; esac }

if [ -z "$S" ] || [ ! -d "$S" ]; then
  echo "bad  no sandbox: run launch.sh, then source the env.sh it names"
  echo "doctor: not ok"
  exit 1
fi
is "HOME is in the sandbox ($HOME)" 'inside "$HOME"'
is "jbus config, state and home are in the sandbox" \
  'inside "$JBUS_CONFIG_DIR" && inside "$JBUS_STATE_DIR" && inside "$JBUS_HOME_DIR"'
is "the machine and the plan jgauge reads are the sandbox's" 'inside "$PROC" && inside "$LIMITS"'
is "gh is the stand-in ($(command -v gh))" '[ "$(command -v gh)" = "$S/stub/gh" ]'
is "notify-send is the stand-in" '[ "$(command -v notify-send)" = "$S/stub/notify-send" ]'
is "systemctl is the stand-in" '[ "$(command -v systemctl)" = "$S/stub/systemctl" ]'
is "the units, the state, uv's tools and its bin directory are in the sandbox" \
  'inside "${XDG_CONFIG_HOME:-$HOME/.config}/" && inside "${XDG_STATE_HOME:-$HOME/.local/state}/" &&
    inside "${UV_TOOL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/uv/tools}/" &&
    inside "${UV_TOOL_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}/"'
for tool in jbus jmerge jgauge jbriefs; do
  is "$tool is this checkout's ($(command -v $tool))" \
    '[ "$(command -v $tool)" = "$VERIFY_JSTACK_REPO/.venv/bin/$tool" ]'
done
pid=$(cat "$S/t3/pid" 2>/dev/null)
is "the stand-in for T3 Code is the process this sandbox started (pid $pid)" \
  'tr "\0" " " < "/proc/$pid/cmdline" | grep -qF "fake_t3.py $S/t3"'
is "it answers at $VERIFY_JSTACK_URL for this sandbox" \
  'curl -fsS "$VERIFY_JSTACK_URL/health" | grep -qF "$S/t3"'
is "jbus reads the sandbox's config: project demo" \
  'jbus queue show | grep -q "^| slug"'
is "the evidence directory is outside the sandbox ($VERIFY_JSTACK_EVIDENCE)" \
  '[ -d "$VERIFY_JSTACK_EVIDENCE" ] && ! inside "$VERIFY_JSTACK_EVIDENCE"'
# The seed each feature's journey needs, from its `Needs:` line. A sandbox that lacks one
# cannot support that journey, which is then reported as failed and never driven around it.
# A recipe edits the seed (it empties machine/limits, rewrites gh/open.json), and a drive
# ends with this check, so each test is of what every such edit keeps: that the file is
# there, and for JSON that it is still a list. It exits 64 for a name it has no check for.
seed() {
  case $1 in
  demo) git -C "$S/demo" rev-parse -q --verify origin/main ;;
  config) grep -q '^name = "demo"$' "$S/config/config.toml" && [ -s "$S/config/t3.json" ] ;;
  tasks) [ -d "$S/home/.local/state/home/demo/tasks" ] ;;
  home) [ -d "$S/home" ] ;;
  gh/open.json | gh/merged.json | t3/threads.json) jq -e 'type == "array"' "$S/$1" ;;
  machine/proc)
    [ -s "$S/$1/loadavg" ] && [ -s "$S/$1/meminfo" ] && [ -s "$S/$1/pressure/memory" ]
    ;;
  machine/limits) [ -f "$S/$1" ] ;;
  *) return 64 ;;
  esac
}
for feature in "$(dirname "$0")"/../features/*.md; do
  name=$(basename "$feature" .md)
  if [ "$name" = README ]; then continue; fi
  needs=$(sed -n 's/^Needs: //p' "$feature" | head -n 1 | tr -d '`,')
  if [ -z "$needs" ]; then say bad "$name: no Needs: line says which seed its journey relies on"; fi
  lacks=0
  for needed in $needs; do
    seed "$needed" >/dev/null 2>&1
    case $? in
    0) continue ;;
    64) say bad "$name: its Needs: line names $needed, which doctor.sh has no check for" ;;
    *) say bad "$name: seed lacks $needed" ;;
    esac
    lacks=1
  done
  if [ -n "$needs" ] && [ "$lacks" = 0 ]; then say ok "$name: seed has $needs"; fi
done
echo "build $(git -C "$VERIFY_JSTACK_REPO" rev-parse --short HEAD) $(git -C "$VERIFY_JSTACK_REPO" status --porcelain | wc -l) uncommitted"
if [ "$bad" = 0 ]; then echo "doctor: ok"; else
  echo "doctor: not ok"
  exit 1
fi
