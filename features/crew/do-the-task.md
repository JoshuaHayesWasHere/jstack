## Do the task

- The **Done when** list is the whole target. Write the tests for it first where the repo has tests.
- The brief is trusted. Read the files it names; where it names none, read only what the task needs. Do not check its findings again, and do not explore beyond it. If a finding turns out wrong, say so in the result and read only what that needs.
- Stay inside **Where** and out of **Do not touch**. If the task cannot be done without crossing that line, stop and say so.
- While you work, run only the tests that cover the files you change, never the whole suite, in the short lane of the test slots. Run this in this worktree, with the block at the top and the tests in place of the words in angle brackets (in a Python repo, `uv run pytest <those test files>`):

  ```sh
  uv run --project "$T/.." jgauge test-slot --short --thread <thread id> -- <the targeted tests>
  ```

  The short lane has slots of its own, which no full suite takes, so a targeted run never waits behind one. A run still going at the lane's time limit (`jgauge test-slot --help` gives it) is stopped, exit 124, and says so: run fewer files at once. The check command is never run in the short lane.

  `<thread id>` is this thread's own id: the `t3-code` server's `t3_thread_configuration` with no arguments gives it as `threadId` (if your harness defers it, load it first). With `--thread` the call waits for no slot. When every slot of the lane is taken it registers this thread as a waiter, prints one line saying so, and ends 76. Then end your turn at once, with one line: `Waiting on a test slot: jbus will wake this thread when one is free.` Never poll for a slot, never loop on the call, never wait in a background job, and never end the turn with nothing said: `jbus poll` sends this thread one message when a slot of the lane is free, and that message is the wake. On it, run the same command again. If the slots are taken again by then, the call registers this thread again and you stop again: each wait is woken once. On a machine with no jbus nothing wakes a waiter: leave `--thread <thread id>` off, and the call waits in place.
- Once every **Done when** line holds, run the repo's check command (`notes.md` names it), once, under a test slot. It is that command and no other, whatever command a brief's **Done when** names for it. Run this in this worktree, with the block at the top and the check command in place of the words in angle brackets. Every run of the check command this skill asks for, after a failed check, a rebase or a fix, is this block:

  ```sh
  G=$(git rev-parse --path-format=absolute --git-dir)
  C="$G/crew-check"
  limit=540
  index="$G/crew-check.index"
  rm -f "$index"
  cp "$(git rev-parse --path-format=absolute --git-path index)" "$index" 2> /dev/null
  tree=$(GIT_INDEX_FILE="$index" git add -A && GIT_INDEX_FILE="$index" git write-tree)
  rm -f "$index"
  running() { [ -f "$C/pid" ] && ! [ -f "$C/exit" ] && kill -0 "$(cat "$C/pid")" 2> /dev/null; }
  if running; then
      if [ "$(cat "$C/tree")" = "$tree" ]; then
          echo "joined: the check an earlier call started on this worktree still runs, so it is waited on and not started again"
      else
          echo "joined: a check an earlier call started still runs, on the worktree as it was then: it is waited on and not started again, and once it is done this block is run again for the worktree as it is now"
      fi
  elif [ -f "$C/exit" ] && ! [ -f "$C/told" ] && [ "$(cat "$C/tree" 2> /dev/null)" = "$tree" ]; then
      echo "checked: the check of this worktree as it is now ended after the last call, and this is what it said"
  else
      rm -rf "$C" && mkdir -p "$C" && echo "$tree" > "$C/tree"
      cat > "$C/run" << 'THE_CHECK_ENDS_HERE'
  <check command>
  THE_CHECK_ENDS_HERE
      perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die' sh -c 'echo $$ > "${1}/pid"; uv run --project "${2}" jgauge test-slot --thread "${3}" -- sh "${1}/run" > "${1}/out" 2>&1; echo $? > "${1}/exit"' check "$C" "$T/.." '<thread id>' < /dev/null > /dev/null 2>&1 &
      for second in 1 2 3 4 5 6 7 8 9 10; do [ -f "$C/pid" ] && break; sleep 1; done
      echo "started: the check runs on this worktree as it is now, and this call waits on it"
  fi
  waited=0
  while ! [ -f "$C/exit" ] && running && [ "$waited" -lt "$limit" ]; do
      sleep 1
      waited=$((waited + 1))
  done
  if [ "$(cat "$C/exit" 2> /dev/null)" = 76 ] && grep -q "is registered as a waiter" "$C/out"; then
      cat "$C/out"
      rm -rf "$C"
      echo "waiting: no test slot is free and nothing ran: end your turn now with the one line, and run this block again when jbus wakes this thread"
      (exit 76)
  elif [ -f "$C/exit" ] && [ "$(cat "$C/tree")" != "$tree" ]; then
      touch "$C/told"
      echo "stale: the check exited $(cat "$C/exit") on the worktree as it was when it started, which has changed since: run this block again, and it checks the worktree as it is now"
      (exit 75)
  elif [ -f "$C/exit" ]; then
      touch "$C/told"
      tail -n 20 "$C/out"
      echo "done: the check exited $(cat "$C/exit")"
      (exit "$(cat "$C/exit")")
  elif running; then
      echo "running: $(tail -n 1 "$C/out" 2> /dev/null). Run this block again now, in this turn, and again until it prints done: never end your turn while it runs"
  else
      echo "lost: the check stopped with no exit code: run this block again, and it starts the check afresh"
  fi
  ```

  It starts the check command on its own, holding one of the machine-wide test slots, and the call waits on it for up to 9 minutes. Give the call a time limit of 10 minutes, the longest a call in the foreground gets (`timeout: 600000` in Claude Code), and never send it to the background. With every slot taken, nothing runs: the check registers this thread as a waiter, and the block prints `waiting` and ends 76. That wait is the one time the turn ends: end it at once with the one line above, and on jbus's message run this block again, which starts the check afresh. A check runs as long as the check command takes once it holds a slot, longer where the command runs the whole suite, so one call is not always enough: on `running`, run the block again, in this turn, as many times as it takes, until it prints `done`. Never end your turn while your own check runs, and never say you will go on once it finishes: nothing wakes a thread when a command ends, only a message does, and the push, the Result and the pull request would never come. A check that a call or a turn before this one started is joined, not started again (`joined`), and one that ended after the last call gives what it said (`checked`). A check whose answer a call already gave runs afresh on the next call, so a failure that was not the change's (a flake, a full `/tmp`) is run again by running the block again. On `stale`, the check ran on files that have changed since, and its answer is no proof: run the block again. On `done`, the block ends with the command's exit code: put its last line on `Proof:`. Never run the command a second way to get past the wait. Testing, not coding, is what uses up the machine, so the check command is not how you find out whether an edit works: the targeted runs are. Run it again only after changing something to fix what that run found.
