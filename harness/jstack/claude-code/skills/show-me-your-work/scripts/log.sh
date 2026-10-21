#!/bin/sh
# Append one row to a decision log, a TSV file of six columns.
# Usage: log.sh <logfile> <phase> <decision> <why> <evidence> <result>
set -eu

if [ "$#" -ne 6 ]; then
    echo "usage: log.sh <logfile> <phase> <decision> <why> <evidence> <result>" >&2
    exit 1
fi

logfile=${1}
shift
mkdir -p "$(dirname "$logfile")"

# Always `>>`, never `>`: if this test is wrong about a log that has rows, the cost is one
# stray header line and not the rows.
if [ ! -s "$logfile" ]; then
    printf 'ts\tphase\tdecision\twhy\tevidence\tresult\n' >> "$logfile"
fi

# A cell stays on one line, and one that a spreadsheet would read as a formula (it starts
# with =, +, - or @) gets a single quote in front: evidence can be text somebody else wrote.
clean() {
    cell=$(printf '%s' "${1}" | tr '\t\n\r' '   ')
    case $cell in
    [=+@-]*) printf "'%s" "$cell" ;;
    *) printf '%s' "$cell" ;;
    esac
}

printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(clean "${1}")" "$(clean "${2}")" "$(clean "${3}")" "$(clean "${4}")" "$(clean "${5}")" \
    >> "$logfile"
