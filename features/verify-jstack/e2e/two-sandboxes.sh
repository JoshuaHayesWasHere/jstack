#!/usr/bin/env bash
# Two sandboxes side by side, each taken through the skill's whole loop as an agent types it:
# Launch, Doctor, a recorded drive, the evidence kept, Cleanup. Then it checks what no test
# reads: a cleanup after a good drive stops its own stand-in and removes its own sandbox, keeps
# the evidence, and leaves the other sandbox driving.
#   bash features/verify-jstack/e2e/two-sandboxes.sh
# It follows Poteto's create-verification-skill, section 4 (prove the skill once end to end, and
# confirm the evidence outlives the cleanup) and section 1's Isolate (two instances side by side),
# with maintain-verification-skill's live-pass invariants: doctor before the first drive, the
# evidence survives every cleanup, nothing a drive started outlives it.
. "$(dirname "$0")/lib.sh"

launch a
launch b
port_a=$(inside a sh -c 'cat "$VERIFY_JSTACK_SANDBOX/t3/port"')
port_b=$(inside b sh -c 'cat "$VERIFY_JSTACK_SANDBOX/t3/port"')
dir_a=$(inside a sh -c 'echo "$VERIFY_JSTACK_SANDBOX"')
dir_b=$(inside b sh -c 'echo "$VERIFY_JSTACK_SANDBOX"')
evidence_a=$(inside a sh -c 'echo "$VERIFY_JSTACK_EVIDENCE"')
evidence_b=$(inside b sh -c 'echo "$VERIFY_JSTACK_EVIDENCE"')
pid_a=$(standin a)
pid_b=$(standin b)
check "a and b have their own directory" [ "$dir_a" != "$dir_b" ]
check "a and b have their own port" [ "$port_a" != "$port_b" ]
check "a and b have their own evidence directory" [ "$evidence_a" != "$evidence_b" ]

doctor a
doctor b

brief alpha | step a record drive jbus queue add alpha --priority 1
brief beta | step b record drive jbus queue add beta --priority 1
step a record drive jbus queue show
step b record drive jbus queue show
rows_a=$(inside a jbus queue show | sed -n 's/^| \([a-z]*\) | [0-9].*/\1/p' | tr '\n' ' ')
rows_b=$(inside b jbus queue show | sed -n 's/^| \([a-z]*\) | [0-9].*/\1/p' | tr '\n' ' ')
check "a's queue shows alpha alone" [ "$rows_a" = "alpha " ]
check "b's queue shows beta alone" [ "$rows_b" = "beta " ]

step a sh -c 'cp "$JBUS_STATE_DIR/demo/queue.json" "$VERIFY_JSTACK_EVIDENCE/" && "$VERIFY_JSTACK_SCRIPTS/doctor.sh" >"$VERIFY_JSTACK_EVIDENCE/doctor.txt"'
step a sh -c '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"'
check "a's stand-in is stopped" gone "$pid_a"
check "a's sandbox is gone" [ ! -e "$dir_a" ]
check "a's evidence outlives its cleanup" \
  [ -s "$evidence_a/drive.txt" -a -s "$evidence_a/queue.json" -a -s "$evidence_a/doctor.txt" ]
check "b's stand-in still runs" alive "$pid_b"
doctor b
step b jbus queue show

echo "\$ [host] the drive a recorded, under the list of what a stand-in set up"
sed '/^#/d' "$evidence_a/drive.txt" | tidy

step b sh -c '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"'
check "b's stand-in is stopped" gone "$pid_b"
check "b's evidence outlives its cleanup" [ -s "$evidence_b/drive.txt" ]
check "a's evidence holds a's drive and not b's" \
  sh -c 'grep -q "alpha" "$1" && ! grep -q "beta" "$1"' _ "$evidence_a/drive.txt"
finish