- A repo's heavy suite (a browser end-to-end matrix, anything that runs under the machine-wide `heavy-suite.lock`) is part of that one run of the check command, and the crewmate runs it: once, under the test slot, and under the suite's own `heavy-suite.lock`, which the repo's command for the suite takes itself. While you work, run the checks your change touches (the spec files it edits or covers) and not the whole suite. The reviewer never runs it, whatever the brief's `Review:` line or the repo's `notes.md` says. A repo with no heavy suite has nothing more here: its check command is the whole of it.
- Write each Markdown prose line you add or change as one sentence, and leave old lines as they are: jstack's check (`features/writing/scripts/prose_lint.py`) fails a new line that holds two.
- Keep the proof as you go: for each **Done when** line, the command you ran and what it printed, or what you looked at. It goes on the Result's `Proof:` line, and a **Done when** line with no proof there is "does not hold".
- When every **Done when** line holds, stop. Do not go looking for more to improve. Anything noticed that is outside the task goes in the result under "Noticed", not into the diff.
- Before the pull request opens, with the work committed, ask which changed files the brief's **Where** does not cover.
  Run this in this worktree, with the block at the top and the brief's slug in place of the words in angle brackets:

  ```sh
  uv run --project "$T/.." jmerge --scope <slug>
  ```

  It prints nothing when every changed file is inside **Where**.
  It prints `outside: <path>` for a file that is not, and `wider: <path>: <why>` for one the Result's `Wider:` line already gives a reason for.
  Do not reason about it from the diff: this is the answer.
  For each `outside:` line, take the file out of the diff when the task does not need it.
  When it does, a test the change breaks, a page tied to a changed `--help`, keep one line for each file, `Wider: <path>: <why it had to change>`, for the Result.
  It goes in the Result "End" writes, after the pull request opens, and not in a `## Result` of its own before it: the command reads the last Result, and prints `wider:` for the file from then on.
  The pull request opens either way.
  A file left `outside:` with no `Wider:` line is a finding of the review.

