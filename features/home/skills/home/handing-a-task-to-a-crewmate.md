## Handing a task to a crewmate

The root home does step 1 and no other: it queues the brief by "Queueing a row in a child" (`scoped-homes.md`), and jbus's pass launches it.

1. Write the brief, `tasks/<slug>.md`, from the plan entry, in the shape of `$T/brief.md`: read it first.
   Its `Home:` line names a home and never a thread.
   A scoped home writes `Home: <scope>`, the word step 1 of "When a home starts" printed after `scope`, and the root home writes `Home: <child>`, the scope whose goal the work serves or `uncategorized`: `jbus queue add` refuses a brief with no `Home:` line, or one that names no home of the project.
   The crewmate, and its reviewer when it must, read the id in that home's `home-id` each time they send, so the brief is not changed when the home hands off.
   A brief a scout wrote is already there: check that its `Home:` line is as this says and that its `Size:` line is its plan entry's size, set each if not, and go to step 2.

   The user's request is kept once, in `$H/asked/<entry>.md`, under `$H` and never under a scope's `$M`, with `<entry>` the plan entry the request became.
   The home writes the file when it takes the request, before it cuts the first brief, and never once per brief.
   It holds the user's messages of the request, word for word, each under its time and its message id, and the earlier words the user's reason or example comes from, each with its own time and id, and the pictures the user sent, by their paths.
   A later message of the user's that adds to the same request is added to the same file.
   Every brief cut from that request names the file on its `Asked:` line, and keeps only its own slice on `Task:`.
   A quote on `Task:` holds only words the file holds, as the user typed them, and the home's own words, such as which slice this brief is, go outside the quotes.
   A brief that comes from no message of the user's, such as a fix jbus filed or a scout's finding, has no `Asked:` line.
   `jbus queue add` and `jbus queue check` warn of an `Asked:` path that is no file under `$H/asked/`, and of a `Task:` quote whose words the file does not hold, and queue the brief all the same: mend the line and add the brief again.
   An edit of the `Asked:` line keeps the go.

   Its `Proves it:` line, under the "Done when" list, names what outside the agent shows the task is done: a test or a command, a metric, a dataset, an external judge or the user.
   `jbus queue add` queues no brief whose line names only the crew, the crewmate, the reviewer, the agent, the model or a review, or is empty.
   A crewmate's desk check is the crew skill's touched check, `make check-fast BASE=<base> PART=touched`: the lint, the test files the branch adds or edits, and the repo-guards tests the selection names (`select_tests.py --part guards`).
   The whole suite, `make check-fast BASE=origin/main` with no `PART=` or `make check`, is CI's check on the pull request, never a desk step a brief asks for: it holds a full test slot for about 9 minutes, and CI runs it again.
   Write the line to name the touched check and the test the task adds, as `Proves it: the touched check passes, with the test the task adds, <its test file>`.
   `jbus queue add` warns of a brief whose `Proves it:` or **Done when** runs the whole suite at the desk, and queues it all the same: a task about the suite itself may need the whole run.

   Each **Done when** line ends with the file it lands in, the one its goal needs changed, as ``(in `<path>`)``, or `(in none)` where it changes no file.
   A line that lands outside **Where**, or under **Do not touch**, is not this brief's: widen **Where** when the file is this change's, and otherwise move the line to a follow-up brief with a `Follows: <slug>` line, queued with `jbus queue add`, where it is approved on this row's go.
   Do it now, before the go: an edit of **Done when** or **Where** after it voids the go.
   `jbus queue add` refuses such a line and warns of a line with no marker.
   It also warns of a **Done when** list of 5 or more items (``warning: <slug>'s brief's Done when: lists <n> items``) and queues the brief all the same: split the row as "One entry per task" says (`SKILL.md`), and never fold items into fewer lines.

   A **Done when** line that asks for the check names it as "the check command (`$H/fresh-check`)", never as a literal `make check`: the crewmate runs the command `fresh-check` names, once, or, in a repo whose check selects its tests, the lint and the tests its change touches, and CI's check runs it whole.
   `jbus queue add` prints a line that begins ``warning: <slug>'s brief's Done when: asks for `make check` `` for a brief whose **Done when** asks for a bare `make check` while `fresh-check` names another check command, one that is no `make check-fast`, which the warning of the whole suite above covers: mend the line and add the brief again.

   Its `Size:` line is the task's t-shirt size, `S`, `M` or `L`, as its plan entry's `Size:` line has it: the feature playbook's step 4 reads it to decide on a design read.
   `jbus queue add` queues no brief with no such line, or with any other word on it.

   Its `Review:` line says how much review the pull request gets. It is fixed now, when the brief is written, and the crewmate and the reviewer both go by it:

   | Write | When |
   |---|---|
   | `Review: review` | always, unless one below holds or the user says otherwise: Josh, 2026-11-04 (bot-chat t147u), "We will first trigger deterministic validation that proves or fails the work before a reviewer does. The reviewer should not look for nits or warnings, only for blocking or severe work." One review round, launched once `check` has passed. A finding blocks only with a proof: a run that exits non-zero, a failed check, a doc line made wrong, an unmet `Done when` line, or a measure. The crewmate answers each finding, and its fix merges on its checks with no review. The one later pass judges again a `Meets the brief: no`, and its `error` findings alone are fixed in the pull request, its `warning` findings go to the day's warnings row (Josh, 2026-11-01: one follow-up row a day), and its `info` findings are dropped. `Review: twice`, the default from 2026-10-21, reads as `review` |
   | `Review: none` | the task is text only (wording, a note, a doc with nothing that runs) or throwaway (a spike nobody merges) |

   A brief with no line, or with any other word, an old `after` included, counts as `review`.
   `Review: cleanup` is the day's warnings row's alone, which jbus files: `jbus queue add` refuses it on a brief the home writes.
   With `none` the crewmate launches no reviewer, and `jmerge` holds the pull request for the user's word.
   No reviewer runs a test step or a suite: the desk's one run of the check is the crewmate's, and CI's check on the pull request is the check of record.

   A brief is checked when it is queued, not when it launches.
   `jbus queue add` refuses a brief that is short of anything a launch asks: a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, each filled in; a `Proves it:` line that names something outside the agent; a t-shirt size; a crewmate's playbook; a `Design:` line, written only where `/architect` wrote a design, that names that design; and a `Skills:` line that names at least one skill, whose every name is a skill of `skills/` or a principle of `principles/`.
   It prints `refused: <slug>'s brief has <n> faults, and nothing is queued` and one line under it for each fault: mend the brief and add it again.
   Nothing is queued, so the user is never asked to approve a brief that cannot launch.
   It also refuses a brief that asks for a load on every core (`stress-ng --cpu 0`, `--cpu $(nproc)`) instead of a bounded one inside `jgauge test-slot`, and one whose `Done when:` asks for a screenshot, a shot or a recording as proof.
   The lints run once, at `jbus queue add`: a launch lints nothing again, so a lint added after a row's approval does not refuse that row.
   A launch refuses only a brief its approval no longer covers.

   Its order behind other rows is one of two kinds, and one rule tells them apart from the plan alone: does this row's crew need another row's code in hand when it starts, code it changes, calls or imports?
   Where it does, the row is queued with `--depends <that row>`, and the brief has a `Builds on:` line that names that row before a colon and what of its work it starts from after it, as `$T/brief.md` shows.
   The row launches once that row has merged, or once it has opened its pull request: jbus then launches it stacked on that pull request's branch, writes its `Stacked on:` line, and moves it onto the default branch once that row merged.
   A stack is made by a `--depends` only: the home never writes a `Stacked on:` line, and `jbus queue add` refuses a brief whose `Stacked on:` line names a row its depends does not, and says to add the depends.
   A stacked row stays on its stack until that row merged.
   A row that builds on two rows whose pull requests are both open waits until one of them merged, since a stack sits on one branch.
   Every other order is only about merging, such as two rows that touch the same files or that must land in a set order: the row is queued with `--merge-after <that row>`, and has no `Builds on:` line.
   It launches at once, and `jmerge` holds its pull request until that row has merged.
   A brief stacks only on a parent whose code it changes, calls or imports: a stack holds a row behind its parent's whole review, so a stack with no code edge is a wait for nothing.
   A plan layer is no such need, and neither is docs order or a file two rows share.
   A Result is no such need either: the home queues the row once that Result is written, with the lines it rests on in its brief's `Rests on:`, and no `Builds on:` line for it.
   Sibling work of one plan layer queues unstacked, with no `Builds on:` line for the layer under it, and is chained with `--merge-after` only where the order of the merges matters.
   Two rows that share a file and are one change are one row, not a stack: a row that only finishes another's work (a `-rest`, a numbered part) goes in that row's brief, or the crew clears it in its own pull request.
   `jbus queue add` and `jbus queue check` print `warning: <slug> shares <paths> with <row>, which it builds on` for each `Where:` path the brief shares with a row its `Builds on:` line names.
   Where the two are one change, join the rows, and where the row has no need of the other's code, take the shared path out of one of them.
   Where it does need that code, leave it: the row is queued all the same and stays stacked.
   For a follow-up, a brief with a `Follows:` line or with `noticed in` on its `Task:` or `Decisions:` line, `jbus queue add` and `jbus queue check` also print `warning: <slug> may be the fault <row> (<status>, <pull request>) holds: both name <paths> and <tokens>: drop this row where <row> holds the fault` for each other live row whose brief shares a `Where:` path and a code token of its title and `Task:` with it.
   It is a warning, never a refusal or a hold: read that row's brief, and drop this row where that row already holds the fault, since a shared path and token are no proof of one fault.
   `jbus queue add` refuses a brief whose `Builds on:` line gives a plan layer as its reason, such as `launch-caps: its merged code, the base of layer 2`.
   `jbus queue add` refuses a `--depends` that the brief's `Builds on:` line does not name, and queues nothing: write the line, or make the order `--merge-after`.
   A `--merge-after` names a row that is already queued, so a chain is queued from its first link up.
   A wait goes on a `Builds on:` line or a `--depends`, never in prose: no code reads "brief once X lands" under a plan entry's `Decisions:`, so such a wait is forgotten.
   Queue the waiting row now with `--depends`, a scout's included, where its brief can be written now.
   Where it cannot, give the plan entry its own `Builds on:` line, in the brief's form, naming the rows or entries it starts from.
   Once every one of them has merged and the entry has no row, jbus wakes its home once with `brief <entry>: <them> merged`: brief it then.

   Its `Shown:` line names each picture the user sent with the request, so the crewmate sees what the user saw.
   Where a message the brief comes from had a picture, run `uv run --project "$T/../source" jbriefs --shown <this home's thread id> --since <a time just before that message>`: this home's thread id is `threadId` from the `t3-code` server's `t3_thread_configure` with no arguments.
   It prints one line for each message of that thread in which the user sent a picture: its time, its id, its first words, and each picture's path, or `gone` where the file is not on disk.
   Put each path it printed for the brief's messages on `Shown:`, with what the picture shows in a few words, and leave the line out where the user sent none.
   The paths are T3 Code's own files, which stay until the thread is deleted: never copy or move one.

   Its `Playbook:` and `Skills:` lines are picked together, by the kind of task, from this table.
   Every brief names a crewmate's playbook and at least one skill: `jbus queue add` refuses a brief with no line, or one that says `none`, and its fault names this table.

   | Kind of task | Playbook | Skills | Their tokens |
   |---|---|---|---|
   | A bug fix | `bug-fix` | `tdd` | 850 |
   | New or changed behaviour | `feature` | `tdd` at size S, `architect` at M or L | 850, 2,000 |
   | A change of shape that keeps behaviour | `refactoring` | `blast-radius` | 1,400 |
   | A `SKILL.md`, or a template a skill reads | `authoring-a-skill` | `technical-writing` | 2,400 |
   | Other docs | `autonomous-run` | `technical-writing` | 2,400 |
   | Tests only | `autonomous-run` | `principle-test-behavior-not-implementation` | 1,050 |
   | Too slow | `perf-issue` | `principle-explain-the-number` | 550 |
   | A number toward a target | `hillclimb` | `benchmark-checklist` | 1,800 |
   | An operation that changes no file | `operations` | `principle-make-operations-idempotent` | 540 |
   | A measurement with no fix and no target | `measurement` | `benchmark-checklist` | 1,800 |

   A skill's tokens are its file's bytes divided by 4: the crewmate loads each named file in full at its start, and its Result owes one artifact for each.
   Name what the playbook does not already cite, and no more.
   A playbook is 900 to 1,400 tokens and brings each principle a step of it cites (`feature` cites 11, `perf-issue` cites `benchmark-checklist`), so a `Skills:` line that repeats one adds its tokens and nothing else.
   A kind the table does not name takes the crewmate's playbook whose row in the block below fits it, and the skill of the table's nearest kind.
   Name more than the table gives only where the task needs it: a skill on top costs its tokens and an artifact.
   Write each name in its canonical form, pstack's, so it reads the same in Grok Bot and in T3: a skill as its directory, `architect`, and a principle as its file without `.md`, `principle-model-the-domain`.
   `features/jbriefs/docs/jbriefs.md` "Skills a brief names" says which aliases resolve.
   The crewmate loads each file in full at its start, and its Result owes one artifact for each, the one `templates/skill-artifacts.md` names: `jmerge` merges no pull request whose Result leaves one out.

   Its `Playbook:` line names the steps the crewmate works through: one file in `$T/../playbooks/`, without its `.md`.
   Run this with the block at the top.
   It prints a row for each playbook, its name and then who runs it and for what kind of task, and a last row for `none`, which only a scout's request may take:

   ```sh
   for f in "$T"/../playbooks/*.md; do
       if [ -f "$f" ]; then
           printf '%s | %s\n' "$(basename "$f" .md)" "$(sed -n 's/^Run by: //p' "$f" | head -n 1)"
       fi
   done
   echo "none | nothing above fits"
   ```

   Pick from what it prints, by who runs the row.
   A brief takes a row `a crewmate` runs, the one the table above gives for its kind of task, and never `none`.
   A scout's request takes a row `a scout` runs, or `none`.
   A row `the home` runs goes on no brief and no request: "A playbook of the home's own" opens it.
   jbus launches no brief whose line names a playbook that is no file there, such as `fix` or `feature.`: it is a gate that says why.
   A row that ends `in a brief with` some lines asks for those lines in the brief: write them.
   Do not read the playbook to pick it: its row is enough.

   Then ask for the deeper version of the task, not a bigger one (`$T/../principles/principle-depth-over-breadth.md`). Run this, for a brief or a scout's request alike, with the playbook you picked in place of the words in angle brackets. Put the kind of work there instead, `research`, `perf`, `analysis`, `outcome` or `other`, where you picked `none`, and where the playbook hides the kind: an outcome under `feature` or `autonomous-run` is `outcome`, and a bug whose cause is not proven is `analysis`, whatever the playbook:

   ```sh
   picked='<the playbook picked, or for none the kind of work>'
   case $picked in
   *'<'* | *'>'* | '') echo "not filled in: put the playbook or the kind of work in place of the placeholder" ;;
   investigation | trace-forensics | runtime-forensics | perf-issue | hillclimb | eval | research | perf | analysis | outcome)
       echo "deeper: answer these four for this task, in this repo, on this machine, and write each where it says"
       echo "1. What would a top professional in this field do here that is not asked? Name the field: the answer shapes 2, 3 and 4, and adds no line and no deliverable"
       echo "2. What is the rawest material they would start from, in place of what is already digested? A brief's Read: line, or each of a request's questions, where to start looking"
       echo "3. What specific methods and tools would they use, each with the command that runs it here? A brief's Instruments: line, for the crew"
       echo "4. What, other than the agent or the user's trust in it, would show the result is right? A brief's Proves it: line"
       ;;
   bug-fix) echo "skip: a bug fix with a known cause goes by the direct path; where the cause is not proven, run this again with analysis" ;;
   feature | autonomous-run) echo "skip: a $picked task that builds a named change goes by the direct path; where it is an outcome to reach, run this again with outcome" ;;
   *) echo "skip: $picked is not research, perf, analysis or outcome work: a mechanical fix, a docs change and a bug fix with a known cause go by the direct path" ;;
   esac
   ```

   On `deeper`, answer the four from `$H` and what the user said, as for the rest of the brief: an answer that needs the code or the docs is a question for the scout. A brief the step ran on has a `Read:` line with answer 2 and an `Instruments:` line with answer 3, though the home wrote it. A request has no brief to hold 3 and 4: where its "Deliver" list asks for the crewmate's brief, name them on that line, so the scout's brief carries them on `Instruments:` and `Proves it:`. Do not run `/sharpen`: it is the user's to type. On `skip`, write the brief as it is. Skip it too for a task whose "Done when" already names its data, its instruments and its outside judge.

