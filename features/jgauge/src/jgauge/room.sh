#!/bin/sh
# `room.sh sweep` runs the sweep alone, whatever share of the file slots is used: a test slot let go
# runs it. It prints how many runs it removed. A Mac has no /proc to tell a held run by, so there it
# removes none unless given a PROC.
sweep() (
  if [ -z "${PROC:-}" ] && [ "$(uname -s 2> /dev/null)" = Darwin ]; then echo 0; return; fi
  PROC=${PROC:-/proc}
  TMPFS=${TMPFS:-/tmp}
  here=$(cd "$TMPFS" 2> /dev/null && pwd -P) || { echo 0; return; }
  stale=$({
    find "$PROC"/[0-9]*/cwd "$PROC"/[0-9]*/fd/ -maxdepth 1 -type l -exec readlink {} + 2> /dev/null
    printf '\001\n'
    find "$here"/pytest-of-* -mindepth 1 -maxdepth 1 -name 'pytest-*' -type d -user "$(id -u)" -mmin +20 2> /dev/null
  } | awk '
    $(0) == "\001" {runs = 1; next}
    !runs {path = $(0); while (path ~ /.\//) {held[path]; sub(/\/[^\/]*$/, "", path)}; next}
    !($(0) in held)')
  printf '%s\n' "$stale" | while IFS= read -r run; do
    [ -n "$run" ] || continue
    pid=$(head -c 20 "$run/.lock" 2> /dev/null)
    case $pid in ("" | *[!0-9]*) ;; (*) [ -e "$PROC/$pid" ] && continue ;; esac
    rm -rf -- "$run" 2> /dev/null
    [ -e "$run" ] || echo "$run"
  done | awk 'END {print NR}'
)
room() (
  LOAD=200
  CPU=40
  MEMORY=6
  PRESSURE=10
  CUSHION=${HEADROOM:-90}
  SLOTS=85
  mac=0
  if [ -z "${PROC:-}" ] && [ "$(uname -s 2> /dev/null)" = Darwin ]; then mac=1; fi
  PROC=${PROC:-/proc}
  LIMITS=${LIMITS:-$HOME/.local/state/claude/limits}
  TMPFS=${TMPFS:-/tmp}
  SKIP_LOAD=${SKIP_LOAD:-0}
  POOL=${POOL:-claudeAgent}
  if ! awk -v pool="$POOL" 'BEGIN {exit !(pool ~ /^[A-Za-z0-9_-]+(,[A-Za-z0-9_-]+)*( [A-Za-z0-9_-]+(,[A-Za-z0-9_-]+)*)*$/)}'; then
    echo "wait: $POOL is not a pool of provider instances"
    return
  fi
  hollow=" "
  for instance in $(echo "$POOL" | tr ',' ' '); do
    file=$LIMITS
    if [ "$instance" != claudeAgent ]; then file=$LIMITS.$instance; fi
    if [ -d "$file" ]; then hollow="$hollow$instance "; fi
  done
  if [ "$mac" = 1 ]; then
    psi=0
    tmp=0
    load=$(sysctl -n vm.loadavg 2> /dev/null | awk '$(1) == "{" {print $(2)}')
    cores=$(sysctl -n hw.ncpu 2> /dev/null)
    memory=$(vm_stat 2> /dev/null | awk '
      NR == 1 && /page size of [0-9]+ bytes/ {size = $(NF - 1)}
      /^Pages (free|inactive|speculative):/ {sub(/\.$/, "", $(NF)); if ($(NF) ~ /^[0-9]+$/) {pages += $(NF); seen++}}
      END {if (size > 0 && seen == 3) print int(pages * size / 1024)}')
  else
    psi=1
    tmp=1
    load=$(cut -d' ' -f1 "$PROC/loadavg" 2> /dev/null)
    cores=$(nproc 2> /dev/null || getconf _NPROCESSORS_ONLN 2> /dev/null || sysctl -n hw.ncpu 2> /dev/null)
    memory=$(awk '/^MemAvailable:/ {print $(2)}' "$PROC/meminfo" 2> /dev/null)
    pressure=$(sed -n 's/^some .*avg60=\([0-9.]*\).*/\1/p' "$PROC/pressure/memory" 2> /dev/null)
    stalled=$(sed -n 's/^some .*avg60=\([0-9.]*\).*/\1/p' "$PROC/pressure/cpu" 2> /dev/null)
  fi
  read_slots() { df -Pi "$TMPFS" 2> /dev/null | awk '
    NR == 1 {for (i = 1; i <= NF; i++) column[tolower($(i))] = i}
    NR == 2 && column["iused"] {
      used = $(column["iused"])
      if (column["inodes"]) total = $(column["inodes"])
      else if (used ~ /^[0-9]+$/ && $(column["ifree"]) ~ /^[0-9]+$/) total = used + $(column["ifree"])
      print total, used
    }'; }
  if [ "$tmp" = 1 ]; then slots=$(read_slots); fi
  if [ "$tmp" = 1 ] && echo "$slots" | awk -v SLOTS="$SLOTS" '{exit !($(1) ~ /^[0-9]+$/ && $(2) ~ /^[0-9]+$/ && $(2) * 100 > $(1) * SLOTS)}'; then
    removed=$(sweep)
    if [ "$removed" -gt 0 ]; then
      was=$slots
      slots=$(read_slots)
      echo "$was $slots" | awk -v removed="$removed" -v TMPFS="$TMPFS" '{
        print "room: removed " removed " stale pytest directories under " TMPFS ", freeing " ($(2) - $(4) > 0 ? $(2) - $(4) : 0) " file slots" > "/dev/stderr"
      }'
    fi
  fi
  said=$(awk -v busy="$load" -v cores="$cores" -v stalled="$stalled" -v memory="$memory" -v pressure="$pressure" \
    -v psi="$psi" -v tmp="$tmp" -v light="$SKIP_LOAD" -v slots="${slots% *}" -v taken="${slots#* }" -v TMPFS="$TMPFS" \
    -v LOAD="$LOAD" -v CPU="$CPU" -v MEMORY="$MEMORY" -v PRESSURE="$PRESSURE" -v SLOTS="$SLOTS" \
    -v CUSHION="$CUSHION" -v LIMITS="$LIMITS" -v pool="$POOL" -v hollow="$hollow" -v now="$(date +%s)" '
    function span(left) {
      return (left < 86400 ? "" : int(left / 86400) " d ") sprintf("%d h %d min", left % 86400 / 3600, left % 3600 / 60)
    }
    function listed(names, n,    all, i) {
      all = names[1]
      for (i = 2; i <= n; i++) all = all (i == n ? " and " : ", ") names[i]
      return all
    }
    # Read one instance of the pool, once: its file, whether a window has it full, the first
    # such window in order, the one that keeps it full longest, and the note for a window it lacks.
    function plan(instance,    file, row, at, n, name, count, expired, unknown, reason, past) {
      if (instance in read) return
      read[instance] = 1
      file = instance == "claudeAgent" ? LIMITS : LIMITS "." instance
      while (!index(hollow, " " instance " ") && (getline row < file) > 0)
        if (split(row, at, " ") == 3 && at[1] in window && at[2] ~ number && at[3] ~ /^[0-9]+$/) {
          used[instance, at[1]] = at[2]
          left[instance, at[1]] = at[3] - now
        }
      close(file)
      for (n = 1; n <= 2; n++) {
        name = n == 1 ? "five_hour" : "seven_day"
        if (!((instance, name) in used) || left[instance, name] <= 0) {
          past = (instance, name) in used
          count++
          expired += past
          unknown = unknown (unknown == "" ? "" : " and ") window[name]
          reason = reason (reason == "" ? "" : " and ") (past ? "is past the " window[name] " limit\047s reset" : "does not give the " window[name] " limit")
        }
        else if (used[instance, name] >= CUSHION) {
          if (!(instance in first)) first[instance] = name
          if (!(instance in longest) || left[instance, name] > left[instance, longest[instance]]) longest[instance] = name
        }
      }
      if (expired == 0) reason = count == 1 ? "does not give it" : "does not give them"
      else if (expired == count) reason = count == 1 ? "is past its reset" : "is past their resets"
      if (count > 0) note[instance] = "note: the plan\047s " unknown (count == 1 ? " limit is" : " limits are") " not known: " file " " reason
    }
    function held(instance,    name) {
      name = longest[instance]
      return instance "\047s " window[name] " limit is " used[instance, name] "% used and resets in " span(left[instance, name])
    }
    BEGIN {
      number = "^[0-9]+(\\.[0-9]+)?$"
      window["five_hour"] = "five-hour"
      window["seven_day"] = "weekly"
      if (light != "1" && (busy !~ number || cores !~ number || cores == 0)) why = "the load or the core count could not be read"
      else if (light != "1" && int(busy * 100 + 0.5) >= cores * LOAD) why = "load " busy " is at or over " LOAD "% of " cores " cores"
      else if (light != "1" && psi && stalled !~ number) why = "the CPU pressure could not be read"
      else if (light != "1" && psi && stalled >= CPU) why = "CPU pressure " stalled " is at or over " CPU
      else if (memory !~ number) why = "the available memory could not be read"
      else if (memory < MEMORY * 1048576) why = sprintf("%.1f GB of memory available, under %s", memory / 1048576, MEMORY)
      else if (psi && pressure !~ number) why = "the memory pressure could not be read"
      else if (psi && pressure >= PRESSURE) why = "memory pressure " pressure " is at or over " PRESSURE
      else if (tmp && (slots !~ /^[0-9]+$/ || taken !~ /^[0-9]+$/)) why = "the file slots of " TMPFS " could not be read"
      else if (tmp && taken * 100 > slots * SLOTS) why = TMPFS " has " taken " of " slots " file slots used, over " SLOTS "%"
      # Room holds back a launch only while every instance of a line of the pool is full. For a
      # pool of one, the reason names its first full window; for a larger pool, each instance
      # and the first reset.
      else for (l = 1; l <= split(pool, lines, " ") && why == ""; l++) {
        members = split(lines[l], member, ",")
        full = 0
        free = ""
        for (m = 1; m <= members; m++) {
          plan(member[m])
          if (member[m] in first) capped[++full] = member[m]
          else if (free == "") free = member[m]
        }
        if (full == 0) continue
        if (members == 1) {
          name = first[member[1]]
          why = sprintf("the %s limit is %s%% used, at or over %s%%, and resets in %s",
            window[name], used[member[1], name], CUSHION, span(left[member[1], name]))
          continue
        }
        soonest = ""
        said = ""
        for (m = 1; m <= full; m++) {
          held_for = left[capped[m], longest[capped[m]]]
          if (soonest == "" || held_for < soonest) soonest = held_for
          said = said (said == "" ? "" : ", ") held(capped[m])
        }
        if (full == members) why = listed(member, members) " are " (members == 2 ? "both" : "all") " at or over " CUSHION "%: " said "; the first resets in " span(soonest)
        else held_note[l] = "note: " said "; the pool has room on " free
      }
      if (why == "") {
        for (l = 1; l <= split(pool, lines, " "); l++) {
          members = split(lines[l], member, ",")
          for (m = 1; m <= members; m++)
            if (member[m] in note && !(member[m] in told)) {
              told[member[m]] = 1
              print note[member[m]] > "/dev/stderr"
            }
          if (l in held_note) print held_note[l] > "/dev/stderr"
        }
      }
      print (why == "" ? "go" : "wait: " why)
    }')
  case $mac:$said in
  0:"wait: load "*" cores")
    hz=$(getconf CLK_TCK 2> /dev/null)
    up=$(cut -d' ' -f1 "$PROC/uptime" 2> /dev/null)
    top=$(awk -v hz="${hz:-100}" -v up="$up" '
      FNR == 1 {
        line = $(0)
        sub(/^.*\) /, "", line)
        split(line, field, " ")
        pid = FILENAME
        sub(/\/stat$/, "", pid)
        sub(/^.*\//, "", pid)
        age = up - field[20] / hz
        if (age > 0 && field[1] != "Z") printf "%d %s\n", 100 * (field[12] + field[13]) / hz / age + 0.5, pid
      }' "$PROC"/[0-9]*/stat 2> /dev/null | sort -rn | head -n 3 | while read -r share pid; do
      [ "$share" -gt 0 ] || continue
      command=$(tr '\0' ' ' < "$PROC/$pid/cmdline" 2> /dev/null | cut -c1-80 | sed 's/ *$//')
      cwd=$(readlink "$PROC/$pid/cwd" 2> /dev/null)
      printf '%s in %s (%s%%), ' "${command:-?}" "${cwd:-?}" "$share"
    done)
    if [ -n "$top" ]; then said="$said; the busiest: ${top%, }"; fi
    ;;
  esac
  echo "$said"
)
if [ "${1:-}" = sweep ]; then sweep; else room; fi
