- Once every **Done when** line holds, with the work committed, run the check of the change, once.
  CI is the check of record: its check on the pull request runs every test the change selects, and it is the gate.
  The desk's check is the lint and the touched tests, and never the whole suite or the selection.
  In a repo whose pull request check selects its tests, jstack's `scripts/select_tests.py`, the touched tests are the test files the branch adds or edits since it left its base (`select_tests.py --part touched`), and the check is `make check-fast BASE=<base> PART=touched`, run in steps: the lint first, then each touched test file alone, each step its own call of `jgauge test-slot --short`.
  A step the short lane stops at its time limit (exit 124) runs again alone in a full test slot, which has no time limit, so every step reaches a verdict however loaded the machine is.
  A 124 is never a pass and never a failure: it is no verdict.
  The cross-cutting tests, the catch-all and the tests the change reaches through imports, names and features are CI's to run: the desk does not run them.
  A change of the tests alone, where every changed path is a module of a folder of tests that the head still holds, selects only the changed test files and the tests that import or name a helper they changed, so CI runs no catch-all for it, and a cross-cutting test only where it is one of those.
  The base is the branch the pull request goes on, as the block that opens it reads it from the brief: the branch of a `Stacked on:` line, and `origin/main` for a brief with none.
  A base branch that is gone, as one is once it merged, is `origin/main` too.
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
      elif ! touched=$(python3 scripts/select_tests.py --part touched "$base" HEAD); then
          echo "no check: scripts/select_tests.py could not name the touched tests"
          false
      else
          printf 'make check-fast BASE=%s PART=touched\n' "$base" > "$code.command"
          steps=$(git rev-parse --git-path crew-check-steps)
          [ "$(sed -n 1p "$steps" 2> /dev/null)" = "$head $base" ] || printf '%s %s\n' "$head" "$base" > "$steps"
          echo "touched: $(printf '%s' "$touched" | command grep -c .) test files, each alone in the short lane after the lint; CI's check runs the rest of the selection"
          ran=0
          for step in lint $touched; do
              if command grep -qxF "passed $step" "$steps"; then
                  echo "$step: passed at this head already"
                  continue
              fi
              if [ "$step" = lint ]; then
                  set -- make check-fast BASE="$base" PYTEST=: PART=touched
              else
                  set -- make test TESTS="$step"
              fi
              started=$(date +%s)
              lane=short
              uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- "$@"
              said=$?
              if [ "$said" = 124 ]; then
                  echo "$step: stopped at the short lane's limit, no verdict: it runs again alone in a full slot"
                  lane=full
                  uv run --project "$T/../source" jgauge test-slot --thread '<thread id>' -- "$@"
                  said=$?
              fi
              echo "$step: exit $said in $(($(date +%s) - started)) s, $lane lane"
              case $said in
              0) [ -n "$clean" ] || echo "passed $step" >> "$steps" ;;
              76)
                  ran=76
                  break
                  ;;
              124) ran=124 ;;
              *)
                  ran=$said
                  break
                  ;;
              esac
          done
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
  For a selected check the line reads `Checked: make check-fast BASE=<base> PART=touched exit <n> at <head>`, and the block prints each step as `<step>: exit <n> in <s> s, <lane> lane`, the step `lint` or a test file.
  The block's exit is the first step's failure where one failed, and it stops there; else 124 where a step reached no verdict even in a full slot; else 0.
  A step that passed at a committed head is kept in the worktree's `crew-check-steps` (`git rev-parse --git-path crew-check-steps`), and a run of the block at the same head and base skips it, so a wait for a slot, or a call cut at its time limit, never starts the check over.
  `jmerge` merges a pull request only once its last `Checked:` line says the desk's check (`PART=touched`, a `PART=guards` line of an earlier head, or another repo's `jgauge check`) exited 0 at its head, or at a head whose patch the head carries unchanged (`ready.short_on_checked`): a missing line, a failure, a 124 and a line of a head whose patch changed since each hold it, until this block runs again at the head.
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), and never send it to the background: a step that falls back to a full slot can take minutes on a busy machine.
  With every slot of a lane taken, it ends 76, and the turn ends as a targeted run's does, with the same one line; on jbus's message run the block again, and it goes on from the first step that has not passed.
  It ends with the check's exit code, and on 0 the `touched:` line, each step's line and that exit code go on `Proof:`.
  A step that fails is the change's to fix, and every exit but 0 holds the pull request: a 124 reached no verdict, so run the block again.
  The pull request is ready only once CI's check on it passed, as "The checks" says, and `Proof:` names CI's check at that head beside the desk's run.
  In any other repo the block runs `jgauge check`, and the rest of this step is about that run.
  It starts the check command on its own, holding one of the machine-wide test slots, and the call waits on it for up to 9 minutes. Give the call a time limit of 10 minutes, the longest a call in the foreground gets (`timeout: 600000` in Claude Code), and never send it to the background. With every slot taken, nothing runs: the check registers this thread as a waiter, and the block prints `waiting` and ends 76. That wait is the one time the turn ends: end it at once with the one line above, and on jbus's message run this block again, which starts the check afresh. A check runs as long as the check command takes once it holds a slot, longer where the command runs the whole suite, so one call is not always enough: on `running`, run the block again, in this turn, as many times as it takes, until it prints `done`. Never end your turn while your own check runs, and never say you will go on once it finishes: nothing wakes a thread when a command ends, only a message does, and the push, the Result and the pull request would never come. A check that a call or a turn before this one started is joined, not started again (`joined`), and one that ended after the last call gives what it said (`checked`). A check whose answer a call already gave runs afresh on the next call, so a failure that was not the change's (a flake, a full `/tmp`) is run again by running the block again. On `stale`, the check ran on files that have changed since, and its answer is no proof: run the block again. On `done`, the block ends with the command's exit code: put its last line on `Proof:`. Never run the command a second way to get past the wait. Testing, not coding, is what uses up the machine, so the check command is not how you find out whether an edit works: the targeted runs are. Run it again only after changing something to fix what that run found.