- If the brief says to open a pull request, open it once the checks pass, on the base this prints. Do not merge. What follows it is under "Stay on the pull request". The base is the home's to give, never yours to choose. Run this in this worktree, with the block at the top. It is the only check:

  ```sh
  B="$H/tasks/<slug>.md"
  line=$(awk '/^## / {exit} /^Stack:/ {print; exit}' "$B")
  if [ -n "$line" ]; then
      printf '%s\n' "$line" | awk '{
          if (NF == 5 && $(3) ~ /^[0-9]+$/ && $(4) == "on") print "base " $(5) ": the brief\047s Stack: line, link " $(3) " of the stack " $(2)
          else print "no base: the brief\047s Stack: line is not Stack: <name> <place> on <branch>, and only the home writes it"
      }'
  elif base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD); then
      echo "base ${base#origin/}: the default branch, the brief has no Stack: line"
  else
      echo "no base: the brief has no Stack: line, and the remote's default branch is not known here"
  fi
  ```

  On `base <branch>`, open the pull request with `--base <branch>`. A brief with a `Stack:` line in its head is a link of a stack: its base is the branch of the link under it, the one this thread's worktree started from. On `no base`, open no pull request: say what it printed in the Result under "Noticed" and in what you tell the home.

The user may steer in this thread at any time. What they say here overrides the brief; record it in the result.

A question only the user can answer does not wait. A gate acts unless stopped: take the default you would recommend, act on it at once, carry on with everything, what depends on the default included, and park the question as a gate: read `$T/gates.md` now, the gate's lines and the rule under them, and fill the lines in. The one exception is a default that is irreversible or slow to revert, one of the six cases of the table in `$T/gates.md`: undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. Do not act on that one. Do its fail-safe (the dry-run, the bundle, the plan or diff, the exact artifact), add the `Holds:` and `Fail-safe:` lines under `Undo:`, and carry on with what does not depend on it: the action waits for the user's answer. Leave its `<n>` as it is: jbus numbers the question and is the one place it is kept. A gate goes to jbus and not into the home's thread: the user answers it wherever they are, and jbus closes it, or closes it with its default when the user has not answered in 2 hours and it has no `Holds:` line. Under the gate go one `Context:` line and one `Option:` line for every option you weighed, the default you took among them, which is the one you recommend, marked `(default, recommended)`, and the rest with no mark. Run this in this worktree, with the block at the top and the filled-in lines in place of the line in angle brackets:

```sh
gate=$(cat << 'THE_GATE_ENDS_HERE'
<the gate, filled in>
Context: <what the user needs to know to answer it, in one line, with the links to it>
Option: <an option's short name> (default, recommended): <what follows from it>
THE_GATE_ENDS_HERE
)
if ! command -v jbus > /dev/null; then
    echo "to the home: jbus is not installed here"
elif said=$(printf '%s\n' "$gate" | jbus gate '<slug>' 2>&1); then
    echo "sent to jbus: $said"
    printf '%s\n' "$said" | sed -n 's/^[a-z ]*: question \([0-9][0-9]*\).*/Gate: question \1/p'
else
    case $said in
    'not sent: '*) echo "$said" ;;
    *) echo "to the home: jbus said: $said" ;;
    esac
fi
```

`jbus gate` checks the lines against `$T/gates.md`, the one copy of their shape, and refuses what they lack with `not sent: <why>`.
It speaks for the project whose repo this worktree is of, and refuses a repo its config does not name.
On `sent to jbus`, send the home nothing.
The line under it, `Gate: question <number>`, is all the Result keeps of the gate: add it under "Noticed", as printed, and no line of the gate itself.
Where the first line says `already answered: question <number>:`, nothing was asked: the same question was answered before, and the line gives that answer.
Go by it, and take the default back where it differs.
On `to the home`, jbus holds nothing: send the lines, under a first line `<slug>: gate`, to the thread "Telling the home" finds, and with no home there put them in the Result under "Noticed", the one place left that can hold them.
On `not sent`, nothing was queued: fill in the line it names and run it again.
An answer that differs from the default comes back as a message here, from jbus.
A review finding you cannot settle without the user's word is such a question.
Only the four pauses of "Carry on" are asked here and waited on.
