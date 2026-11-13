- Once every **Done when** line holds, with the work committed, run the check of the change, once.
  CI is the check of record: its check on the pull request runs every test the change selects, and it is the gate.
  The desk's check is the lint, the touched tests, the repo's guard tests and the tests that read the change, and never the whole suite or the selection.
  In a repo whose pull request check selects its tests, jstack's `scripts/select_tests.py`, the touched tests are the test files the branch adds or edits since it left its base (`select_tests.py --part touched`), the guard tests are the cross-cutting tests the selection names, wherever their files live (`select_tests.py --part cross`), that are not touched already, and the tests that read the change are the ones the pull request's check selects because they name or read a file the branch edits, a skill that includes it or a read set that matches it, and that neither of the others holds (`select_tests.py --part names`, a few files a line, as many as fit 60 s of test time).
  The block asks `origin/main`'s `scripts/select_tests.py` for the three lists, a copy of it run over the branch's own tree, so a branch stacked on a base that left main before a part existed still gets them, and is not held for want of a `Checked:` line.
  Where `origin/main` has no such file the block says so and asks the branch's own.
  The check is `make check-fast BASE=<base> PART=touched`, run in steps, each its own call of `jgauge test-slot --short`: the lint first, then the touched test files, then the guard test files, then the test files CI failed on (below), then the files of the names part, each kind in steps of as many files as fit 60 s of measured time, half the short lane's limit.
  So a test that reads an edited skill file, as test_status_line_readers.py reads features/crew/no-pr-end.md, fails at the desk and not first on the pull request, as it failed twice on #1691.
  Over main's last 20 merges the names part added a median of 98 test files to the desk's 48 (6 to 256), in 20 steps (1 to 59), so a check takes several calls of the block more often than before.
  A file's measured time is its share of the pytest session's seconds in the report (`JUNIT=`) of the last step that ran it in the short lane, by its tests' seconds, so it counts the lane's workers and the session's start, kept in the repo's `crew-check-times`, in the git dir every worktree shares (`git rev-parse --git-common-dir`), beside each worktree's `crew-check-steps`, so one crew's check measures the files for the next.
  A file no step has measured runs alone, and a line of the names part with such a file runs as the selector gave it, as each did when every file was its own take: on 2026-11-12 that cost 272 slot takes a merged pull request.
  A step of several files the short lane stops at its time limit (exit 124) reached no verdict: the block forgets their times (`<file> -`) and runs each again alone in the short lane.
  A step of one file it stops runs again alone in a full test slot, which has no time limit, so every step reaches a verdict however loaded the machine is.
  A 124 is never a pass and never a failure: it is no verdict.
  Each test file a step passed at a committed head, and each one a step failed on, goes on the desk's store of runs, `crew-passed-runs` in the git dir every worktree shares, as `passed <file> <head>` or `failed <file> <head>`, and the block hands the store to the selector (`CREW_PASSED_RUNS`) for the guard tests and the tests that read the change.
  The selector leaves out a file whose last run on the store passed at a head this checkout holds, where the diff from that head to this one changes nothing the pull request's own selection would run the file for, its read set: it prints `<file>: skipped, its read set is as it was when it passed on this desk at <head>`.
  A cross-cutting guard reads the whole tree, so only a tree the same as the passed head's skips it; a file whose last run failed, a head from another desk, and a worktree with work not committed skip nothing.
  On 2026-11-12 61% of jstack's short-lane CPU, 431k of 710k CPU-s, went to a file a worktree had run before.
  CI's check and jmerge's run never set the store, so they run every file they select.
  The catch-all and the tests the change reaches through imports and features are CI's to run: the desk does not run them.
  The base is the branch the pull request goes on, as the block that opens it reads it from the brief: the branch of a `Stacked on:` line, and `origin/main` for a brief with none.
  A base branch that is gone, as one is once it merged, is `origin/main` too.
  In any other repo the check is the repo's check command, the first line of `$H/fresh-check` with its `jgauge test-slot --` left off (the block takes the slot itself), under a full test slot, and it is that command and no other, whatever command a brief's **Done when** names for it.
  In a repo with no `$H/fresh-check`, the check command is the one the repo's own instructions name (`CLAUDE.md`, `AGENTS.md` or its `Makefile`).
  Run this in this worktree, with the block at the top, and the brief's slug and the check command in place of the words in angle brackets.
  Every run of the check this skill asks for, after a failed check, a rebase or a fix, is this block:

  ```sh
  budget=540 reserve=120
  began=$(date +%s)
  B="$H/tasks/<slug>.md"
  head=$(git rev-parse HEAD)
  clean=$(git status --porcelain)
  out=$(mktemp "${TMPDIR:-/tmp}/out.XXXXXX")
  code=$(mktemp "${TMPDIR:-/tmp}/code.XXXXXX")
  {
  if [ -f scripts/select_tests.py ]; then
      on=$(uv run --project "$T/../source" jbriefs line base "$H/tasks/<slug>.md" 2> /dev/null)
      [ "$on" != none ] || on=
      on=origin/${on:-main}
      git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
      selector=$code.selector
      if ! git show origin/main:scripts/select_tests.py > "$selector" 2> /dev/null; then
          echo "origin/main has no scripts/select_tests.py: the branch's own names the tests"
          selector=scripts/select_tests.py
      fi
      reuse=$(git rev-parse --path-format=absolute --git-common-dir)/crew-passed-runs
      selects() {
          CREW_PASSED_RUNS=$reuse python3 -c 'import os, sys
  main = sys.modules["__main__"]
  path = sys.argv.pop(1)
  sys.argv[0] = main.__file__ = os.path.abspath("scripts/select_tests.py")
  sys.path[0] = os.path.dirname(sys.argv[0])
  exec(compile(open(path).read(), sys.argv[0], "exec"), vars(main))' "$selector" "$@"
      }
      exec 3>&1
      if ! base=$(git merge-base "$on" HEAD); then
          echo "no check: the branch shares no commit with $on"
          false
      elif ! touched=$(selects --part touched "$base" HEAD); then
          echo "no check: scripts/select_tests.py could not name the touched tests"
          false
      elif ! guards=$(selects --part cross "$base" HEAD 2>&3); then
          echo "no check: scripts/select_tests.py could not name the guard tests"
          false
      elif ! names=$(selects --part names "$base" HEAD 2>&3); then
          echo "no check: scripts/select_tests.py could not name the tests that read the change"
          false
      else
          guards=$(printf '%s\n' "$guards" | command grep -vxF -e "$touched")
          kept=$(git rev-parse --git-path crew-failed-files)
          failed=$(cat "$kept" 2> /dev/null | while read -r one; do [ ! -f "$one" ] || echo "$one"; done | command grep -vxF -e "$touched" -e "$guards" -e "$(printf '%s\n' $names)")
          printf 'make check-fast BASE=%s PART=touched\n' "$base" > "$code.command"
          steps=$(git rev-parse --git-path crew-check-steps)
          [ "$(sed -n 1p "$steps" 2> /dev/null)" = "$head $base" ] || printf '%s %s\n' "$head" "$base" > "$steps"
          times=$(git rev-parse --path-format=absolute --git-common-dir)/crew-check-times
          plan() {
              awk -v steps="$steps" -v times="$times" -v most=60 '
                  BEGIN {
                      while ((getline line < times) > 0) { split(line, word, " "); took[word[1]] = word[2] }
                      while ((getline line < steps) > 0) if (line ~ /^passed /) passed[substr(line, 8)] = 1
                  }
                  NF {
                      unit = ""; sum = 0; known = 1
                      for (i = 1; i <= NF; i++) {
                          if ($i in passed) continue
                          unit = unit (unit == "" ? "" : ",") $i
                          if (!($i in took) || took[$i] == "-") known = 0
                          else sum += took[$i]
                      }
                      if (unit == "") next
                      if (!known) { print unit; next }
                      if (held != "" && heldsum + sum > most) { print held; held = ""; heldsum = 0 }
                      held = held (held == "" ? "" : ",") unit
                      heldsum += sum
                  }
                  END { if (held != "") print held }'
          }
          todo=$(
              command grep -qxF 'passed lint' "$steps" || echo lint
              for kind in "$touched" "$guards" "$failed" "$names"; do printf '%s\n' "$kind" | plan; done
          )
          echo "touched: $(printf '%s' "$touched" | command grep -c .) test files, then $(printf '%s' "$guards" | command grep -c .) cross-cutting guard tests, then $(printf '%s' "$failed" | command grep -c .) test files CI failed on, then $(printf '%s\n' $names | command grep -c .) test files that read the change, in $(printf '%s' "$todo" | command grep -cvx -e lint -e '') steps of the short lane after the lint; CI's check runs the rest of the selection"
          for one in lint $touched $guards $failed $names; do
              ! command grep -qxF "passed $one" "$steps" || echo "$one: passed at this head already"
          done
          ran=0
          ceiling=${JGAUGE_SHORT_WAIT_SECONDS:-300}
          left=
          junit=$code.junit
          while [ -n "$todo" ]; do
              step=$(printf '%s\n' "$todo" | sed -n 1p)
              todo=$(printf '%s\n' "$todo" | sed 1d)
              have=$((budget - $(date +%s) + began))
              if [ "$have" -lt "$reserve" ]; then
                  left=$(printf '%s\n' "$step" "$todo" | command grep -c .)
                  break
              fi
              wait=$((have - reserve))
              [ "$wait" -le "$ceiling" ] || wait=$ceiling
              files=$(printf '%s' "$step" | tr , ' ')
              if [ "$step" = lint ]; then
                  set -- make check-fast BASE="$base" PYTEST=: PART=touched
              else
                  set -- make test TESTS="$files" BASE="$base" JUNIT="$junit"
              fi
              started=$(date +%s)
              lane=short
              JGAUGE_SHORT_WAIT_SECONDS=$wait uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- "$@"
              said=$?
              if [ "$said" = 124 ] && [ "$files" != "${files#* }" ]; then
                  echo "$step: stopped at the short lane's limit, no verdict: its $(printf '%s\n' $files | command grep -c .) files run again, each alone"
                  printf '%s -\n' $files >> "$times"
                  todo=$(printf '%s\n' $files "$todo" | sed '/^$/d')
                  continue
              fi
              if [ "$said" = 124 ]; then
                  echo "$step: stopped at the short lane's limit, no verdict: it runs again alone in a full slot"
                  lane=full
                  uv run --project "$T/../source" jgauge test-slot --thread '<thread id>' -- "$@"
                  said=$?
              fi
              echo "$step: exit $said in $(($(date +%s) - started)) s, $lane lane"
              bad=
              if [ "$step" != lint ] && [ "$said" != 124 ] && [ "$said" != 76 ]; then
                  bad=$(python3 -c 'import os, sys, xml.etree.ElementTree as tree
  report, step, times, lane = sys.argv[1:]
  try:
      root = tree.parse(report).getroot()
  except (OSError, tree.ParseError):
      sys.exit()
  suite = root if root.tag == "testsuite" else root.find("testsuite")
  dotted = {one.removesuffix(".py").replace("/", "."): one for one in step.split(",")}
  took, failed = {}, set()
  for case in root.iter("testcase"):
      names = (case.get("classname") or "", case.get("name") or "")
      hits = [key for key in dotted for name in names if name == key or name.startswith(key + ".")]
      if hits:
          one = dotted[max(hits, key=len)]
          took[one] = took.get(one, 0) + float(case.get("time") or 0)
          if case.find("failure") is not None or case.find("error") is not None:
              failed.add(one)
  summed = sum(took.values())
  wall = float(suite.get("time") or 0) if suite is not None else 0
  if lane == "short" and took:
      with open(times, "a") as kept:
          kept.write("".join(f"{one} {(wall * spent / summed if wall and summed else spent):.1f}\n" for one, spent in sorted(took.items())))
  if os.path.exists(times) and os.path.getsize(times) > 1 << 20:
      last = {}
      for line in open(times):
          if len(line.split()) == 2:
              last[line.split()[0]] = line.split()[1]
      with open(f"{times}.{os.getpid()}", "w") as new:
          new.write("".join(f"{one} {spent}\n" for one, spent in last.items()))
      os.replace(f"{times}.{os.getpid()}", times)
  print("\n".join(sorted(failed)))' "$junit" "$step" "$times" "$lane")
              fi
              case $said in
              0)
                  if [ -z "$clean" ] && [ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$head" ]; then
                      printf 'passed %s\n' $files >> "$steps"
                      [ "$step" = lint ] || for one in $files; do echo "passed $one $head"; done >> "$reuse"
                  elif [ -z "$clean" ]; then
                      echo "$step: passed over work that $head does not have, so it is not kept"
                      ran=76
                      break
                  fi
                  ;;
              76)
                  ran=76
                  break
                  ;;
              124) ran=124 ;;
              *)
                  if [ "$step" != lint ]; then
                      if [ -z "$bad" ]; then
                          echo "$step: pytest's report names no failing file, so each file of the step is kept"
                          bad=$files
                      fi
                      for one in $bad; do echo "$one: failed in step $step"; done
                      for one in $bad; do echo "failed $one $head"; done >> "$reuse"
                      { printf '%s\n' $bad; cat "$kept" 2> /dev/null; } | sort -u > "$kept.new" && mv "$kept.new" "$kept"
                  fi
                  ran=$said
                  break
                  ;;
              esac
          done
          if [ -f "$reuse" ] && [ "$(wc -c < "$reuse")" -gt 4194304 ]; then
              tail -n 20000 "$reuse" > "$reuse.$$" && mv "$reuse.$$" "$reuse"
          fi
          if [ -s "$kept" ]; then
              while read -r one; do
                  command grep -qxF "passed $one" "$steps" || echo "$one"
              done < "$kept" > "$kept.new"
              mv "$kept.new" "$kept"
          fi
          if [ -n "$left" ]; then
              echo "running: $left steps left"
              ran=76
          fi
          (exit "$ran")
      fi
  else
      echo 'jgauge check' > "$code.command"
      uv run --project "$T/../source" jgauge check --thread '<thread id>' << 'THE_CHECK_ENDS_HERE'
  <check command>
  THE_CHECK_ENDS_HERE
  fi
  echo $? > "$code"
  } | tee "$out"
  ran=$(cat "$code")
  command=$(sed 's/ *$//' "$code.command" 2> /dev/null)
  case $command in
  'jgauge check') tail -n 1 "$out" | command grep -q '^done: the check exited ' || command= ;;
  esac
  if [ -n "$command" ] && [ "$ran" != 76 ] && [ -z "$clean" ] && [ -z "$(git status --porcelain)" ] &&
      [ "$(git rev-parse HEAD)" = "$head" ] && [ -f "$B" ]; then
      printf 'Checked: %s exit %s at %s\n' "$command" "$ran" "$head" >> "$B"
  fi
  (exit "$ran")
  ```

  A `no check:` line ends the block 1: nothing was checked, and it is no proof.
  The block adds `Checked: <the command> exit <its exit> at <the full head>` to the brief for a check that ran to its end on a committed head, which `jmerge` reads, and nobody writes that line by hand.
  It does so from the first head on, whether or not the brief has a Result yet, so the first head's check is on record too.
  For a selected check the line reads `Checked: make check-fast BASE=<base> PART=touched exit <n> at <head>`, and the block prints each step as `<step>: exit <n> in <s> s, <lane> lane`, the step `lint` or its test files joined by commas.
  The block's exit is the first step's failure where one failed, and it stops there; else 76 where steps are left or a lane had no slot; else 124 where a step reached no verdict even in a full slot; else 0.
  The steps after the guards are the test files CI failed on that the block of "The failed files" kept in the worktree's `crew-failed-files` and that are in the worktree, so a fix head's `Checked:` line says exit 0 only once they pass there.
  A failing step names each file pytest's report shows failing, as `<file>: failed in step <step>`, and keeps it in `crew-failed-files` too; where the report names none, as when pytest could not start, it keeps each file of the step.
  A name leaves that list once a step it was in passed at a committed head.
  Each file of a step that passed at a committed head is kept in the worktree's `crew-check-steps` (`git rev-parse --git-path crew-check-steps`) as `passed <file>`, and a run of the block at the same head and base skips it and packs the rest anew, so a wait for a slot, or a call cut at its time limit, never starts the check over.
  A step's files are kept only where the worktree was clean when the block began and is still clean at that head when the step ends: a call moved to the background lets the crew edit while a step runs, and a step that passed over such an edit is no pass at the head.
  The block prints `<step>: passed over work that <head> does not have, so it is not kept`, starts no further step, and ends 76 with no `Checked:` line and no `running:` line: commit or drop the work first, then run the block again.
  `jmerge` merges a pull request only once its last `Checked:` line says the desk's check (`PART=touched`, a `PART=guards` line of an earlier head, or another repo's `jgauge check`) exited 0 at its head, or at a head whose patch the head carries unchanged (`ready.short_on_checked`): a missing line, a failure, a 124 and a line of a head whose patch changed since each hold it, until this block runs again at the head.
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), in the foreground: a call that outlives 10 minutes is moved to the background, and each step's end then wakes the thread.
  Claude Code stops a background command at 30 minutes, and a wait for a slot can take that long, so the crew's `check-foreground` hook (`features/crew/hooks/check-foreground.sh`) refuses a call sent to the background whose command runs `jgauge test-slot`, `jgauge check` or `proved.sh`, with one line that says to run it in the foreground with `timeout: 600000`.
  So the block counts the time since it began and starts no step with less than `reserve` (120 s, the short lane's limit) left of its `budget` (540 s).
  A step waits for a short slot for what is left less `reserve`, and never longer than the lane's ceiling (`JGAUGE_SHORT_WAIT_SECONDS`, 300 s by default).
  A step that falls back to a full slot can still take minutes on a busy machine.
  With steps left, the block prints `running: <n> steps left`, writes no `Checked:` line and ends 76: run it again at once, in this turn.
  With no slot of a lane, it ends 76, as a targeted run does: where the short lane had none by its ceiling, run the block again at once, in this turn; where the full lane had none, the turn ends with the one line of "test slots", and on jbus's message run the block again.
  Each run goes on from the first step that has not passed, and the run that passes the last step writes the `Checked:` line.
  It ends with the check's exit code, and on 0 the `touched:` line, each step's line and that exit code go on `Proof:`.
  A step that fails is the change's to fix, and every exit but 0 holds the pull request: a 124 reached no verdict, so run the block again.
  This desk proof, the `Checked:` line and the `Proved:` line below, is what jbus launches the review on, before the pull request opens.
  The pull request is ready to merge only once CI's check on it passed, as "The checks" says, and the follow-up Result's `Proof:` names CI's check at that head beside the desk's run.
  In any other repo the block runs `jgauge check`, and the rest of this step is about that run.
  It starts the check command on its own, holding one of the machine-wide test slots, and the call waits on it for up to 9 minutes.
  Give the call a time limit of 10 minutes, the longest a call in the foreground gets (`timeout: 600000` in Claude Code), in the foreground, which the `check-foreground` hook holds it to.
  With every slot taken, nothing runs: the check registers this thread as a waiter, and the block prints `waiting` and ends 76.
  That wait is the one time the turn ends: end it at once with the one line above, and on jbus's message run this block again, which starts the check afresh.
  A check runs as long as the check command takes once it holds a slot, longer where the command runs the whole suite, so one call is not always enough: on `running`, run the block again, in this turn, as many times as it takes, until it prints `done`.
  Never end your turn while your own check runs, and never say you will go on once it finishes: nothing wakes a thread when a command ends, only a message does, and the push, the Result and the pull request would never come.
  A check that a call or a turn before this one started is joined, not started again (`joined`), and one that ended after the last call gives what it said (`checked`).
  A check whose answer a call already gave runs afresh on the next call, so a failure that was not the change's (a flake, a full `/tmp`) is run again by running the block again.
  On `stale`, the check ran on files that have changed since, and its answer is no proof: run the block again.
  On `done`, the block ends with the command's exit code: put its last line on `Proof:`.
  Never run the command a second way to get past the wait.
  Testing, not coding, is what uses up the machine, so the check command is not how you find out whether an edit works: the targeted runs are.
  Run it again only after changing something to fix what that run found.
- A repo's heavy suite (a browser end-to-end matrix, anything that runs under the machine-wide `heavy-suite.lock`) is part of that one run of the check command, and the crewmate runs it: once, under the test slot, and under the suite's own `heavy-suite.lock`, which the repo's command for the suite takes itself.
  While you work, run the checks your change touches (the spec files it edits or covers) and not the whole suite.
  A repo with no heavy suite has nothing more here: its check command is the whole of it.
- Once the check passed, prove the change with the tests it changes: each `test_*.py` or `*_test.py`, and each `*.test.*` or `*.spec.*` of JavaScript or TypeScript (`.js`, `.ts`, `.jsx`, `.tsx` and their `.mjs`, `.mts` kin), the branch adds or changes since its base fails over the base's code and passes at the head.
  A run of a whole suite, or of tests that pass at the base as well, proves nothing: #968's `Proves it` printed 853 passed at its base while its named test failed there.
  Run this in this worktree, with the block at the top, and the brief's slug and this thread's id in place of the words in angle brackets:

  ```sh
  bash "$T/proved.sh" "$H/tasks/<slug>.md" '<thread id>'
  ```

  The block is one command that runs `$T/proved.sh` by its path, and the script holds the proof's steps.
  Claude Code holds a command that has `rm` in it, in a trap or an inner shell too, for an approval, even in full access ("This shell -c script runs rm and could not be checked"), and no crew can give its own: on 2026-11-07 five crews stalled for hours on the trap that removed the copy.
  Run the script as the block does, never its steps pasted into a call.
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), in the foreground, which the `check-foreground` hook holds it to: a side that falls back to a full slot can take minutes on a busy machine.
  The head's tests run in a copy of the head the block began at, then laid over a copy of the base's files, each copy with a venv of its own, so the base run imports the base's code and not the head's, and an edit or a commit made in the worktree while the call runs reaches neither run.
  The head run and the base run share the one short slot the block gets, since a side that gave its slot back would find every slot taken on a busy machine when it asked again; a side the short lane stops at its limit (exit 124) runs again alone in a full slot, which has none, as a step of the check block does, and the block ends 76 only where it gets no slot.
  A `test_*.py` runs on pytest, with `-m "not browser"`.
  A `*.test.*` runs on the Vitest of its package, the directory of the nearest `package.json` above it: that package's own (`node_modules/.bin/vitest run`), or the one its workspace's install put in a directory above it.
  It runs from the directory of the nearest `vitest.config.*` between it and that package, the package's own directory where none is between, so that config's `include` reaches it.
  A `*.spec.*` runs on Playwright (`node_modules/.bin/playwright test`, found the same way) where its directory, or one above it, has a `playwright.config.*`, and then from the directory of the nearest one, so its `testDir` reaches it; it runs on Vitest where none has one.
  Both run with `CI=1`, so Playwright starts its own web server and takes no dev server already on the port for the change's.
  A test whose tree names no Vitest, with no `vitest.config.*` and no `package.json` that names `vitest` in its folder or one above it, runs on `node --test` from its package's folder, or the root where it has none, as FAFU's `flows/` and `mapdata/` tests do: its exit is the side's, 1 only where Node's report counts a failed test.
  Each copy installs what its tests run on: `uv sync` for pytest, and for each Node test's package the install its lockfile names, or the lockfile of the workspace above it (`npm ci`, `pnpm`, `yarn` or `bun install --frozen-lockfile`, `npm install` with none), once per directory; an install that fails prints `no proof: the <side>'s install failed: <its last line>`, with ` in <directory>` after `install` where it ran below the root, and ends 1.
  Vitest and Playwright end 1 on a failed test and on a run that reached none alike (no file found, a web server that would not start, a spec outside Playwright's `testDir`): the side's exit is 1 only where the runner's JSON report has a failed test or a test file that did not load, and 2 where it has neither, which proves nothing.
  A base with no `package.json` for a test's package, a Node repo's or a package's first pull request, has nothing of the project for its tests to run on: the base side runs nothing there and prints `base exit 1: <runner>: no package.json at the base, so its tests have nothing of the project to run on`, with the directory the tests run from after `<runner>` where it is not the root, and the line reads as any other, `Proved: <tests> base exit 1 at <base>, head exit 0 at <head>`.
  The pytest side runs on pytest's workers where the tree's venv has pytest-xdist, on one process where it has not: the short lane's count (`SHORT_WORKERS` in `jgauge.sizes`) in a short slot, and an eighth of the processors, at least two (the Makefile's `PER_CORE`, `DESK_SHARE` in `jgauge.sizes`), in a full one, never `-n auto`, which takes every processor beside the other slots' runs.
  `jgauge sizes` prints both counts for this machine on its `total` line, `<n> full x <workers> + <n> short x <workers>`: read a run's wall time against those, not against a count worked out here.
  Each copy is a clone of this repo in a temp directory, checked out at its commit and sharing this repo's objects, not a git worktree: it is a repository of its own, so a test that runs git there reads that commit, and it leaves `git worktree list` here as it was, whether the tests pass, fail or the call is cut off.
  The block needs no `git worktree remove`, which the door hook refuses as a deletion of data (`deletes data`), refusing the whole call with it.
  The script removes both copies when it exits, after a pass, a failure, a slot's 124 or a TERM that stops the call alike (a trap on `EXIT`), so no copy is left in the temp directory; a call killed outright, with KILL, leaves its copies there, as other scratch is left.
  Where a copy cannot be made, as when the thread's `TMPDIR` is gone, it prints `no proof: no copy of the base could be made in <the directory>` or `no proof: no copy of the head could be made in <the directory>`, ends 1, and leaves the worktree on its branch: run the block again with `TMPDIR` on a directory that exists (`TMPDIR=/tmp bash "$T/proved.sh" ...`).
  The files laid over it are the tests and what they lean on: every changed file under a `tests/`, `test/`, `__tests__/` or `__snapshots__/` directory, each test, and each `conftest.py`, as `jbriefs.proved.TEST_FILE` has them.
  A branch whose every changed file, a deleted one too, is such a file or of a kind `jbriefs.proved.EXEMPT` names (docs, config, listed below) changes no code: the base's code is the head's own, so its tests pass there as well and a base run proves nothing.
  A test made faster, split or cleaned up is such a branch, and so is a removal of tests with the doc that named them.
  For it the block prints `tests only:`, makes no copy of the base, runs the tests in the head's copy alone, and prints `Proved: <tests> head exit <n> at <head>, tests only`; its `exempt` pattern matches the files `EXEMPT` covers.
  `jmerge` takes that line only where every file the pull request changes is such a file, or of a kind `jbriefs.proved.EXEMPT` names (docs, config), and the head exit is 0 (`jbriefs.proved.TEST_FILE`): a change to code still needs its base run to fail.
  At the base a test that cannot import what the change adds counts as failed, not as a collection error (`--continue-on-collection-errors`).
  A slot run that ends 76 got no slot, as in "test slots": after a short-lane 76 run the block again at once, and after a full-lane 76 end the turn and wait for jbus's message.
  A side that exited 0 at a committed head and base is kept in the worktree's `crew-proof-sides` (`git rev-parse --git-path crew-proof-sides`), and a run of the block at the same head and base prints `<side>: exited 0 at this head and base already, <its line>` and runs only the side still owed, so a wake after a cut side waited on a full slot runs that side alone; a run at another head or base runs both.
  A side that ends 124 in the short lane prints `<side>: stopped at the short lane's limit, no verdict: it runs again alone in a full slot`, and the `Proved:` line is of the full slot's run; one that ends 124 there too reached no verdict, the run after it does not start, and the block prints `no proof: the slot's run ended 124`: run it again.
  It proves the change where the base run exits 1 and the head run exits 0, and only then: an exit 2, 4 or 5 at the base (an error, a usage fault, no test collected) or a 124 proves nothing.
  On anything else, fix the tests until they fail without the change, commit, and run it again.
  A commit made, or an edit left in the worktree, while the call runs ends it with no `Proved:` line and exit 1, on `no proof: the head or the worktree moved while it ran: HEAD <head> is now <commit>` or `no proof: the head or the worktree moved while it ran: the worktree has changes: <files>`: commit the edit or drop it, then run the block again at the head as it is now.
  The `Proved:` line it prints goes, as printed, on the Result between `Proof:` and `Branch:`; once the brief has a Result, the block appends it itself.
  The line is of the head it ran at: a rebase or a merge of the base keeps it, and a push that changes the patch, a fix for a finding among them, runs the block again; the last `Proved:` line is the one `jmerge` reads.
  `jmerge` waits on a pull request that changes tests and whose Result has no `Proved:` line, one that does not name each test file it changes, one with a base exit other than 1 or a head exit other than 0, a `tests only` line, which has no base exit, where the pull request changes a file that is no test, docs or config, or one of a head whose patch the pull request's head no longer carries unchanged (`ready.short_on_proved`).

  A pull request that changes no test file writes `Proved: none, <kind>`, with `docs`, `config`, or `docs and config`, and is exempt.
  The block prints that line itself, and appends it once the brief has a Result, where every file is of a kind (`jbriefs --proved-none`).
  The kinds that are exempt, and the files each covers (`jbriefs.proved.EXEMPT`), are these:
  - `docs`: `*.md`, `*.txt`, `*.rst`, anything under a `docs/` directory, and a `.py` file whose change is to its docstrings and comments alone: its base and its head parse to the same code once docstrings are dropped (`jbriefs.proved.prose_only`), and a `Makefile` or `*.mk` file whose change is to its `#` comment lines alone: its base and its head have the same lines once comments are dropped (`jbriefs.proved.comments_only`), since no test can fail over a docstring or a comment without pinning its words.
  - `config`: `*.toml`, `*.json`, `*.yml`, `*.yaml`, `*.cfg`, `*.ini`, `*.conf`, `*.lock`, Go's `go.mod`, `go.sum`, `go.work` and `go.work.sum`, a dotfile such as `.gitignore`, and anything under `.github/`.

  `jmerge` waits on a `none` line where the pull request changes a test or a file of no kind the line names.
  A change to code is none of these: it adds or changes a test that fails without it.

  A branch that changes no test file and whose every other file is under a feature's `packaging/` folder (`jbriefs.proved.FORK_FILE`), or of an `EXEMPT` kind, changes a fork, such as T3 Code's patches in `features/t3code-jstack/packaging`, whose tests are inside its patches.
  For it the block lays each side's series over the tag its own `PKGBUILD` names, the head's with the head's patches and the base's with the base's patches and the head's test files over them, installs each with `vp i --frozen-lockfile`, and runs the vitest files the changed patches add or change, each through its package's own `test` script, in one full test slot.
  It prints `Proved: <fork tests> base exit <n> at <base>, head exit <n> at <head>, fork patches`, which proves the change where the base exits 1 and the head 0, as above, and `jmerge` takes only where every file the pull request changes is a fork file, docs or config (`jbriefs.proved.outside_fork`).
  A changed patch that adds or changes no vitest file prints `no proof: the fork patches it changes add or change no vitest file`: add the test to the patch.
  `jmerge` waits on a pull request that adds or changes a fork patch and has no `Proved:` line, as on one that changes a test; one that only edits the `PKGBUILD` or deletes a patch needs no line.
