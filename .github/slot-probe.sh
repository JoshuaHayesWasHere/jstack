#!/bin/bash
# 50 runs of the short-lane limit, as test_slot.py's test runs it, under a load of 2 of the
# runner's 3 cores; each run that does not end 124 prints its stderr.
set -u
yes > /dev/null & l1=$!
yes > /dev/null & l2=$!
trap 'kill $l1 $l2' EXIT
fails=0
for i in $(seq 1 50); do
    d=$(mktemp -d)
    err=$(HOME="$d/home" D="$d" python -c "import sys; from jgauge import cli, slot; slot.SHORT_LIMIT_SECONDS = 0.5; sys.exit(cli.main(sys.argv[1:]))" test-slot --short -- sh -c 'touch "$D/started.$1"; n=0; until [ -e "$D/release.$1" ] || [ ! -d "$D" ] || [ "$n" -gt 3000 ]; do sleep 0.02; n=$((n + 1)); done' sh a 2>&1 >/dev/null)
    rc=$?
    if [ "$rc" != 124 ]; then fails=$((fails + 1)); echo "run $i: exit $rc"; echo "$err"; fi
    rm -rf "$d"
done
echo "direct runs: $fails of 50 failed"
pf=0
for i in $(seq 1 50); do
    python -m pytest -q -p no:cacheprovider "features/jgauge/tests/test_slot.py::test_a_short_job_past_its_limit_is_stopped_and_says_so" > /tmp/out.txt 2>&1 || { pf=$((pf + 1)); tail -5 /tmp/out.txt; }
done
echo "pytest runs: $pf of 50 failed"
zf=0
for i in $(seq 1 50); do
    python -m pytest -q -p no:cacheprovider "features/jgauge/tests/test_slot.py::test_a_short_job_whose_group_is_left_with_a_zombie_still_stops_and_says_so" > /tmp/out.txt 2>&1 || { zf=$((zf + 1)); tail -5 /tmp/out.txt; }
done
echo "zombie test runs: $zf of 50 failed"
[ "$fails" = 0 ] && [ "$pf" = 0 ] && [ "$zf" = 0 ]
