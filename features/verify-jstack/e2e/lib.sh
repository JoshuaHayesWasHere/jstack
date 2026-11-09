# Sourced by each script of this folder, never run. It gives a script a scratch TMPDIR of its
# own, the helpers that launch, drive and clean up a sandbox, and `tidy`, which masks what
# changes from run to run (paths, pids, ports, times, the commit), so that two runs print the
# same lines. Real paths go to stderr; stdout is the transcript a reviewer diffs.
set -u
E2E=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPTS=$(cd "$E2E/../project-skill/scripts" && pwd -P)
REPO=$(git -C "$E2E" rev-parse --show-toplevel)
export UV_OFFLINE=1
for name in $(env | sed -n 's/^\(VERIFY_JSTACK_[A-Z_]*\)=.*/\1/p'); do unset "$name"; done
TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/verify-jstack-e2e.XXXXXX")
export TMPDIR
echo "scratch, kept with its evidence: $TMPDIR" >&2

masks=()
mask() { masks+=("$1" "$2"); }
mask_last() { last+=("$1" "$2"); }
last=()
failed=0
started=()
strays=()

tidy() {
  local line i all
  all=(${masks[@]+"${masks[@]}"} "${last[@]}")
  while IFS= read -r line || [ -n "$line" ]; do
    i=0
    while [ "$i" -lt "${#all[@]}" ]; do
      line=${line//"${all[$i]}"/${all[$((i + 1))]}}
      i=$((i + 2))
    done
    printf '%s\n' "$line"
  done | sed -E \
    -e 's/\(pid [0-9]+\)/(pid <pid>)/g' \
    -e 's#127\.0\.0\.1:[0-9]+#127.0.0.1:<port>#g' \
    -e 's/, [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z\]$/]/' \
    -e 's/^build [0-9a-f]+ [0-9]+ uncommitted$/build <commit> <n> uncommitted/' \
    -e '/^total [0-9]+$/d' \
    -e 's/^[-d][rwx-]{9}.* ([^ ]+)$/file \1/'
}

# launch <label>: make a sandbox, mask its path, evidence, token and name as <label>,
# <label>-evidence, <label>-token and <label>-name, and set env_<label> to its env.sh. The masks
# go longest first: the evidence path and the token hold the sandbox's name.
launch() {
  local said env sandbox
  if ! said=$("$SCRIPTS/launch.sh" 2>&1); then
    printf '%s\n' "$said" >&2
    echo "FAIL launch $1"
    exit 1
  fi
  env=${said#ready: . }
  sandbox=$(dirname "$env")
  started+=("$sandbox")
  echo "sandbox $1: $sandbox" >&2
  mask "$TMPDIR/verify-jstack-evidence/$(basename "$sandbox")" "<$1-evidence>"
  mask "$sandbox" "<$1>"
  mask "sandbox-$(basename "$sandbox")" "<$1-token>"
  mask "$(basename "$sandbox")" "<$1-name>"
  eval "env_$1=\$env"
  echo "launched $1: ready"
}

# inside <label> <command...>: run it in that sandbox's shell, as a drive types it after `. env.sh`.
# The label host runs it in a shell that is in no sandbox.
inside() {
  local env
  if [ "$1" = host ]; then
    shift
    "$@"
    return
  fi
  eval "env=\$env_$1"
  shift
  bash -c '. "$1" && shift && "$@"' _ "$env" "$@"
}

# step <label> <command...>: print the command, what it printed, and its exit code, tidied.
step() {
  local code
  echo "\$ [$1] ${*:2}" | tidy
  inside "$@" 2>&1 | tidy
  code=${PIPESTATUS[0]}
  echo "[exit $code]"
  return 0
}

# check <what> <test...>: one line, ok or FAIL, and a FAIL fails the script.
check() {
  local what=$1
  shift
  if "$@"; then
    echo "ok   $what"
  else
    echo "FAIL $what"
    failed=1
  fi
}

# doctor <label>: run Doctor in that sandbox and print every line but its ok lines, tidied.
doctor() {
  local code
  echo "\$ [$1] doctor.sh, its lines but the ok ones"
  inside "$1" "$SCRIPTS/doctor.sh" 2>&1 | tidy | sed '/^ok /d'
  code=${PIPESTATUS[0]}
  echo "[exit $code]"
  return 0
}

# standin <label>: the pid of that sandbox's stand-in for T3 Code, as launch.sh wrote it down.
standin() { inside "$1" sh -c 'cat "$VERIFY_JSTACK_SANDBOX/t3/pid"'; }

alive() { kill -0 "$1" 2>/dev/null; }

gone() {
  local tries=0
  while alive "$1"; do
    tries=$((tries + 1))
    [ "$tries" -gt 50 ] && return 1
    sleep 0.1
  done
}

# A brief that warns of nothing, so the transcript holds only what the commands did.
brief() {
  printf '# %s: a demo task\nTask: %s, a demo task\nDone when:\n- `judged: a demo`\nProves it: `judged: a demo`\nSize: S\nWhere: `src/%s/`\nDesign: none, a demo\nReview: none\nPlaybook: none\nPull request: none\nHome: uncategorized\n' "$1" "$1" "$1"
}

# On any exit, clean up each sandbox this script launched that is still there. The evidence stays.
teardown() {
  local sandbox pid
  for sandbox in ${started[@]+"${started[@]}"}; do
    [ -d "$sandbox" ] && "$SCRIPTS/cleanup.sh" "$sandbox" >&2
  done
  for pid in ${strays[@]+"${strays[@]}"}; do
    alive "$pid" && kill "$pid"
  done
  return 0
}
trap teardown EXIT

finish() {
  if [ "$failed" = 0 ]; then
    echo "e2e: ok"
  else
    echo "e2e: FAIL"
    exit 1
  fi
}

mask_last "$TMPDIR" "<tmp>"
mask_last "$REPO" "<repo>"
