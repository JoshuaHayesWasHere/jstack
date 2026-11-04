- Once every **Done when** line holds, with the work committed, run the check of the change, once.
  In a repo whose pull request check selects its tests, jstack's `scripts/select_tests.py`, the check is the lint and only the tests that cover the files the branch changed since it left its base, in two steps.
  The first step is the guards: the lint, the cross-cutting tests, the catch-all and the test files the branch changed (`select_tests.py --part guards`), under a full test slot, which has no time limit, so it always reaches a verdict, and it must pass.
  The second runs only once the guards passed: the rest of the selection, the tests the change reaches through imports, names and features (`--part rest`), in the short lane.
  The base is the branch the pull request goes on, as the block that opens it reads it from the brief: the branch of a `Stacked on:` line, and `origin/main` for a brief with none.
  A base branch that is gone, as one is once it merged, is `origin/main` too.
  It never runs the whole suite: CI's check on the pull request runs every test the selection leaves out, and CI's check is the gate.
  In any other repo the check is the repo's check command, the first line of `$H/fresh-check` with its `jgauge test-slot --` left off (the block takes the slot itself), under a full test slot, and it is that command and no other, whatever command a brief's **Done when** names for it.
  In a repo with no `$H/fresh-check`, the check command is the one the repo's own instructions name (`CLAUDE.md`, `AGENTS.md` or its `Makefile`).
  Run this in this worktree, with the block at the top, and the brief's slug and the check command in place of the words in angle brackets.
  Every run of the check this skill asks for, after a failed check, a rebase or a fix, is this block:

  ```sh
  B="$H/tasks/<slug>.md"
  head=$(git rev-parse HEAD)
  clean=$(git status --porcelain)
  out=$(mktemp)
  code=$(mktemp)
  {
  if [ -f scripts/select_tests.py ]; then
      on=$(awk '/^## / {exit} /^Stacked on:/ {print $(4); exit}' "$H/tasks/<slug>.md" 2> /dev/null)
      on=origin/${on:-main}
      git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
      if ! base=$(git merge-base "$on" HEAD); then
          echo "no check: the branch shares no commit with $on"
          false
      elif ! parts=$(python3 scripts/select_tests.py --part desk "$base" HEAD); then
          echo "no check: scripts/select_tests.py could not select the tests"
          false
      elif guards=$(printf '%s\n' "$parts" | sed -n 's/^guards //p') &&
          rest=$(printf '%s\n' "$parts" | sed -n 's/^rest //p') &&
          { [ "$parts" = all ] || [ -z "$guards$rest" ]; }; then
          if [ "$parts" = all ]; then
              echo "selected: all, the whole suite: lint only here, and CI's check runs every test"
          else
              echo 'selected: none, no test covers this change: lint only'
          fi
          printf 'make check-fast BASE=%s PYTEST=:\n' "$base" > "$code.command"
          uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- make check-fast BASE="$base" PYTEST=:
      else
          echo "selected: $(printf '%s' "$guards" | grep -c .) guard test files, which must pass, in a full slot:"
          printf '%s\n' "$guards" | grep .
          echo "then $(printf '%s' "$rest" | grep -c .) test files the change reaches, in the short lane, where the time limit passes:"
          printf '%s\n' "$rest" | grep .
          guarded="make check-fast BASE=$base PART=guards"
          printf '%s\n' "$guarded" > "$code.command"
          uv run --project "$T/../source" jgauge test-slot --thread '<thread id>' -- make check-fast BASE="$base" PART=guards
          first=$?
          if [ "$first" = 0 ] && [ -n "$rest" ]; then
              printf '%s exit 0, then the import-reached remainder, where exit 124 is the short lane%ss time limit and passes: make check-fast BASE=%s PART=rest\n' "$guarded" "'" "$base" > "$code.command"
              uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- make check-fast BASE="$base" PART=rest
          else
              (exit "$first")
          fi
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
  'jgauge check') tail -n 1 "$out" | grep -q '^done: the check exited ' || command= ;;
  esac
  if [ -n "$command" ] && [ "$ran" != 76 ] && [ -z "$clean" ] && [ -z "$(git status --porcelain)" ] &&
      [ "$(git rev-parse HEAD)" = "$head" ] && grep -q '^## Result' "$B" 2> /dev/null; then
      printf 'Checked: %s exit %s at %s\n' "$command" "$ran" "$head" >> "$B"
  fi
  (exit "$ran")
  ```

  A `no check:` line ends the block 1: nothing was checked, and it is no proof.
  Once the brief has a Result, the block adds `Checked: <the command> exit <its exit> at <the full head>` to it for a check that ran to its end on a committed head, which `jmerge` reads, and nobody writes that line by hand.
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), and never send it to the background: the guards take a few minutes on a busy machine.
  With every slot of a lane taken, it ends 76, and the turn ends as a targeted run's does, with the same one line.
  It ends with the exit code of the guards' `make check-fast` where they failed, and of the rest's where they passed, and on 0 the `selected:` line and that exit code go on `Proof:`.
  A guard step that fails is the change's to fix, whatever the rest would say: the rest does not run.
  The pull request is ready only once CI's check on it passed, as "The checks" says, and `Proof:` names CI's check at that head beside the selected run.
  On 124 the guards passed and the rest ran past the short lane's time limit, which says nothing of the change: go on as on 0, opening the pull request, with the `Checked:` line saying the guards passed and the import-reached remainder hit the limit, and let CI's check on the pull request be the proof, as `Proof:` then says.
  An exit 124 means this only after a guard step that passed, and the `Checked:` line names that step: the guards never run under the limit.
  In any other repo the block runs `jgauge check`, and the rest of this step is about that run.
  It starts the check command on its own, holding one of the machine-wide test slots, and the call waits on it for up to 9 minutes. Give the call a time limit of 10 minutes, the longest a call in the foreground gets (`timeout: 600000` in Claude Code), and never send it to the background. With every slot taken, nothing runs: the check registers this thread as a waiter, and the block prints `waiting` and ends 76. That wait is the one time the turn ends: end it at once with the one line above, and on jbus's message run this block again, which starts the check afresh. A check runs as long as the check command takes once it holds a slot, longer where the command runs the whole suite, so one call is not always enough: on `running`, run the block again, in this turn, as many times as it takes, until it prints `done`. Never end your turn while your own check runs, and never say you will go on once it finishes: nothing wakes a thread when a command ends, only a message does, and the push, the Result and the pull request would never come. A check that a call or a turn before this one started is joined, not started again (`joined`), and one that ended after the last call gives what it said (`checked`). A check whose answer a call already gave runs afresh on the next call, so a failure that was not the change's (a flake, a full `/tmp`) is run again by running the block again. On `stale`, the check ran on files that have changed since, and its answer is no proof: run the block again. On `done`, the block ends with the command's exit code: put its last line on `Proof:`. Never run the command a second way to get past the wait. Testing, not coding, is what uses up the machine, so the check command is not how you find out whether an edit works: the targeted runs are. Run it again only after changing something to fix what that run found.
