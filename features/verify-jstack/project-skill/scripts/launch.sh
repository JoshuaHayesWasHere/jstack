#!/bin/sh
# Make one verify-jstack sandbox and print the line that enters it.
#   launch.sh
# It installs this checkout's commands (uv sync), then makes a new directory under
# ${TMPDIR:-/tmp} that holds everything a drive touches: a HOME, jbus's config and state, a
# demo repo with its origin, a `gh`, a `notify-send`, a `systemctl` and a `launchctl` that are stand-ins, a
# directory for uv's tools, a machine that is idle, and a local stand-in for T3 Code and the webhook. It prints `ready:` only after
# jbus and jmerge have each run in it. Nothing outside it is written
# but the evidence directory, ${TMPDIR:-/tmp}/verify-jstack-evidence/<run>, which cleanup.sh
# keeps. Two sandboxes never share a path or a port, so runs may sit side by side.
# Run it from a shell that is in no sandbox: inside one, HOME and PATH are that sandbox's.
set -eu
if [ -n "${VERIFY_JSTACK_SANDBOX-}" ]; then
  echo "launch.sh: this shell is in the sandbox $VERIFY_JSTACK_SANDBOX: launch from a new shell" >&2
  exit 1
fi
here=$(cd "$(dirname "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel)

uv sync --quiet --project "$repo"
# Where uv keeps its cache and its Pythons on this machine, asked while HOME is still the
# host's: env.sh hands both on, so `uv tool install` in the sandbox writes neither into its HOME.
uv_cache=$(uv cache dir)
uv_pythons=$(uv python dir)

S=$(mktemp -d "${TMPDIR:-/tmp}/verify-jstack.XXXXXX")
# The marker cleanup.sh asks for, written first. A launch that fails from here on tears
# down what it made, so a broken attempt strands no directory and no process.
: >"$S/.verify-jstack-sandbox"
run=$(basename "$S")
E=${TMPDIR:-/tmp}/verify-jstack-evidence/$run
trap 'code=$?; [ "$code" = 0 ] || { echo "launch.sh: failed, tearing down $S" >&2; "$here/cleanup.sh" "$S" >&2; rmdir "$E" 2>/dev/null; }' EXIT
mkdir -p "$E" "$S/home/.local/state/home/demo/tasks" "$S/config" "$S/state" "$S/stub" "$S/gh" \
  "$S/t3" "$S/machine/proc/pressure"

# The stand-ins on PATH. notify-send only writes down what it was asked to show.
ln -s "$here/fake-gh" "$S/stub/gh"
ln -s "$here/fake-systemctl" "$S/stub/systemctl"
ln -s "$here/fake-launchctl" "$S/stub/launchctl"
printf '#!/bin/sh\necho "$*" >> "%s/notify.log"\n' "$S" >"$S/stub/notify-send"
chmod +x "$S/stub/notify-send"
for name in open merged commits; do echo "[]" >"$S/gh/$name.json"; done
echo "{}" >"$S/gh/checks.json"
mkdir "$S/gh/logs"

# A machine with room, and a plan that is under its limits: what `jgauge room` reads.
echo "0.10 0.10 0.10 1/100 1" >"$S/machine/proc/loadavg"
echo "MemAvailable:   33554432 kB" >"$S/machine/proc/meminfo"
for resource in cpu memory; do
  echo "some avg10=0.00 avg60=0.00 avg300=0.00 total=0" >"$S/machine/proc/pressure/$resource"
done
reset=$(($(date +%s) + 3600))
printf 'five_hour 10 %s\nseven_day 10 %s\n' "$reset" "$reset" >"$S/machine/limits"

# The demo project: a main checkout named demo, and the bare repo that is its origin.
export GIT_AUTHOR_NAME=verify GIT_AUTHOR_EMAIL=verify@example.test
export GIT_COMMITTER_NAME=verify GIT_COMMITTER_EMAIL=verify@example.test
git init -q -b main "$S/demo"
git -C "$S/demo" commit -q --allow-empty -m start
git init -q --bare -b main "$S/origin.git"
git -C "$S/demo" remote add origin "$S/origin.git"
git -C "$S/demo" push -q origin main
git -C "$S/demo" fetch -q origin
git -C "$S/demo" remote set-head origin main >/dev/null

