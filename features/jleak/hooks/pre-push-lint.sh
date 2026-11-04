#!/bin/sh

limit=60
for file in GNUmakefile makefile Makefile; do
  [ -f "$file" ] && break
done
[ -f "$file" ] && grep -q '^lint:' "$file" || exit 0
for tool in make perl; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "lint: no $tool to run make lint with, so the push is refused" >&2
    exit 1
  }
done
within='
  my $limit = shift;
  defined(my $pid = fork) or die "lint: fork: $!\n";
  if (!$pid) { setpgrp; exec @ARGV or exit 127 }
  setpgrp $pid, $pid;
  $SIG{ALRM} = sub { kill "TERM", -$pid; exit 124 };
  alarm $limit;
  waitpid $pid, 0;
  exit($? & 127 ? 128 + ($? & 127) : $? >> 8);
'
said=$(perl -e "$within" "$limit" make --no-print-directory lint 2>&1 </dev/null)
case $? in
0) exit 0 ;;
124)
  printf '%s\n' "$said" >&2
  echo "lint: make lint ran past ${limit} s, so the push is refused" >&2
  ;;
*)
  printf '%s\n' "$said" >&2
  echo "lint: make lint failed, so the push is refused" >&2
  ;;
esac
exit 1