- A repo's heavy suite (a browser end-to-end matrix, anything that runs under the machine-wide `heavy-suite.lock`) is part of that one run of the check command, and the crewmate runs it: once, under the test slot, and under the suite's own `heavy-suite.lock`, which the repo's command for the suite takes itself.
  While you work, run the checks your change touches (the spec files it edits or covers) and not the whole suite.
  A repo with no heavy suite has nothing more here: its check command is the whole of it.
- If the brief says to open a pull request, open it once the checks pass, on the base this prints. Do not merge. What follows it is under "Stay on the pull request". The base is the home's to give, never yours to choose. Run this in this worktree, with the block at the top. It is the only check:

  ```sh
  B="$H/tasks/<slug>.md"
  stacked=$(awk '/^## / {exit} /^Stacked on:/ {print; exit}' "$B")
  if [ -n "$stacked" ]; then
      printf '%s\n' "$stacked" | awk '{
          if (NF == 4) print "base " $(4) ": the brief\047s Stacked on: line, stacked on " $(3) "\047s pull request"
          else if (NF == 6 && $(5) == "at") print "base " $(4) ": the brief\047s Stacked on: line, moved onto " $(4) " once " $(3) " merged"
          else print "no base: the brief\047s Stacked on: line is not Stacked on: <slug> <branch>, and only jbus writes it"
      }'
  elif base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD); then
      echo "base ${base#origin/}: the default branch, the brief has no Stacked on: line"
  else
      echo "no base: the brief has no Stacked on: line, and the remote's default branch is not known here"
  fi
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
  elif printf '%s\n' "$said" | grep -q "label it cross-cutting"; then
      echo "label cross-cutting: the diff touches two features"
  else
      echo "no label: the diff touches one feature at most"
  fi
  ```

  On `label cross-cutting`, open it with `--label cross-cutting` too.
  A pull request already open whose diff a later push makes touch two features gets it with `gh pr edit --add-label cross-cutting`, and the borders check reruns when it is labelled.
  A brief with a `Stacked on:` line in its head is a link jbus stacked: its row builds on a row whose pull request was open when it launched, and its worktree started from that pull request's branch.
  Its Result names the stack on its `Stacked on:` line, and jbus says when it moves ("A link that moved").
  The link stays stacked until its base merged, and only then does jbus move it and rewrite the line.
  On `no base`, open no pull request: write what it printed on the Result's `Left:` line and in what you tell the home.