- A repo's heavy suite (a browser end-to-end matrix, anything that runs under the machine-wide `heavy-suite.lock`) is part of that one run of the check command, and the crewmate runs it: once, under the test slot, and under the suite's own `heavy-suite.lock`, which the repo's command for the suite takes itself.
  While you work, run the checks your change touches (the spec files it edits or covers) and not the whole suite.
  A repo with no heavy suite has nothing more here: its check command is the whole of it.
- Once the check passed, prove the change with the tests it changes: each `test_*.py` or `*_test.py` the branch adds or changes since its base fails over the base's code and passes at the head.
  A run of a whole suite, or of tests that pass at the base as well, proves nothing: #968's `Proves it` printed 853 passed at its base while its named test failed there.
  Run this in this worktree, with the block at the top, and the brief's slug and this thread's id in place of the words in angle brackets:

  ```sh
  B="$H/tasks/<slug>.md"
  on=$(awk '/^## / {exit} /^Stacked on:/ {print $(4); exit}' "$B" 2> /dev/null)
  on=origin/${on:-main}
  git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
  head=$(git rev-parse HEAD)
  if [ -n "$(git status --porcelain)" ]; then
      echo "no proof: commit the work first"
  elif ! base=$(git merge-base "$on" HEAD); then
      echo "no proof: the branch shares no commit with $on"
  elif ! tests=$(git diff --name-only --diff-filter=d "$base" HEAD | command grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$'); then
      echo "no test changed: the Result says Proved: none, <kind>, where every file it changes is of that kind"
  else
      kept='(^|/)tests?/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$'
      exempt='(^|/)(docs|\.github)/|(^|/)\.[^/]*$|\.(md|txt|rst|toml|json|yml|yaml|cfg|ini|lock)$'
      tree=$(mktemp -d)
      if git diff --name-only --no-renames "$base" HEAD | command grep -vE "$kept" | command grep -qvE "$exempt"; then
          only=
          sides='head base'
          git clone -q --shared --no-checkout . "$tree"
          git -C "$tree" checkout -q --detach "$base"
          git diff --name-only --diff-filter=d "$base" HEAD | command grep -E "$kept" |
              while read -r file; do
                  mkdir -p "$tree/$(dirname "$file")"
                  git show "HEAD:$file" > "$tree/$file"
              done
          (cd "$tree" && env -u VIRTUAL_ENV uv sync -q)
      else
          only=1
          sides=head
          echo "tests only: every file the branch changes is a test, docs or config, so its tests run at the head alone"
      fi
      list=$(printf '%s\n' "$tests" | paste -sd ' ' -)
      : > "$tree/.proof-said"
      for side in $sides; do
          if [ "$side" = head ]; then at=$PWD more=; else at=$tree more=--continue-on-collection-errors; fi
          PROOF_AT=$at PROOF_MORE=$more PROOF_SIDE=$side PROOF_OUT=$tree/.proof-$side PROOF_TESTS=$list uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- bash -c '
              cd "$PROOF_AT" || exit
              workers=
              if env -u VIRTUAL_ENV uv run python -c "import xdist" > /dev/null 2>&1; then workers="-n auto --dist worksteal"; fi
              env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider $workers $PROOF_MORE $PROOF_TESTS > "$PROOF_OUT" 2>&1
              echo "$PROOF_SIDE exit $?: $(tail -n 1 "$PROOF_OUT")"
          ' | tee -a "$tree/.proof-said"
          ran=${PIPESTATUS[0]}
          [ "$ran" = 0 ] || break
      done
      at_head=$(sed -n 's/^head exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
      at_base=$(sed -n 's/^base exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
      line=
      if [ "$ran" != 0 ] || [ -z "$at_head" ] || { [ -z "$only" ] && [ -z "$at_base" ]; }; then
          echo "no proof: the slot's run ended $ran"
      elif [ -n "$only" ]; then
          line="Proved: $list head exit $at_head at $head, tests only"
      else
          line="Proved: $list base exit $at_base at $base, head exit $at_head at $head"
      fi
      if [ -n "$line" ]; then
          echo "$line"
          if command grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi
      fi
  fi
  ```

  The head's tests run at the head, then laid over a copy of the base's files with a venv of its own, so the base run imports the base's code and not the head's.
  The head run and the base run each take a short slot of their own, so each has the lane's whole time limit, and each runs on pytest's workers (`-n auto --dist worksteal`) where the tree's venv has pytest-xdist, on one process where it has not.
  The copy is a clone of this repo in a temp directory, checked out at the base and sharing this repo's objects, not a git worktree: it is a repository of its own, so a test that runs git there reads the base, and it leaves `git worktree list` here as it was, whether the tests pass, fail or the call is cut off.
  The block needs no `git worktree remove`, which the door hook refuses as a deletion of data (`deletes data`), refusing the whole call with it.
  The copy stays in the temp directory, as scratch does.
  The files laid over it are the tests and what they lean on: every changed file under a `tests/` or `test/` directory, each `test_*.py` or `*_test.py`, and each `conftest.py`.
  A branch whose every changed file, a deleted one too, is such a file or of a kind `jbriefs.proved.EXEMPT` names (docs, config, listed below) changes no code: the base's code is the head's own, so its tests pass there as well and a base run proves nothing.
  A test made faster, split or cleaned up is such a branch, and so is a removal of tests with the doc that named them.
  For it the block prints `tests only:`, makes no copy, runs the tests at the head alone, and prints `Proved: <tests> head exit <n> at <head>, tests only`; its `exempt` pattern matches the files `EXEMPT` covers.
  `jmerge` takes that line only where every file the pull request changes is such a file, or of a kind `jbriefs.proved.EXEMPT` names (docs, config), and the head exit is 0 (`jbriefs.proved.TEST_FILE`): a change to code still needs its base run to fail.
  At the base a test that cannot import what the change adds counts as failed, not as a collection error (`--continue-on-collection-errors`).
  A slot run that ends 76 is a wait for a slot, as in "test slots"; one that ends 124 hit the lane's time limit in the head run or the base run, and the run after it does not start: lay over fewer tests, and run it again.
  It proves the change where the base run exits 1 and the head run exits 0, and only then: an exit 2, 4 or 5 at the base (an error, a usage fault, no test collected) or a 124 proves nothing.
  On anything else, fix the tests until they fail without the change, commit, and run it again.
  The `Proved:` line it prints goes, as printed, on the Result between `Proof:` and `Branch:`; once the brief has a Result, the block appends it itself.
  The line is of the head it ran at: a rebase or a merge of the base keeps it, and a push that changes the patch, a fix for a finding among them, runs the block again; the last `Proved:` line is the one `jmerge` reads.
  `jmerge` waits on a pull request that changes tests and whose Result has no `Proved:` line, one that does not name each test file it changes, one with a base exit other than 1 or a head exit other than 0, a `tests only` line, which has no base exit, where the pull request changes a file that is no test, docs or config, or one of a head whose patch the pull request's head no longer carries unchanged (`ready.short_on_proved`).

  A pull request that changes no test file writes `Proved: none, <kind>`, with `docs`, `config`, or `docs and config`, and is exempt.
  The kinds that are exempt, and the files each covers (`jbriefs.proved.EXEMPT`), are these:
  - `docs`: `*.md`, `*.txt`, `*.rst`, and anything under a `docs/` directory.
  - `config`: `*.toml`, `*.json`, `*.yml`, `*.yaml`, `*.cfg`, `*.ini`, `*.lock`, a dotfile such as `.gitignore`, and anything under `.github/`.

  `jmerge` waits on a `none` line where the pull request changes a test or a file of no kind the line names.
  A change to code is none of these: it adds or changes a test that fails without it.