2. Start the crewmate thread with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first). The brief must be on disk before this call.

   ```json
   {
     "title": "crew: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "<slug>", "startFromOrigin": true},
     "message": "/crew <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/../source" jroles crew` with the block at the top.
   When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names.
   When it prints nothing, the call is the one above.
   Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line.
   When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line.
   A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed.

   ```json
   {
     "title": "crew: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "<slug>", "startFromOrigin": true},
     "message": "/crew <slug>",
     "modelSelection": <model selection>
   }
   ```

   - The default branch is `git symbolic-ref --short refs/remotes/origin/HEAD` without the `origin/` prefix.
   - The title is `crew: ` and the slug, so the left bar shows which threads are crewmates.
   - Leave the project and modes out, and the model unless `jroles` printed one. What is left out, the crewmate inherits from this thread.
   - A launch has no retry key. If the call fails or its reply is lost, look for the thread with `t3_thread_list` before launching again:

     ```json
     {"titleContains": "crew: <slug>"}
     ```
   - If the session has no such tool, tell the user instead: "Open a new thread in this project, in a new worktree, and type `/crew <slug>`."
3. Add the line `Thread: <threadId>` to the brief. Run this with the block at the top, with `tasks` or, for a scout's request, `scouts` in place of `<tasks or scouts>`, and the id the launch returned in place of `<the launched thread>`:

   ```sh
   B="$H/<tasks or scouts>/<slug>.md"
   line='Thread: <the launched thread>'
   case $line in
   *'<'* | *'>'* | 'Thread: ') echo "not written: put the id the launch returned in place of the placeholder" ;;
   *)
       if [ ! -f "$B" ]; then
           echo "not written: there is no $B"
       elif command grep -qxF -e "$line" "$B"; then
           echo "not written: $B has $line"
       elif command grep -q '^Thread:' "$B"; then
           was=$(command grep -m 1 '^Thread:' "$B")
           awk -v line="$line" '/^Thread:/ && !put { print line; put = 1; next } { print }' "$B" > "$B.thread" && mv "$B.thread" "$B"
           echo "written: $line, in place of $was, in $B"
       else
           awk -v line="$line" '
               /^## / && !put { print line; put = 1 }
               { print }
               END { if (!put) print line }' "$B" > "$B.thread" && mv "$B.thread" "$B"
           echo "written: $line, in $B"
       fi ;;
   esac
   ```

   The line goes above the Result, when a fast crewmate has written one by then, and takes the place of the line of an earlier launch from the same brief: a review's findings go to the thread it names.
   Briefs and requests are in the repo's directory, whichever home launches from them.
   Write no status in the plan.
   A launch by this section adds no row to the queue, and `jbus plan` counts an entry from its rows, so where the brief has no row yet, add one for its entry.
   Run this in the main checkout with the block at the top and the block that finds this home, with the brief's slug, a priority and the entry's slug in place of the words in angle brackets, and with the row's order from step 1 added as `--merge-after <slugs>` or `--depends <slugs>`:

   ```sh
   : "${M:?run the block that finds this home first}"
   if command -v jbus > /dev/null && jbus plan > /dev/null 2>&1; then
       if said=$(jbus queue add '<slug>' --priority '<n>' --entry '<entry>' --from "$ME" < "$H/tasks/<slug>.md" 2>&1); then
           echo "added: the row <slug>, of the entry <entry>"
       else
           printf '%s\n' "$said"
       fi
   else
       echo "no row: jbus has no plan for this repo, so nothing is added to its queue"
   fi
   ```

   `jbus plan` answers only for the repo it is run in, and `jbus queue add` with no project takes the config's only project whatever the repo: so the row is added only where `jbus plan` answered, and on `no row` none is, since it would be another repo's row.
   On `refused:`, nothing is queued: mend the brief as the lines under it say, and run it again.
   A line `refused: <slug> is filed under no entry of the <home> home's plan` or `refused: --entry <entry> names no entry of the <home> home's plan` means the row has no open entry of the plan to count for and take its go from: give the entry that the brief's work serves, from the list the line prints, or write the entry first, one heading and its `Done when:` list, then run it again.
   A row with no approval is never launched again.
   Then give the user the link: `[<slug>](t3-thread://v1/<threadId>)`.
   `--from "$ME"` says which home adds the row, and jbus refuses a brief whose `Home:` line names another home, so two homes never brief one fix unseen: that home briefs it, or this home hands it over on purpose by adding `--for <that home>`, `uncategorized` or the scope's name.

