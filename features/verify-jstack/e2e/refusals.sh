#!/usr/bin/env bash
# What the harness refuses, so that a drive never lands on an instance it did not make: a launch
# from a shell already in a sandbox, a cleanup of a path that is not whole, a cleanup of a
# directory launch.sh did not make, and a cleanup whose recorded pid is now another process,
# here the other sandbox's stand-in. Each refusal leaves the thing it refused untouched.
#   bash features/verify-jstack/e2e/refusals.sh
# It follows Poteto's create-verification-skill, section 1's Isolate ("refusing to double-drive a
# shared instance beats corrupting the user's session") and section 2's Cleanup ("Never kill by
# process name; kill what you started"), with maintain-verification-skill's third live-pass
# invariant: residue is cleaned, and only the residue.
. "$(dirname "$0")/lib.sh"

launch a
launch b
dir_a=$(inside a sh -c 'echo "$VERIFY_JSTACK_SANDBOX"')
pid_a=$(standin a)
pid_b=$(standin b)
strays+=("$pid_a")
sandboxes() { find "$TMPDIR" -maxdepth 1 -name 'verify-jstack.*' | wc -l | tr -d ' '; }

step a sh -c '"$VERIFY_JSTACK_SCRIPTS/launch.sh"'
check "a launch inside a made no third sandbox" [ "$(sandboxes)" = 2 ]

step host sh -c 'cd "$TMPDIR" && "$1/cleanup.sh" "$(basename "$2")"' _ "$SCRIPTS" "$dir_a"
check "a's sandbox is still there after a cleanup by a part of its path" [ -f "$dir_a/.verify-jstack-sandbox" ]

mkdir "$TMPDIR/verify-jstack.notmine"
echo kept >"$TMPDIR/verify-jstack.notmine/work"
step host "$SCRIPTS/cleanup.sh" "$TMPDIR/verify-jstack.notmine"
check "a directory with no marker keeps its files" [ "$(cat "$TMPDIR/verify-jstack.notmine/work")" = kept ]

echo "\$ [host] give a's pid file b's stand-in, as a pid the system gave again"
echo "$pid_b" >"$dir_a/t3/pid"
step a sh -c '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"'
check "b's stand-in still runs after a's cleanup" alive "$pid_b"
doctor b
check "a's own stand-in was not stopped by name either" alive "$pid_a"
kill "$pid_a"
check "a's stand-in stops by its own pid" gone "$pid_a"

step b sh -c '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"'
check "b's stand-in is stopped" gone "$pid_b"
finish