- If the brief says to open a pull request, open it once the checks pass and the first-push block below has pushed the branch, on the base this prints.
  Do not merge.
  What follows it is under "Stay on the pull request".
  The base is the home's to give, never yours to choose.
  Run this in this worktree, with the block at the top.
  It is the only check:

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
  elif printf '%s\n' "$said" | command grep -q "label it cross-cutting"; then
      echo "label cross-cutting: the diff touches two features"
  else
      echo "no label: the diff touches one feature at most"
  fi
  ```

  On `label cross-cutting`, open it with `--label cross-cutting` too.
  A pull request already open whose diff a later push makes touch two features gets it with `gh pr edit --add-label cross-cutting`, and the borders check reruns when it is labelled.
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
  A failure, a 124, a missing line and a line of another head each refuse the push, so no pull request opens on a head whose desk check did not pass.
  It is a block and not a git hook: a flag of `git push` skips a hook, and the check takes a slot of its own.
  A brief with a `Stacked on:` line in its head is a link jbus stacked: its row builds on a row whose pull request was open when it launched, and its worktree started from that pull request's branch.
  Its Result names the stack on its `Stacked on:` line, and jbus says when it moves ("A link that moved").
  The link stays stacked until its base merged, and only then does jbus move it and rewrite the line.
  On `no base`, open no pull request: write what it printed on the Result's `Left:` line and in what you tell the home.
