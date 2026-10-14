#!/bin/sh
room() (
  LOAD=85
  MEMORY=6
  PRESSURE=10
  CUSHION=85
  SLOTS=85
  PROC=${PROC:-/proc}
  LIMITS=${LIMITS:-$HOME/.local/state/claude/limits}
  TMPFS=${TMPFS:-/tmp}
  rows=$LIMITS
  if [ -d "$LIMITS" ]; then rows=/dev/null; fi
  load=$(cut -d' ' -f1 "$PROC/loadavg" 2> /dev/null)
  cores=$(nproc 2> /dev/null)
  memory=$(awk '/^MemAvailable:/ {print $(2)}' "$PROC/meminfo" 2> /dev/null)
  pressure=$(sed -n 's/^some .*avg60=\([0-9.]*\).*/\1/p' "$PROC/pressure/memory" 2> /dev/null)
  slots=$(df -Pi "$TMPFS" 2> /dev/null | awk 'NR == 2 {print $(2), $(3)}')
  awk -v busy="$load" -v cores="$cores" -v memory="$memory" -v pressure="$pressure" \
    -v slots="${slots% *}" -v taken="${slots#* }" -v TMPFS="$TMPFS" \
    -v LOAD="$LOAD" -v MEMORY="$MEMORY" -v PRESSURE="$PRESSURE" -v SLOTS="$SLOTS" \
    -v CUSHION="$CUSHION" -v LIMITS="$LIMITS" -v rows="$rows" -v now="$(date +%s)" 'BEGIN {
      number = "^[0-9]+(\\.[0-9]+)?$"
      window["five_hour"] = "five-hour"
      window["seven_day"] = "weekly"
      while ((getline row < rows) > 0)
        if (split(row, at, " ") == 3 && at[1] in window && at[2] ~ number && at[3] ~ /^[0-9]+$/) {
          used[at[1]] = at[2]
          left[at[1]] = at[3] - now
        }
      if (busy !~ number || cores !~ number || cores == 0) why = "the load or the core count could not be read"
      else if (int(busy * 100 + 0.5) >= cores * LOAD) why = "load " busy " is at or over " LOAD "% of " cores " cores"
      else if (memory !~ number) why = "the available memory could not be read"
      else if (memory < MEMORY * 1048576) why = sprintf("%.1f GB of memory available, under %s", memory / 1048576, MEMORY)
      else if (pressure !~ number) why = "the memory pressure could not be read"
      else if (pressure >= PRESSURE) why = "memory pressure " pressure " is at or over " PRESSURE
      else if (slots !~ /^[0-9]+$/ || taken !~ /^[0-9]+$/) why = "the file slots of " TMPFS " could not be read"
      else if (taken * 100 > slots * SLOTS) why = TMPFS " has " taken " of " slots " file slots used, over " SLOTS "%"
      else for (n = 1; n <= 2 && why == ""; n++) {
        name = n == 1 ? "five_hour" : "seven_day"
        if (!(name in used) || left[name] <= 0) {
          past = name in used
          count++
          expired += past
          unknown = unknown (unknown == "" ? "" : " and ") window[name]
          reason = reason (reason == "" ? "" : " and ") (past ? "is past the " window[name] " limit\047s reset" : "does not give the " window[name] " limit")
        }
        else if (used[name] >= CUSHION) why = sprintf("the %s limit is %s%% used, at or over %s%%, and resets in %s%d h %d min",
          window[name], used[name], CUSHION, left[name] < 86400 ? "" : int(left[name] / 86400) " d ", left[name] % 86400 / 3600, left[name] % 3600 / 60)
      }
      if (expired == 0) reason = count == 1 ? "does not give it" : "does not give them"
      else if (expired == count) reason = count == 1 ? "is past its reset" : "is past their resets"
      if (why == "" && count > 0) print "note: the plan\047s " unknown (count == 1 ? " limit is" : " limits are") " not known: " LIMITS " " reason > "/dev/stderr"
      print (why == "" ? "go" : "wait: " why)
    }'
)
room
