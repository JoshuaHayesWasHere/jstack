#!/bin/sh
# Tear one sandbox down: stop the stand-in for T3 Code that it started, and remove its
# directory. The evidence directory is kept, and its path and files are printed.
#   cleanup.sh [<sandbox>]     default: $VERIFY_JSTACK_SANDBOX
# It stops only the process whose pid launch.sh wrote down, and only while that pid is
# still the stand-in of this sandbox. It removes only a directory that holds the marker
# launch.sh writes first, .verify-jstack-sandbox.
# The sandbox is named by its whole path: the stand-in is found by it, and so is the evidence.
S=${1:-${VERIFY_JSTACK_SANDBOX:?name the sandbox, or source its env.sh first}}
case $S in
/*) ;;
*)
  echo "cleanup.sh: name the sandbox by its whole path, from /: $S" >&2
  exit 1
  ;;
esac
if [ -d "$S" ] && [ ! -f "$S/.verify-jstack-sandbox" ]; then
  echo "cleanup.sh: $S is not a sandbox launch.sh made: it has no .verify-jstack-sandbox" >&2
  exit 1
fi
E=$(dirname "$S")/verify-jstack-evidence/$(basename "$S")
if [ -d "$S" ]; then
  pid=$(cat "$S/t3/pid" 2>/dev/null)
  if [ -n "$pid" ] && tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -qF "fake_t3.py $S/t3"; then
    kill "$pid" && echo "stopped the stand-in for T3 Code (pid $pid)"
  else
    echo "the stand-in for T3 Code was not running"
  fi
  cd / && rm -rf "$S" && echo "removed $S"
else
  echo "no sandbox at $S"
fi
echo "evidence kept: $E"
ls -l "$E"
