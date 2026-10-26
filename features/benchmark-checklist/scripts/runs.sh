#!/bin/sh
# Time one command, or two in turn (A, B, A, B, ...), and print every run and each side's
# median, range and count of failed runs, tab-separated.
# Usage: runs.sh <rounds> <command A> [<command B>]
# Each command is one argument, run by `sh -c` in this directory. Of what a run prints, its
# last line is kept, in the column `said`: a command that ends by printing its count of work
# done shows there that the work happened.
set -eu

usage() {
    echo "usage: runs.sh <rounds> <command A> [<command B>]" >&2
    exit 1
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then usage; fi
rounds=${1}
case $rounds in
"" | *[!0-9]* | 0) usage ;;
esac
shift

each=$(mktemp)
out=$(mktemp)
trap 'rm -f "$each" "$out"' EXIT

printf 'round\tside\tseconds\texit\tsaid\n'
round=1
while [ "$round" -le "$rounds" ]; do
    side=A
    for command in "$@"; do
        start=$(perl -MTime::HiRes=time -e 'printf "%.6f\n", time')
        code=0
        sh -c "$command" > "$out" 2>&1 || code=$?
        end=$(perl -MTime::HiRes=time -e 'printf "%.6f\n", time')
        row=$(awk -v r="$round" -v s="$side" -v a="$start" -v b="$end" -v c="$code" \
            'BEGIN {printf "%d\t%s\t%.3f\t%d", r, s, b - a, c}')
        printf '%s\t%s\n' "$row" "$(awk 'NF {last = $(0)} END {print last}' "$out" | tr '\t\r' '  ')"
        printf '%s\n' "$row" >> "$each"
        side=B
    done
    round=$((round + 1))
done

# The command reaches awk by the environment: a `-v` value is read for escape sequences,
# and a backslash in the command would be printed as something else.
printf 'side\truns\tfailed\tmedian\tmin\tmax\tcommand\n'
side=A
for command in "$@"; do
    awk -F '\t' -v s="$side" '$(2) == s {print $(3) "\t" $(4)}' "$each" | sort -n |
        COMMAND=$command awk -F '\t' -v s="$side" '
            {t[NR] = $(1); failed += ($(2) != 0)}
            END {
                median = NR % 2 ? t[(NR + 1) / 2] : (t[NR / 2] + t[NR / 2 + 1]) / 2
                printf "%s\t%d\t%d\t%.3f\t%.3f\t%.3f\t%s\n", s, NR, failed, median, t[1], t[NR], ENVIRON["COMMAND"]
            }'
    side=B
done