- If the brief says to open a pull request, its review comes first: once the checks pass and the first-push block below has pushed the branch, write the Result with `Branch: <branch>   Pull request: after the review` and end your turn, as "The review" says, and jbus launches the reviewer at the head you pushed.
  The pull request opens on jbus's message that the review is written, once its findings are handled, or at once where the brief says `Review: none`, on the base this prints.
  Do not merge.
  What follows it is under "Stay on the pull request".
  The base is the home's to give, never yours to choose.
  Where the task needs code that is only on an open row's branch, not on main, build on that branch in this worktree, commit, and pause with `Waits on: <that row>` on the Result: jbus stacks the task on that row's pull request, writes the `Stacked on:` line, and tells this thread to check and push on it.
  Never open a pull request on the default branch that carries another row's commits.
  Run this in this worktree, with the block at the top.
  It is the only check:

  ```sh
  B="$H/tasks/<slug>.md"
  stacked=$(uv run --project "$T/../source" jbriefs line stacked "$B")
  case $stacked in
  '') echo "no base: jbriefs could not read the brief's Stacked on: line" ;;
  malformed) echo "no base: the brief's Stacked on: line is not Stacked on: <slug> <branch>, and only jbus writes it" ;;
  none)
      if base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD); then
          echo "base ${base#origin/}: the default branch, the brief has no Stacked on: line"
      else
          echo "no base: the brief has no Stacked on: line, and the remote's default branch is not known here"
      fi
      ;;
  *)
      slug=${stacked%% *}
      branch=${stacked#* }
      branch=${branch%% *}
      if [ "${stacked% at *}" != "$stacked" ]; then
          echo "base $branch: the brief's Stacked on: line, moved onto $branch once $slug merged"
      else
          echo "base $branch: the brief's Stacked on: line, stacked on $slug's pull request"
      fi
      ;;
  esac
  ```

  On `base <branch>`, open the pull request with `--base <branch>`, and with the label this prints.
  A diff that touches two features is labelled `cross-cutting` by its crew when it opens, since the repo's borders check fails it without the label.
  Run this in this worktree, with `<branch>` the base it printed, as the only check of the label:

  ```sh
  base='<branch>'
  top=$(git rev-parse --show-toplevel)
  if [ ! -f "$top/scripts/lint-borders.py" ]; then
      echo "no label: this repo has no scripts/lint-borders.py"
  elif ! git fetch -q origin "$base" || ! said=$(python3 "$top/scripts/lint-borders.py" --base "origin/$base"); then
      echo "no label: the borders check could not read the diff from origin/$base"
  elif printf '%s\n' "$said" | command grep -q "label it cross-cutting"; then
      echo "label cross-cutting: the diff touches two features"
  else
      echo "no label: the diff touches one feature at most"
  fi
  ```

  On `label cross-cutting`, open it with `--label cross-cutting` too.
  A pull request already open whose diff a later push makes touch two features gets it with `gh pr edit --add-label cross-cutting`, and the borders check reruns when it is labelled.
  The pull request opens only on a head that merges cleanly into today's base: one opened on a base hours old is in conflict the moment it opens, and then waits on a rebase that races the next merge, as #1725 did, opened three hours behind main.
  Run this in this worktree right before you open it, with the block at the top and `<branch>` the base it printed, and open it only where it prints `open it`:

  ```sh
  G=$(git rev-parse --git-dir)
  B="$H/tasks/<slug>.md"
  base='<branch>'
  branch=$(git branch --show-current)
  if [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
      echo "the rebase stopped: resolve these as A conflict says, then git rebase --continue"
      git diff --name-only --diff-filter=U
  elif [ -f "$G/crew-before-rebase" ]; then
      echo "a rebase is not pushed yet: prove it and push it as A conflict says, then run this again"
  elif stacked=$(uv run --project "$T/../source" jbriefs line stacked "$B" 2> /dev/null) && [ "$stacked" != none ] && { [ "${stacked% at *}" = "$stacked" ] || ! git merge-base --is-ancestor "${stacked##* }" HEAD 2> /dev/null; }; then
      echo "open it: a link of a stack, jbus moves it onto its base's merge"
  elif [ "origin/$base" != "$(git symbolic-ref -q --short refs/remotes/origin/HEAD)" ]; then
      echo "open it: $base is the base of a link, and jbus moves a link"
  elif ! git fetch -q origin "$base"; then
      echo "not opened: could not fetch origin/$base"
  else
      tip=$(git rev-parse --short=12 "origin/$base")
      said=$(git merge-tree --write-tree --name-only "origin/$base" HEAD)
      merged=$?
      files=$(printf '%s\n' "$said" | sed -n '2,/^$/p' | sed '/^$/d' | paste -sd' ' -)
      pushed=$(git ls-remote origin "refs/heads/$branch" | cut -f 1)
      if [ "$merged" -eq 0 ]; then
          echo "open it: $(git rev-parse --short=12 HEAD) merges cleanly into origin/$base at $tip"
      elif [ "$merged" -ne 1 ]; then
          echo "not opened: git merge-tree could not merge origin/$base with the head"
      elif [ -z "$pushed" ]; then
          echo "not opened: origin has no $branch, so a rebase has no lease: push it with the first push block, then run this again"
      elif ! git update-ref "refs/jstack/pre-rebase/<slug>/$(git rev-parse --short=12 HEAD)" HEAD; then
          echo "not opened: could not keep the head under refs/jstack/pre-rebase, so no rebase"
      else
          echo "not opened: the head conflicts with origin/$base at $tip in $files: rebasing onto it first"
          echo "$(git rev-parse HEAD) $base $pushed" > "$G/crew-before-rebase"
          if out=$(git rebase -q "origin/$base" 2>&1); then
              echo "rebased onto origin/$base: prove it and push it as A conflict says, then run this again"
          elif [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
              echo "the rebase stopped: resolve these as A conflict says, then git rebase --continue"
              git diff --name-only --diff-filter=U
          else
              uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null
              echo "the rebase did not start: $out"
          fi
      fi
  fi
  ```

  It fetches the base each time, so it reads main as it is now and not as the worktree last saw it, and asks `git merge-tree` what GitHub's merge would: exit 0 is a head that merges cleanly, exit 1 a conflict.
  On a conflict it starts the rebase of "A conflict", with its record and its `refs/jstack/pre-rebase` ref, so the rest is that section's: resolve the files with `jmerge --remake` for the generated ones, prove no line was lost, check the new head with the guard tests and the lint, and push with its lease.
  Then run this again: main may have moved once more while you rebased, and the pull request opens on the first run that prints `open it`.
  A link of a stack opens at once, since jbus moves it once its base merged ("A link that moved").
  So does a link jbus already moved onto main, whose `Stacked on:` line ends `at <merge>`, until its head holds that merge: until then its branch holds its base's commits too, and a rebase onto main would replay them, as "A conflict" says, so the block reads the line by the same rule that section does.
  The first push of the branch is this block's, run in this worktree with the block at the top and the brief's slug in place of the words in angle brackets, before the pull request opens:

  ```sh
  B="$H/tasks/<slug>.md"
  head=$(git rev-parse HEAD)
  branch=$(git branch --show-current)
  if [ -n "$(git status --porcelain)" ]; then
      echo "no push: commit the work first"
      false
  elif [ ! -f "$B" ]; then
      echo "no push: there is no brief at $B"
      false
  elif ! why=$(uv run --project "$T/../source" python -c '
  import sys
  from pathlib import Path
  from jmerge import ready
  print(ready.short_on_checked(Path(sys.argv[1]).read_text(), sys.argv[2]))
  ' "$B" "$head"); then
      echo "no push: jmerge's rule could not read the Checked: line of $B"
      false
  elif [ -n "$why" ]; then
      echo "no push: $why"
      false
  elif git push -q -u origin "HEAD:refs/heads/$branch"; then
      echo "pushed: $branch at $head"
  else
      echo "no push: git push failed"
      false
  fi
  ```

  It asks `jmerge`'s own rule (`ready.short_on_checked`) of the brief's last `Checked:` line at the head, with no other head carried, and pushes only where the check block passed there: on `no push`, run the check block again at the head, fix what it finds, and run this block again.
  A failure, a 124, a missing line and a line of another head each refuse the push, so no review is launched and no pull request opens on a head whose desk check did not pass.
  jleak's `pre-push` hook asks the same rule of every head a crew's worktree pushes, the fix pushes of "The review" and "The checks" and a rebase's included, and refuses one it does not bind with `crew-push: refused: <why>: run the check block of "Do the task" at <head12>, then push again`.
  The hook holds since the door hook refuses a `git push` that skips it, by `--no-verify` or by a moved `core.hooksPath`; it runs no check itself, since the check takes a slot of its own, and this block stays to say why before a push is tried.
  A brief with a `Stacked on:` line in its head is a link jbus stacked: its row builds on a row whose pull request was open when it launched, and its worktree started from that pull request's branch.
  Its Result names the stack on its `Stacked on:` line, and jbus says when it moves ("A link that moved").
  The link stays stacked until its base merged, and only then does jbus move it and rewrite the line.
  On `no base`, open no pull request: write what it printed on the Result's `Left:` line and in what you tell the home.
