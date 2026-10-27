### Outside the diff

Write the lead's findings, the **Act on** and **Consider** ones of step 4 with what step 5 added, one to a line, each as `<severity> <file>:<line> <what is wrong> (principle: <name>) (bucket: <Act on or Consider>)`, with its `(risk: <area>)` tag where it has one, in place of the middle line of this block. A finding about a file as a whole has no `:<line>`. A finding about what the change as a whole lacks (a `Done when` line it does not meet, a test it does not have) has `-` in place of the file and line: that form is for what the pull request leaves out, never for code it did not touch. A finding about something a changed line breaks is written against that changed line before it goes in: if no changed line can be named for it, it goes in as it came, and the block drops it.

```sh
gh pr diff <url> | awk '
  pass == 2 {
    file = $(2)
    sub(/:[0-9]+$/, "", file)
    if ($(2) == "-" || $(2) in changed || file in removed) print
    else if (NF) dropped++
    next
  }
  old > 0 || new > 0 {
    mark = substr($(0), 1, 1)
    if (mark == "+") { changed[file ":" at++]; new-- }
    else if (mark == "-") { changed[file ":" at - 1]; changed[file ":" at]; old-- }
    else if (mark != "\\") { at++; old--; new-- }
    next
  }
  /^diff --git / { file = $NF; sub(/^b\//, "", file); changed[file]; seen = 1 }
  /^--- / { was = substr($(0), 5); sub(/^a\//, "", was) }
  /^\+\+\+ / {
    file = substr($(0), 5)
    sub(/^b\//, "", file)
    if (file == "/dev/null") removed[was]
    else changed[file]
  }
  /^@@ / {
    split($(2), o, ",")
    split($(3), n, ",")
    old = (2 in o) ? o[2] : 1
    new = (2 in n) ? n[2] : 1
    at = substr(n[1], 2) + 0
  }
  END {
    if (!seen) { print "no diff was read: nothing kept, nothing dropped" > "/dev/stderr"; exit 1 }
    print "Dropped: " dropped + 0
  }
' - pass=2 /dev/fd/3 3<<'FINDINGS'
<the findings, one to a line>
FINDINGS
```

- It prints the findings to keep, then the count dropped.
  Record the kept ones only.
  The dropped ones are named nowhere: not in the section, not in this thread's summary.
  The count goes in the section's `Dropped:` line.
- A line counts as changed when the pull request added it, or removed a line that sat just before or just after it. Any line of a file the pull request removed counts, and so does a file-level finding on any file in the diff, a renamed or binary one included.
- If it exits with something other than 0, `gh` gave no diff (no network, or a diff too large for GitHub to send).
  Nothing was kept and nothing dropped: do not write a review as clean.
  Run it once more, and if it fails again, say so in the section in place of the findings.
- Do not look at what was dropped to see whether it was true. Whether it was true is not the question.