No fixed count limits the threads out, crewmates and durable scouts together, and no file does: each crew has its own worktree and branch, and two pull requests that change the same file are settled at the merge, where the second to merge rebases. What holds a launch is the machine: it has to have room.

The machine is shared with the homes of other repos, so check it before every launch:

```sh
uv run --project "$T/../source" jgauge room || echo "wait: jgauge room did not run"
```

It prints `go`, or `wait: ` and the first reading that has no room.
There are four readings: the one-minute load against the core count, the available memory, the memory pressure, which is the share of the last minute that something on the machine stood waiting for memory, and the plan's limits, which is the share of the account's five-hour and weekly limit already used.
A reading of the machine it cannot take is a `wait` too.
The limits are the one reading that never stops a launch unread: they come from the file on the `LIMITS` line, which the user's status line script writes, and for a window that file does not give, `room` prints `go` and under it a `note: ` line saying that limit is not known.
A window past its reset counts as empty, and a `wait` on a limit says when the window resets.
The check is one file, `features/jgauge/src/jgauge/room.sh` in the repo this skill lives in, and `jgauge room` runs it: the pr-review skill's run block and `jbus` ask the same file, and no skill holds a copy.
The four thresholds are the first four lines of its `room`: change one there.
`PROC` points the readings at another directory and `LIMITS` at another file, for a test.
Run it with the block at the top, which sets `T`: `uv run --project` needs nothing on `PATH` but `uv`.
A check that did not run is a `wait` as well.

Launch on `go`.
On `wait`, do not launch: write it as a `waits:` line of the turn's end, the task and why ("How a turn ends"), and launch it when the user next asks or the check says `go`.
That holds whatever the user asks for in one message: every launch gets its own check, and the ones with no room wait their turn.

A review is a task like any other. Do not run several review subagents that each install and test their own checkout: that is the same load as that many crewmates, with nobody able to watch it. Each review runs in its own reviewer thread, as many at a time as the machine has room for (the pr-review skill's run block makes the same check before a run starts), and their heavy suites run under the machine-wide lock in the user's global instructions.
