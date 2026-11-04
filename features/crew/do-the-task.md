- Once every **Done when** line holds, with the work committed, run the check of the change, once.
  In a repo whose pull request check selects its tests, jstack's `scripts/select_tests.py`, the check is the lint and only the tests that cover the files the branch changed since it left its base, in the short lane.
  The base is the branch the pull request goes on, as the block that opens it reads it from the brief: the branch of a `Stacked on:` line, and `origin/main` for a brief with none.
  A base branch that is gone, as one is once it merged, is `origin/main` too.
  It never takes a full slot: CI's check on the pull request runs every test the selection leaves out, and CI's check is the gate.
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
      elif ! tests=$(python3 scripts/select_tests.py "$base" HEAD); then
          echo "no check: scripts/select_tests.py could not select the tests"
          false
      else
          lint=
          case $tests in
          all)
              lint='PYTEST=:'
              echo "selected: all, the whole suite: lint only here, and CI's check runs every test"
              ;;
          '')
              lint='PYTEST=:'
              echo 'selected: none, no test covers this change: lint only'
              ;;
          *)
              echo "selected: $(printf '%s\n' "$tests" | wc -l | tr -d ' ') test files, in the short lane:"
              printf '%s\n' "$tests"
              ;;
          esac
          printf 'make check-fast BASE=%s %s\n' "$base" "$lint" > "$code.command"
          uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- make check-fast BASE="$base" $lint
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
  Give the call a time limit of 3 minutes (`timeout: 180000` in Claude Code), and never send it to the background.
  With every slot of the lane taken, it ends 76, and the turn ends as a targeted run's does, with the same one line.
  It ends with the exit code of `make check-fast`, and on 0 the `selected:` line and that exit code go on `Proof:`.
  The pull request is ready only once CI's check on it passed, as "The checks" says, and `Proof:` names CI's check at that head beside the selected run.
  On 124 the selected tests ran past the lane's time limit, which says nothing of the change: go on as on 0, opening the pull request, with the `Checked:` line's exit 124 saying the limit was hit, and let CI's check on the pull request be the proof, as `Proof:` then says.
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
  elif ! tests=$(git diff --name-only --diff-filter=d "$base" HEAD | grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$'); then
      echo "no test changed: the Result says Proved: none, <kind>, where every file it changes is of that kind"
  else
      tree=$(mktemp -d)
      git archive "$base" | tar -x -C "$tree"
      git diff --name-only --diff-filter=d "$base" HEAD | grep -E '(^|/)tests?/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$' |
          while read -r file; do
              mkdir -p "$tree/$(dirname "$file")"
              git show "HEAD:$file" > "$tree/$file"
          done
      (cd "$tree" && env -u VIRTUAL_ENV uv sync -q)
      list=$(printf '%s\n' "$tests" | paste -sd ' ')
      PROOF_TREE=$tree PROOF_TESTS=$list uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- bash -c '
          env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider $PROOF_TESTS > "$PROOF_TREE/.proof-head" 2>&1
          echo "head exit $?: $(tail -n 1 "$PROOF_TREE/.proof-head")"
          (cd "$PROOF_TREE" && env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider --continue-on-collection-errors $PROOF_TESTS) > "$PROOF_TREE/.proof-base" 2>&1
          echo "base exit $?: $(tail -n 1 "$PROOF_TREE/.proof-base")"
      ' | tee "$tree/.proof-said"
      ran=${PIPESTATUS[0]}
      at_head=$(sed -n 's/^head exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
      at_base=$(sed -n 's/^base exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
      if [ "$ran" != 0 ] || [ -z "$at_head" ] || [ -z "$at_base" ]; then
          echo "no proof: the slot's run ended $ran"
      else
          line="Proved: $list base exit $at_base at $base, head exit $at_head at $head"
          echo "$line"
          if grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi
      fi
      uv run --project "$T/../source" jbus forget "$tree"
  fi
  ```

  The head's tests run at the head, then laid over a copy of the base's tree in a venv of its own, so the base run imports the base's code and not the head's.
  The files laid over it are the tests and what they lean on: every changed file under a `tests/` or `test/` directory, and each `conftest.py`.
  At the base a test that cannot import what the change adds counts as failed, not as a collection error (`--continue-on-collection-errors`).
  A slot run that ends 76 is a wait for a slot, as in "test slots"; one that ends 124 hit the lane's time limit: lay over fewer tests, and run it again.
  It proves the change where the base run exits 1 and the head run exits 0, and only then: an exit 2, 4 or 5 at the base (an error, a usage fault, no test collected) or a 124 proves nothing.
  On anything else, fix the tests until they fail without the change, commit, and run it again.
  The `Proved:` line it prints goes, as printed, on the Result between `Proof:` and `Branch:`; once the brief has a Result, the block appends it itself.
  A later round that changes the tests runs it again, and the last `Proved:` line is the one `jmerge` reads.
  `jmerge` waits on a pull request that changes tests and whose Result has no `Proved:` line, one that does not name each test file it changes, or one with a base exit other than 1 or a head exit other than 0 (`ready.short_on_proved`).

  A pull request that changes no test file writes `Proved: none, <kind>`, with `docs`, `config`, or `docs and config`, and is exempt.
  The kinds that are exempt, and the files each covers (`jbriefs.proved.EXEMPT`), are these:
  - `docs`: `*.md`, `*.txt`, `*.rst`, and anything under a `docs/` directory.
  - `config`: `*.toml`, `*.json`, `*.yml`, `*.yaml`, `*.cfg`, `*.ini`, `*.lock`, a dotfile such as `.gitignore`, and anything under `.github/`.

  `jmerge` waits on a `none` line where the pull request changes a test or a file of no kind the line names.
  A change to code is none of these: it adds or changes a test that fails without it.
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