# The stand-in for T3 Code and the webhook. Its token is made up here and opens nothing else.
token="sandbox-$run"
PYTHONFAULTHANDLER=1 nohup "$repo/.venv/bin/python" "$here/fake_t3.py" "$S/t3" --token "$token" >"$S/t3/log" 2>&1 &
echo $! >"$S/t3/pid"
tries=0
until [ -s "$S/t3/port" ]; do
  tries=$((tries + 1))
  if [ "$tries" -gt 50 ]; then
    # The trap at the top removes the log with the sandbox, so what it holds is said here.
    echo "launch.sh: the stand-in for T3 Code did not start, and its process is:" >&2
    ps -ww -o pid=,stat=,etime=,command= -p "$(cat "$S/t3/pid")" >&2 || echo "gone" >&2
    # With PYTHONFAULTHANDLER set, SIGABRT writes where each of its threads waits into the log.
    kill -ABRT "$(cat "$S/t3/pid")" 2>/dev/null && sleep 1
    echo "launch.sh: its log said:" >&2
    cat "$S/t3/log" >&2
    exit 1
  fi
  sleep 0.1
done
url=http://127.0.0.1:$(cat "$S/t3/port")

cat >"$S/config/config.toml" <<EOF
server = "$url"
dispatch = true
max_running = 1
runtimeMode = "full-access"
wake = "both"
[[project]]
name = "demo"
checkout = "$S/demo"
state = "demo"
projectId = "00000000-0000-0000-0000-000000000000"
webhook_url = "$url/wake"
webhook_key = "$token"
EOF
printf '{"server": "%s", "token": {"access_token": "%s"}, "obtained_at": %s}\n' \
  "$url" "$token" "$(date +%s)" >"$S/config/t3.json"
chmod 600 "$S/config/config.toml" "$S/config/t3.json"

cat >"$S/env.sh" <<EOF
# Source this in every shell that drives the sandbox $S.
export VERIFY_JSTACK_SANDBOX="$S"
export VERIFY_JSTACK_EVIDENCE="$E"
export VERIFY_JSTACK_REPO="$repo"
export VERIFY_JSTACK_SCRIPTS="$here"
export VERIFY_JSTACK_URL="$url"
export HOME="$S/home"
# What a host may export that outranks HOME for install.sh, uv and the stand-in systemctl:
# unset, each of them is under the sandbox's HOME.
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_BIN_HOME UV_TOOL_BIN_DIR
export JBUS_CONFIG_DIR="$S/config"
export JBUS_STATE_DIR="$S/state"
export JBUS_HOME_DIR="$S/home/.local/state/home"
export PROC="$S/machine/proc"
export LIMITS="$S/machine/limits"
export UV_TOOL_DIR="$S/uv/tools"
export UV_CACHE_DIR="$uv_cache"
export UV_PYTHON_INSTALL_DIR="$uv_pythons"
export PATH="$S/stub:$repo/.venv/bin:\$PATH"
export GIT_AUTHOR_NAME=verify GIT_AUTHOR_EMAIL=verify@example.test
export GIT_COMMITTER_NAME=verify GIT_COMMITTER_EMAIL=verify@example.test
# record <name> <command>: run it and keep it in the evidence file <name>.txt.
record() { "$here/record.sh" "\$@"; }
cd "$S/demo"
EOF

# Ready means a drive can run here, not that the stand-in answers. Two real commands, each
# run as a drive runs them: jbus reads this sandbox's config and state for the project demo,
# and jmerge asks the stand-in gh from the demo checkout. A step that fails is named, and
# the trap above tears down.
usable() {
  if ! said=$( (. "$S/env.sh" && "$@") 2>&1); then
    echo "launch.sh: not ready: \`$*\` failed in the sandbox" >&2
    echo "$said" >&2
    exit 1
  fi
}
usable jbus --project demo queue show
usable jmerge --check
if ! grep -q "^pr list " "$S/gh/calls.log" 2>/dev/null; then
  echo "launch.sh: not ready: \`jmerge --check\` did not ask the stand-in gh" >&2
  exit 1
fi
# A drive starts with no gh call on record: the one above was this probe's.
rm "$S/gh/calls.log"

echo "ready: . $S/env.sh"
