#!/bin/sh
# Run one command and keep it as evidence: the command, what it printed, and its exit code.
#   record.sh <name> <command> [arguments]
# It appends to $VERIFY_JSTACK_EVIDENCE/<name>.txt and prints what the command printed. The
# command reads this script's stdin, so a brief or a gate can be piped in. It exits as the
# command did. A new evidence file starts with the setup steps a stand-in did, from the
# skill's "Set up by a stand-in": the proof under them does not cover those.
name=${1:?usage: record.sh <name> <command> [arguments]}
shift
out=${VERIFY_JSTACK_EVIDENCE:?source the sandbox env.sh first}/$name.txt
if [ ! -s "$out" ]; then
  {
    echo "# Set up by a stand-in, so not verified by this run:"
    awk '/^## / {on = ($0 == "## Set up by a stand-in")} on && /^- / {print "# " $0}' \
      "$(dirname "$0")/../SKILL.md"
    echo
  } >"$out"
fi
said=$(mktemp)
"$@" >"$said" 2>&1
code=$?
cat "$said"
{
  echo "\$ $*"
  cat "$said"
  echo "[exit $code, $(date -u +%Y-%m-%dT%H:%M:%SZ)]"
  echo
} >>"$out"
rm -f "$said"
exit "$code"
