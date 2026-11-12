# jmerge

`jmerge` merges each open pull request of your repo that is reviewed, fixed and green.
After a merge, it removes the crewmate's worktree and branches where it is safe to, as "What a merge does" says.
It applies fixed rules to the briefs and their Results, the review sections, the queue, and GitHub's report of each pull request's checks.
`jmerge` calls no AI model.
When a pull request lacks something, `jmerge` leaves it open and prints the reason it waits.
The rules are in `features/jmerge/src/jmerge/ready.py`.

## Merge what is ready

`jbus` runs `jmerge` on each of its passes, so while `jbus` runs you do not need to run `jmerge` yourself.
To run `jmerge` by hand, follow these steps.

1. Go to the main checkout of the repo.
2. Run `jmerge --check`.
   It prints a `ready` line for each pull request a run would merge, and the reason each other one waits.
3. Run `jmerge`.
4. For each `hold` line, decide whether to accept the pull request ("Accept a held pull request").
   A `wait` line needs nothing from you.
   A later run merges the pull request once the reason no longer applies.

## Name the checks a merge waits for

When the repo has no `required-checks` file, a pull request merges once the check named `check` passes at its head.
To make merges wait for other checks, follow these steps.

1. Open the repo's state directory, `~/.local/state/home/<repo>/`.
2. Write the names of the checks in a file named `required-checks`, one name to a line.
3. Run `jmerge --check` and read the `wait` lines.

For example, the `required-checks` file of jstack's own repo names `check` (its test suite) and `borders` (its border lint), so its pull requests wait for both.
Its macOS job, `macos`, runs on each push to main and on no pull request, so it is no required check: a Mac red is caught after the merge, and jbus reverts its culprit (2026-11-09).
If the file names a check that your repo's CI never runs, every pull request waits.

## Accept a pull request it holds

Run `jmerge --accept <number> --as user --message <thread id>/<message id>` from the main checkout, naming your own message in T3 Code.
The section "Accept a held pull request" lists what `jmerge` checks before it merges.
It is the one way an agent merges on your word: in a repo jbus's config names, the `merge-command` hook refuses an agent's own `gh pr merge` and prints this line in its place ([Hooks](../../home/docs/hooks.md#the-merge-hook)).

## What a merge does

For each ready pull request, `jmerge` runs `gh pr merge <number> --squash --match-head-commit <head>`, then `git fetch origin <default branch>` and `git merge --ff-only origin/<default branch>` in the main checkout.
It pulls by ref and never reads FETCH_HEAD, so another fetch in that checkout cannot break the pull.
`jmerge` writes the squash commit's message itself.
The subject is the pull request's title and ` (#<number>)`.
The body lists the branch's commit messages as GitHub's default does.
`jmerge` removes every AI co-author trailer line from each message (`jmerge.trailers`).
When the crewmate's worktree is clean and its branch is at the merged head, `jmerge` removes the worktree, the local branch and the remote branch.
It writes no plan, because `jbus plan` works out an entry's status from its queue rows.
It needs `gh` and `git`.

It prints one line per open pull request, and appends the lines to `merge.log`.
It takes each revert jbus opened for a red main first ([A red main](../../jbus/docs/jbus/a-red-main.md)).
It takes the rest lowest number first, the oldest first, so an older pull request is not passed over by newer ones that became ready with it.
The migration order ("Migrations") and `merge_after` still come before the number.
When a `wait` or `hold` line repeats from run to run, it logs the line only once.

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", ..., revert: gh pr revert <url>` | Merged. The notes between say what was kept, or that a review carried over (`review carried over: range-diff ... clean`). The last note is the command that opens a pull request reverting the merge. |
| `wait <number> <url>: <reason>` | Not merged. The reason is the first thing the pull request is short of. A later run merges it once the reason is gone. |
| `hold <number> <url>: <why>` | Not merged, and never by a plain `jmerge`. It is yours to accept. Every reason jbus shows as Needs you is a `hold`, but three your other words lift: `jbus queue approve` the queue's two, and `/nohome merge on` the merge that is off (`jmerge.judgement`). |
| `ready <number> <head> <branch> <slug>` | With `--check`: what a run would merge. |
| `listed: GitHub gave 100 open pull requests, the most jmerge asks for, ...` | `jmerge` asks `gh pr list` for at most 100 open pull requests, the cap jbus's own lists use, and this many came back, so there may be more. It judges the 100 it was given, and keeps the holds, base merges and wait records of every pull request, since one past the 100 is still open. |
| `wait: could not ask GitHub: gh exited <code>: <what gh said>` | GitHub did not give the open pull requests or the default branch. The line ends on `gh`'s exit code and the first line of its stderr (`it said nothing` where it had none). A `gh` that exited 0 with output that is not JSON says `gh exited 0: its output was not JSON`, and one that named no default branch says `gh exited 0: it named no default branch`. A token and the query of a URL are cut from the text, and it is at most 160 characters. The same text ends the sweep's `could not ask GitHub about its pull request` and the `could not ask GitHub whether a pull request is based on it` that keeps a branch. |

In `merge.log`, a `wait` or `hold` line ends with its reason's code in brackets, as `wait 7 <url>: check has failed [check-failed]`, and the line it prints has none.
The code is fixed for a reason whatever its text says: a `Reason` in `features/jmerge/src/jmerge/ready.py` has its constant's name in lower case, its words joined by `-` (`CHECK_FAILED` is `check-failed`), and a reason given as plain text has the code of its rule in `ready.rules`.
`check has failed` (`check-failed`) is a check every latest run of which failed, `check has not passed` (`not-passed`) one that is queued, running or cancelled, and a reason no rule names is `unknown`.
jbus and the view read a pull request's step from the code, and from the text on a line logged before the codes and on a line as `jmerge` prints it, which `ready.code_of` gives the same code.

For each pull request it merges, `jmerge` also appends one line to `merge-waits.jsonl` beside `merge.log`, which `jbus telemetry` reads (`features/jmerge/src/jmerge/waits.py`).
The line holds the second the pull request was ready, the second its merge began, the seconds between, and the seconds each reason's code held it.
A pull request is ready once every required check has passed at its head and it is no draft, and its wait starts then, not when it opened.
A push, a check run again or a turn back to a draft starts its wait over.
From one run that sees it wait to the next, the wait is the code of the reason the first run gave, so a reason that clears and comes back adds only the seconds it held.
`merge-waits.json` keeps the waits of the open pull requests between runs, and `--check` writes neither file.

A pull request that waits does not make `jmerge` exit non-zero.
`jmerge` exits non-zero when it runs outside a git repository, when `gh` is missing, when it could not ask GitHub, when it refuses an `--accept`, or when it cannot read the protected list or a pattern in it.
With `--if-free` it exits 75 while another run holds the run lock (`lock.BUSY`).
jbus's pass and its merge tick both run `jmerge --if-free` (`features/jbus/src/jbus/merge.py`), so neither waits on the other's run inside its own 17 min timeout (`JMERGE_TIMEOUT`).
A run that exits 75 did nothing, and jbus counts no failure for it: the next pass or tick runs `jmerge` again.
A run that held the lock past that timeout and was stopped counts one failure of the `jmerge` streak, whether the pass or the tick started it, and three in a row raise the alert.

## What ready means

Each item below is a reason a pull request waits.
`jmerge` prints one reason for each pull request, the first one in the order that `Repo.judge` in `features/jmerge/src/jmerge/cli.py` sets.
The section "Protected paths" describes one more hold.

- **A draft waits.**
  `jmerge` never merges a draft and never marks one ready, whatever flags you pass.
  A crew opens its pull request ready, so a draft is one someone opened by hand.
  CI checks a draft on each push as it checks any open pull request, so a draft is judged as any other, and waits on the first reason that holds: its review, its fix, its queue row, its checks, a drop or a hold.
  Once none holds, it prints `wait <number> <url>: a draft, which jmerge never marks ready` (`HAND_DRAFT`), and it merges once someone marks it ready by hand.
  A draft that no brief names prints the same.
- **A brief names it.**
  A brief's Result has the pull request on its `Branch:` line.
  jbus is the only merger: it runs `jmerge` for every home of the repo, whatever `home-thread` holds, and a scoped home's pull request merges as the root home's does.
  A home's own run, with `--home`, merges nothing, and a brief of another home of the repo is `another home's` to it alone.
- **Its base is the default branch, or a merge base its project names.**
  A project of jbus's names merge bases besides the default branch with `jbus project bases <project> --add <branch>`, and `jbus project bases <project>` prints them: jstack names `t3code-jstack`, the branch the sidebar's pull requests go on.
  `jmerge` merges a pull request into a named base on the rules of one into the default branch: its review written and answered, its required checks green, and not a draft.
  Main's red holds no pull request, into a named base or into main.
  `jmerge` never merges a pull request based on a branch that is neither (`its base is <base>, not <default>`), nor one into a named base where jbus's config does not load.
  The sweep keeps a brief's branch that is a merge base (`it is a merge base of the project`).
  A link jbus stacked, whose brief has a `Stacked on:` line, is not held for its base: it waits as `it is stacked on <branch>, and merges after <slug> merged and jbus moved it onto <default>` while its line names its base's branch, whatever base GitHub gives it.
  That wait is on a step of its own, `stacked`, not on `check`: what moves it is the row it is stacked on, not a check runner.
  Once jbus wrote the commit its base merged as, it waits as `<slug> merged as <sha>, which its head does not hold: it merges after its crew rebased it onto <default>` until its head holds that commit.
  CI checks a link on its base's branch while the base is open, beside its base's own check, as it checks any open pull request, and the link waits on its stack as above.
  Its check at the moved head then adds no round of the suite in series where the move is a clean replay: the check's `reuse` job finds that a passed run already checked the same two trees, the base's and GitHub's merge of the head over it, and `check` passes on that run in the time the lookup takes (`jmerge.reuse`).
  Where the move checks other trees (its base took commits after the link's check, main moved before its base merged, or the replay changed its patch), the suite runs, and the link waits on its check as any pull request does.
  The repo's ruleset requires `check` at the head itself, so `jmerge` counts no other head's run: the reuse is CI's own run at the moved head.
- **The review is done.**
  The brief has a `## Review` section with a verdict.
  The review comes before the pull request: jbus launches it once the brief's `Checked:` and `Proved:` lines bind the head the crew pushed, and adds its `Reviewer:` lines under the Result the crew wrote then, with `Pull request: after the review` (`jbus.prereview`).
  The crew opens the pull request after the review and names it in a follow-up Result, so `jmerge` merges on the required checks plus the review at the head, and waits for each reviewer those lines name.
  If the review had findings, the Result has a `Fixed:` line that names the head or says `none needed`.
  The crewmate writes that line, and the crew's check block writes the `Checked: <command> exit <code> at <head>` line each time the check command ends on a committed head.
  Where the crewmate wrote no `Fixed:` line, `jmerge` reads one from the brief and git (`ready.unwritten_fixed`): `jbriefs --findings --left` says `write Fixed:`, a `Checked:` line says exit 0 at the head, and in `review` mode a `Second pass:` or `Scoped review:` line follows the review.
  That line names the head, or the newest head kept under `refs/jstack/pre-rebase/<slug>/` that holds the fix, or says `none needed` where every finding was declined.
  `jmerge` judges the brief with it and writes nothing to the brief.
  A review after the first owes that line, and a push after it, only where it has an `error` finding.
  One round: a fix pushed for the findings gets no review, and a `Second pass:` line, from a brief before one round, makes the pull request wait for nothing.
  A `Scoped review: needed since <head>` line, which the crew writes only after a `Meets the brief: no`, makes it wait for a review of a later head (`fix`, `its fix is not reviewed`) only while no `Proved:` line of the Result holds at the head (`ready.proves`, as "Its Result proves the work" reads the line).
  A fix whose proof runs there merges on that run and its checks: a `no` still waits on the `Meets the brief:` rule below, whose way out is the scoped review that says `yes`.
- **Every blocking finding is answered.**
  Each blocking finding needs an answer that counts, for every pull request.
  `jbriefs --findings` reads every `## Review` section into one list.
  Its parser, `features/jbriefs/src/jbriefs/findings.py`, is the one the crew skill and jbus use too.
  Each finding gets an id, `F1`, `F2`, ..., in the order it appears.
  Two reviewers' findings share one id when they are at the same head, in the same file within 5 lines (`NEAR`), and cite the same principle.
  In a first review, three kinds of finding block: an `(bucket: Act on)` finding, a finding written before the buckets existed, and a finding tagged `(risk: <area>)` in the Act on or Consider bucket.
  A `Consider` finding there does not block, and a finding's severity does not change whether it blocks.
  In a review after the first, a scoped pass, the severity the review wrote alone decides, whatever the bucket or tag (`findings._LATER`).
  An `error` blocks until the crew answers it, and an `info` is dropped.
  A `warning` blocks nothing and goes to no crew: once the pull request merged, jbus keeps it for the day's warnings row (`findings.KEPT`, `jbus.daywarnings`).
  So a scoped review with no `error` owes no fix push and merges on its checks.
  A blocking finding carries its evidence in a `(proof: ...)` tag of one of the shapes `proofs.PROOFS` reads: a command in backticks that exited non-zero at the head, a check that failed, a doc line the pull request made wrong, an unmet `Done when` line, or a measure of the base and the head.
  One with no such tag waits as `its findings are not handled: F2 block with no proof tag, ...` until it has an answer by id, and a decline of it counts with any reason, a risky one still only on its gate.
  An answer is `Finding F<n>: fixed, ...` or `Finding F<n>: not fixed, ..., because <reason>`.
  A decline counts only if its reason cites a `path:line`, a command in backticks, or a gate the Result names (`Gate: question <n>`).
  It also counts only if no other finding was declined for the same reason.
  A finding tagged `(risk: <area>)` covers security, auth, billing, data, migrations or concurrency.
  A decline of such a finding counts only if it cites a gate.
  The crew parks that gate with the default "fix it".
  The pull request waits with one of these: `its findings are not handled: F1, F3 have no answer by id`, `... the decline of F2 cites no path:line, command or gate`, `... the decline of F2 gives the reason of F1`, `... F1 on auth declined with no gate question`.
  `jmerge` matches `Finding: fixed, ...` lines that have no id to the findings by count, in order.
  A brief whose answers have no id waits with `its findings are not handled: <k> of <n> have no Finding line`.
  A decline that says `because .` is not an answer.
  jbus's `expedite` tells the crew about each of these waits, with the ids.
- A brief that says `Review: none` is held with `its brief says Review: none, so it needs the user's word`, which `--accept` lifts.
  It has no review, so `--accept` asks it for no proven safety fact and no range-diff from a reviewed head: your word stands in for both.
  Every other rule still holds: green checks, a protected path's door, and `merge-off`.
- A brief that says `Review: cleanup` is the day's warnings row, which only jbus files (`jbus.daywarnings`), and it gets one review, of its own diff.
  Only an `error` of that review waits, for an answer by id and a `Fixed:` line pushed after it, and every other finding is dropped.
  `jmerge` asks for no scoped review, no ruling on a decline, and no range-diff review after a rebase.
- A brief whose `Review:` line says anything else, `after` and `twice` included, is read as `review`.
- **The last review round says the brief is met.**
  The reviewer's judgement of the brief is a typed line of each `## Review` section, `Meets the brief: yes, <n> of <n>` or `no, <m> of <n>`, with an item under it for each `Done when` line it does not take as met (`features/pr-review/templates/review.md`).
  `<n>` is the count of the brief's `Done when` lines, and an `after-merge <k>` or `waiting <k>` item, a line only provable once merged or only waiting on CI, is not unmet.
  `features/jbriefs/src/jbriefs/meets.py` is its one parser and the one rule, and `jbriefs --meets <brief>` prints what it reads.
  The last round counts: of the sections that ran, those at the head and of the kind, scoped or not, of the last one, each reviewer's last.
  So a later round, the scoped review a `no` owes, takes the place of an earlier `no`, and a stale first-round `no` holds nothing.
  The pull request waits with `its review at <head12> says the brief is not met, <m> of <n>: Done when <k> unmet, ...` (`meets-no`) while that round says `no`.
  It waits with `its review at <head12> has no Meets the brief line of the shape ...` (`meets-unread`) where a section of the round has no line of that shape, today's free text `yes` included, and with `its review at <head12> counts <said> Done when lines, and its brief has <n>` (`meets-miscounted`) where its count is not the brief's: a skipped or skimmed check is no pass.
  The way out is a fix and a scoped review whose own line says `yes`: the crew skill's "A second pass" gives that review for any round whose line is not `yes`, whatever the fix changed.
  The only other way out is a line `Waived: <the Done when line>, <thread>/<message>` in the brief, which names the line by its words, whole or by a start no other line has.
  `jmerge` asks jbus of each such word once a run (`jmerge.bus.Bus.heard`, `jbus.port.Port.heard`): the user's own message in T3 Code, read by the check `jbus queue approve --message` reads a word with, or a word the bot gave over `POST /act`, and its words name the row's slug, say they waive, and quote the words the `Waived:` line names the line by (`jbriefs.meets.quotes`).
  A waive act bound by `jbus waive <slug> <line number>... --message <thread>/<message>` (`jbus.waive`) also counts, for the lines it names: the user's plain reply ("yes, clear them") in a home's own thread to the home's last message before it, which named the slug and those lines by number.
  `jbus waive` checks that when the home records it, logs the act and writes the `Waived:` lines, and `Port.heard` takes a `Waived:` line whose message and slug such an act holds, with no quote needed.
  A crew's or a home's own message, a word of the bot's that a home typed, and the user's word about the row that waives nothing, its go included, waive nothing, and a word waives only the line it quotes or a waive act names.
  The rule does not apply to a brief that says `Review: none`, to one with no review that ran, or to one with no `Done when` list.
  `jmerge` judges it after every other wait of the review, so a pull request short of a `Fixed:` line or a scoped review says that first.
- **Its Result proves the work.**
  The pull request waits on the `result` step while one of three lines of its brief's Result is short (`ready.short_of`, `ready.short_on_proved`, `ready.short_on_checked`).
  `Skills run:` has an artifact for each skill the brief's `Skills:` line names (`skills-unrun`).
  A pull request that changes tests has a `Proved:` line that names each of them, with their run ending 1 at its base and 0 at its head.
  Its tests are each `test_*.py` and `*_test.py`, and each `*.test.*` and `*.spec.*` of JavaScript or TypeScript, it adds or changes (`ready.changed_tests`), so a Node repo's pull request is held to the same proof as a Python one's.
  A run that does not fail at the base holds it, since such tests prove nothing of the change, unless the pull request changes no code (`ready.changed_code`): its tests then run over the same code at its base as at its head, a pass at the base is what they should do, and the run at the head is the whole proof.
  That ends the hold by rule, with no word of the user's: a pull request of tests, docs and config, of a `.py` file whose change is to its docstrings alone, or of a fork's tests alone, as #1535 was, a patch that adds a test of what the fork already does.
  A fork's change is of its tests alone where each patch it adds or edits touches only the fork's test files and `.md` files at both sides, and its `PKGBUILD` changes only in its series, its checksums, `pkgver` and `pkgrel`, the series losing or gaining only such patches (`jmerge.forktests`).
  A `Proved:` wait its crew could not clear after jbus told it twice becomes the user's, for `jmerge --accept` ([A wait only its crew clears](../../jbus/docs/jbus/what-waits-on-you.md#a-wait-only-its-crew-clears)).
  One that changes only test files, and files of a kind `jbriefs.proved.EXEMPT` names (docs, config), needs only the run at its head, its `tests only` line: a removal of tests with the edit to the doc that named them is one.
  A `tests only` line on one that changes any other file holds it, and one that changes no test needs no line.
  One that adds or changes a fork's patch (a `.patch` under a feature's `packaging/` folder, `jbriefs.proved.FORK_FILE`) needs a line all the same, since its tests are inside the patch, and one that only edits the `PKGBUILD` or deletes a patch needs none: where every file it changes is a fork file, docs or config, its `fork patches` line names the fork's test files, with their run ending 1 over the base's series and 0 over the head's, and the same line on one that changes any other file holds it (`jbriefs.proved.outside_fork`).
  The last `Checked:` line names the desk's whole check, `make check-fast BASE=<sha> PART=touched` (the lint, the touched tests, the cross-cutting tests and the tests that read the change), `make check-fast BASE=<sha> PART=guards` (the desk's check before 2026-11-05) or `jgauge check`, ending 0 at the head, or at a head whose patch the head carries unchanged.
  An exit of 124 is a time limit, and holds the pull request like any other exit but 0.
  On the two-step line the crew's check block once wrote, only the guards' step counts.
  Each line it waits with is a `Reason` in `features/jmerge/src/jmerge/ready.py`, from `SKILLS_UNRUN` to `CHECKED_PART`.
- **The required checks passed, and GitHub reports that the pull request can merge.**
  Green means that the latest run of each required check at the head passed, whatever the other checks say.
  A required check whose job its own workflow skipped by an `if:` counts as passed when every other job of that workflow at the head passed or was skipped, and one passed (`ready.passed`).
  Any other skip is no pass.
  A repo names its required checks in a `required-checks` file in its state directory.
  The file has one check name per line, and `jmerge` ignores blank lines and the spaces around a name.
  With no such file, or one that names no check, the only required check is `check` (`ready.REQUIRED`).
  A check that the repo's workflows never run then blocks no merge.
  A pull request waits with `<check> has failed` for the first required check that has not passed where its latest run failed, with `<check> has not passed` where it has not, and with `it conflicts with its base` for a conflict.
  Where GitHub lists no run of that check at the head, the line is `<check> has no run at <head12>` instead: no runner is at work on it, as for a workflow that reached the base after the head's checks ran.
  GitHub runs no check on a pull request that conflicts with its base, so where it says `CONFLICTING` and the check has no run at the head, the line is `it conflicts with its base`: the conflict is what keeps the check from running, and the crew's rebase is what starts it.
  Where GitHub has not yet decided whether the pull request merges, `GitHub has not decided whether it merges` (`undecided`) is said last, after every reason that does not wait on GitHub: a review, a rebase that changed the content or dropped a line, a go, a scoped ruling, a queue row, a hold and a draft each say their own line first, since GitHub's answer would not change them (`Repo.judged`).
  GitHub decides afresh each time main moves, and #1440 went `dropped`, `undecided`, `dropped` while its rebase's drop stood.
  A held queue row, or one that merges after a row not merged yet, comes before `<check> has failed`, `<check> has not passed` and a running check, and a check with no run at the head comes before it ("Its queue row lets it merge").
- **Its queue row lets it merge.**
  Once each run, `jmerge` reads the `queue.json` of the jbus project that the current checkout belongs to (`features/jmerge/src/jmerge/rows.py`).
  It looks up the row whose slug is the brief's slug.
  Whether a row is over, `merged` or `done`, jmerge asks jbus (`jmerge.bus.over`, which `jbus.work.over` answers), and a row once over stays so.
  A pull request whose row is over is held as `its queue row is <status>, and a row that is over waits for no merge: accept it to merge it` (`row-over`): it opened after the row ended, jbus asks the user about it, and `--accept` lifts the hold.
  It lifts that hold alone: the row's go, its hold, and the rows it merges after or its head carries still hold the pull request (`Repo.queue_of`).
  When `jbus queue hold` has withdrawn a row's approval, the pull request waits as `its queue row is held: approve it again to let it merge`.
  A hold stops a merge as it stops a launch, and `--accept` does not lift it.
  A row with no go waits as `its queue row has no go: the user's go (jbus plan go <entry> --message <thread>/<message>), or the bot's, lets it merge`, and a go given with `jbus plan go` or `jbus queue approve`, or the bot's over `POST /act`, lets it merge.
  When a row names other rows in `merge_after`, its pull request waits as `merges after <slug> (#<n>), not merged yet` for the first of them that is not `merged` or `done`.
  `jmerge` judges it again on the run after the one in which that other pull request merges.
  A pull request built on another open pull request's branch carries that one's commits, and a merge of it lands them too.
  So when its head contains the head of another open pull request, and its base does not, it waits on that one's `merge_after` as on its own: `carries <slug>'s commits (#<n>), which merges after <slug> (#<n>), not merged yet`.
  That holds while the carried row is not `merged` or `done`, and also for a pull request whose brief has no queue row.
  When either head cannot be read, even from `refs/pull/<n>/head`, it waits as `its head or <slug>'s (#<n>) cannot be read to see whether it carries it`.
  When the queue exists but cannot be read, every pull request waits with `its queue cannot be read, so its holds and merge order are not known`.
  A repo with no jbus config, or that no project names, has no queue and no such wait.
  `jmerge` judges these after the review and rebase gates, so it reports a missing review or rebase line first.
  A held row and a `merges after` wait come before GitHub's waits too: a pull request whose row says either waits on it whatever GitHub says of its mergeability or its check, in place of `<check> has failed`, `<check> has not passed` and `<check>'s run at <head12> is <state>` (`Repo.row_first`).
  GitHub's state comes and goes each time main moves, and the row's wait stands until the row changes, so the pull request keeps one `wait` line for as long as its row holds it.
  A check with no run at the head, and a conflict while no required check waits, keep their place before the queue's waits: they are the crew's to act on.
  GitHub names a waiting check before a conflict, so a held row on a pull request that conflicts and has a failed check reads `row-held`, as it read `<check> has failed` before.
  It judges them before today's main, so a run never asks GitHub to update a pull request that must wait.
- **Main is not red: a red main holds no pull request.**
  jbus records main's red tip as `broken` in `main.json` beside the queue, and that file is the one record of it (`features/jbus/docs/jbus.md`).
  No pull request waits on it.
  A launch does: while main is red, jbus launches only a row that fixes main or launches stacked on an open row it depends on, and every other approved row waits as `main is red: waits for green` (`jbus.dispatch`, [What a pass launches](../../jbus/docs/jbus/what-a-pass-launches.md)).
  A pull request red at its own head is still held by its own checks, as `check has failed`.
  While `main.json` names a red tip, `jmerge` asks GitHub for no merge of main into such a pull request: its head would go red again, so the check stands until main's tip is green.
  jbus reverts the one clear culprit of a red main and files a fix row otherwise ([A red main](../../jbus/docs/jbus/a-red-main.md)).
  A revert jbus opened needs no review: `reverts.json` beside the queue names its pull request (`jmerge.reverts`), and it merges by the normal path once its checks are green, at the head jbus opened it at or one whose range-diff from that head is clean.
  A repo with no jbus config, no project or no `main.json` has no such record, and its red pull requests are judged as any other.
  If `jmerge` cannot read the file, nothing is known of main, and no pull request waits on a red main.
  jbus checks every commit that was main's tip since jbus's last pass.
  So jbus counts a failed tip as red even while the check of a newer tip is still running.
  A tip's check is its push run's: the check runs of the workflow runs a push to main started (`jbus.watch._check`).
  A run dispatched by hand, on a schedule or for a tag at the same commit, of browser.yml or any other workflow, does not make main red: browser.yml's red takes the path of "Its own browser run did not fail".
  A later green tip ends the red state.
- **Its own browser run did not fail.**
  browser.yml runs on a pull request that changes the view, and is no required check, so a head with no run of it waits for none.
  A run still going at the head waits as any pending run does: `browser has not passed`.
  A run that ended and failed holds the pull request as `its browser run failed at <head12>`, and jbus tells its crew to fix it (`features/jbus/src/jbus/expedite.py`, `TABLE`).
  When main's last browser run on main failed too, the red is main's, and the pull request waits as `its browser run failed at <head12>, as main's did at <sha12>`, the sha12 being that run's commit, and jbus tells no crew to fix it.
  It is main's only while the row jbus filed for the fix of that run is open, since browser.yml runs on main only nightly and its last run there stays red until the next one.
  Once that fix merged, or where jbus filed no fix for the run, the red is the pull request's, and its crew is told.
  The fix of that red is held by its own red as any other pull request is: the row jbus files as `browser-red-<date>`, or a pull request whose browser run, at a head that contains the commit of main's red run, passed each test main's run failed.
  `jmerge` reads those tests from the logs of main's red run's jobs, and what the pull request's run ran and failed from its own log.
  A job's log says what it ran by its one pytest command: the test files and folders it names, or with none the whole suite.
  A log with no such command, or more than one, says nothing, and so does one with an option not known to leave the run whole.
  The known ones set workers, timings, reports, output and the shard (`jmerge.rows.KEEPS`).
  The marker must be the one its reader expects: `browser` in the browser run (`jmerge.rows.BROWSER`).
  Any other option may leave tests out or stop the run, by name, by path, by marker or by collecting only, so it proves nothing.
  A test the fix deleted or skipped counts as passed, as it does for main's own check.
  `jmerge` asks GitHub for main's browser runs only for a pull request whose browser run failed, once a run, and where GitHub gives no answer the red is the pull request's.
  A draft's browser run holds it as any pull request's does.
  `jmerge` judges this after the queue row, so a pull request short of a review, a rebase line or its queue row's go says that first.
- **Its migration is the next in line.** See "Migrations".
- **Its check ran over today's main.**
  See "Merges cleanly over today's main".
- **Its rebase kept every line.** See "After a rebase".
- **The tests it adds or tightens pass on every open pull request merged with it.**
  #1702 merged at 01:16Z on 2026-11-12 with a new rule, and within the half hour #1711, #1712, #1713 and #1716 went red on it, each crew left to find the red alone.
  So once a pull request has no other reason to wait, and its change adds or edits a test file (`test_*.py`, the repo's guard tests among them), `jmerge` runs those tests on the tree of its head merged with the head of each other open pull request a brief names (`features/jmerge/src/jmerge/preflight.py`).
  The command is the first line of the state's `rule-preflight` file that is not blank, with `RULES` set to the test files: jstack's is `make test TESTS="$RULES"`.
  A repo with no such file runs no preflight.
  The tests run first on its head alone: where they fail there, this machine does not run them as CI did, and nothing is held.
  A pull request that fails them merged with it holds it with `its tests <tests> fail on open pull requests merged with it, #<n> (<test>), ...: carry the fix (an exemption or a changed rule), or name each on a Breaks: line of its Result, and jbus tells their crews when it merges` (`rule-breaks`, on the `result` step), and jbus tells its crew so on the first pass.
  The hold lifts in one of two ways.
  Its crew pushes the fix, a changed rule or an exemption, and the tests pass on every open pull request merged with the new head.
  Or its crew adds a line `Breaks: #<n> #<n> ...` to its Result that names each failing pull request: it then merges with the note `its tests <tests> fail on #<n> ... merged with it, whose crews jbus tells`, and jbus tells each named pull request's crew in the pass that reads that `merged` line (`jbus.rulebreaks`).
  A pull request that fails starts holding it again until it is named, as does a new one that opens and fails.
  A failure holds nothing where the other pull request fails the tests it has at its own head too (that red is its own, and its check shows its crew), nor does a tree that conflicts, cannot be built or runs past 60 s: that crew rebases once the rule lands, and the guards on the merged tree stand behind it.
  A pull request stacked on it, or one it carries, runs nothing: its own check runs the rule.
  `rule-trees.json` keeps each result until either head moves, but a run stopped at its limit or one whose tree or slot would not start runs again on the next run with time left, and a result at another pull request's older head counts until its new head is run, so a crew's push holds no rule.
  The runs of one `jmerge` run spend at most 90 s, apart from the guards' time, each inside a full test slot; while a pull request has not been run once, the rule waits with `its tests <tests> have run on <k> of the <n> open pull requests merged with it: the next run goes on` (`rule-unrun`), which ends by itself.
  `--check` runs the preflight too, in a worktree of its own, so its `wait` line names the pull requests a rule breaks.
- **The repo's merge is on.**
  While `~/.local/state/home/<repo>/merge-off` exists, `jmerge` merges nothing.
  A pull request that would have merged waits with `auto-merge is off for this repo`.
  `/nohome merge` makes the file and `/nohome merge on` removes it.

Before a merge, when the start of the pull request's check is known, `jmerge` runs `git ls-remote` to see whether main is still the commit it judged against.
If main moved, `jmerge` judges the pull request again, at most twice, before it prints `main moved while it was judged`.
A main that moved after the pull request's check started has it wait for a check over the new tip, as "Merges cleanly over today's main" says.

## Migrations

A numbered migration gets its number when its branch is created, and that number must still be free when the branch merges.
So two pull requests that were ready together take the same next number.
The one that merges second breaks main, or someone must renumber its migration by hand.
When a repo sets `migrations = "db/migrations"` in its project table in `~/.config/jbus/config.toml` ([Configuration](../../jinstall/docs/configuration.md#jbus)), `jmerge` checks the number at merge time.
A pull request adds a migration when GitHub lists a file that the pull request adds directly in that directory.
`0005_insulin.up.sql` and `0005_insulin.down.sql` are one migration, `0005_insulin`.
These rules make no pull request wait in a repo with no `migrations` key, and none that adds no migration.

- **They merge in the repo's declared order.**
  `jmerge` judges the migration pull requests in the order that `merge_after` sets in the queue.
  A row comes after every row it names, and the order also follows `merge_after` through rows that have no migration.
  Where the queue declares no order, the older pull request comes first.
  `jmerge --check` shows them in that order, with one `ready` and the others waiting.
- **One merges in a run.**
  `jmerge` merges the first migration pull request that has no other reason to wait.
  A second one that is ready waits as `it adds a migration, and #<n>, which merges before it, is merging`, because the merge changes the numbers that `jmerge` judges the others by.
  `jmerge` judges it again on the next run.
  A pull request that adds no migration does not wait for this reason.
- **One that is being rebased makes those behind it wait.**
  A migration pull request may wait because it conflicts with its base or with today's main, or because its number is taken.
  Such a pull request makes a ready one behind it in the order wait: `it adds a migration, and #<n>, which merges before it, is being rebased`.
  A pull request that waits on anything else (a draft, no brief, another home's, a review) makes none behind it wait, since jbus tells nobody to rebase it.
  A pull request behind another in the order never makes the one ahead of it wait.
- **The crew renumbers a taken number.**
  After a fetch, `jmerge` reads the numbers in the default branch's migration directory.
  A migration whose number main already has waits as `its migration <name> takes number <n>, which main has: renumber it to <free>`, where `<free>` is one more than the highest number main has, with as many digits as the migration has.
  On the third pass that gives the same reason, `jbus` tells the crew what to do (`renumber` in `features/jbus/src/jbus/expedite.py`).
  The crew rebases by running the crew skill's "A conflict" block with `stale`.
  It renumbers the migration that the reason names to the number the reason gives.
  It renumbers each later migration of the pull request to the numbers that follow, one each and in their order.
  It changes the files and every reference to an old number, then pushes.
  `jmerge` judges the renumbered head again, and the content change needs the scoped review that "After a rebase" describes.
- **A repo can name its migrations by timestamp instead.**
  With `migration_names = "timestamped"` the names cannot collide, and `jmerge` skips the number check.
  The pull requests still merge one at a time, in the same order.

Each reason is a constant of `features/jmerge/src/jmerge/ready.py` (`MIGRATION_TAKEN`, `MIGRATION_MERGING`, `MIGRATION_REBASING`) with a rule in `rules()` of `features/jbus/src/jbus/merge.py`.
The rule for a taken number is on the `rebase` step, and the rules for the two waits on another pull request are on the `check` step.

## Merges cleanly over today's main

A check starts when the earliest run of the first required check at the head starts.
When the repo names no required checks, that check is `check`.
After a `git fetch` in the main checkout, `jmerge` lists the paths that the first-parent commits of the default branch changed since that start.
When there are none, the check ran over today's main, and it counts.
When there are any, `jmerge` merges the head over today's main with `git merge-tree`.
A head that does not merge over today's main waits with `it conflicts with today's main`, on the `rebase` step, and GitHub is asked nothing.

A head that merges cleanly then goes one of three ways, by its files, the repo's guards and what it is.

- **It overlaps none of main's changes: it merges on its existing check.**
  None of the pull request's files, nor the old path of a file it renamed, is a path main changed since its check started.
  GitHub is asked for no update of its branch, and no check runs again.
  Before the merge, where the repo names them, `jmerge` runs the fast guards on its tree merged over main ("The guards on the merged tree"), which catch a clash two pull requests make with no file in common, as #923 and #935 made on 2026-11-03 with two new `v007_` files.
  A merge that GitHub refuses waits as `the merge failed: <what GitHub said>`, and the next run judges it again.
  It takes no place in the line below, and merges while a pull request that goes through the line holds it.
- **It overlaps, in a repo that names guards: it merges on the guards on its merged tree.**
  Some of its files are paths main changed since its check started, and the repo has a `merged-tree-guards` file.
  It merges as one that overlaps none does: GitHub is asked for no update of its branch, no check runs again, and the guards on its tree merged over main decide, with main's own run and jbus's revert of a red main's culprit behind it.
  Josh's vision of 2026-11-06, item F: "merge as soon as green, not stopping to rebase if not needed or to catch up with main".
  It takes no place in the line below, and merges while a pull request that goes through the line holds it.
  Where its guards fail or were stopped at their time limit at its head over the tip, it goes through the line instead, in the same run, and is not told to rebase: GitHub's full check over today's main decides, and a check that fails there is its crew's as any red check is.
  A wait of the guards that ends by itself (no slot free, no time left in the run, main moved while they ran) stays that wait, and the next run tries again.
- **It goes through the line: it overlaps in a repo with no guards, its guards failed or were stopped, or it is a revert jbus opened.**
  GitHub merges main into the branch, as "A failed check over a base that moved" does, with `update-branch` and `expected_head_sha`, once for a head and a tip of main.
  The line is `GitHub was asked to merge <base> at <tip12> into it: <base> moved after its check started`, on the `check` step, and `--check` says `<base> moved after its check started: GitHub is to merge <base> at <tip12> into it`.
  GitHub's check at the new head ran over today's main, and it decides by the normal path: the pull request merges once that check passes, and waits as `check has failed` if it fails.
  The review stands across that merge, as across a rebase: its range-diff shows no content.

A repo with no `merged-tree-guards` file runs nothing on the merged tree, and a pull request that overlaps none of main's changes merges on its existing check all the same, with main's own run and jbus's revert of a red main's culprit behind it, while one that overlaps goes through the line.
Josh, 2026-11-05: "we don't need every pr to be up to date".
jstack's guards were off from 15:15 that day, when they outran the 17 minutes jbus gives `jmerge`, and while every such pull request still went through the line, `merge.log` had 418 `in line behind` waits for 16 merges from 15:00 to 18:26, against none from 08:00 to 15:00 with the guards on.
A pull request whose renamed files GitHub did not give is held for you before this (`ready.needs_the_user`), and one you accept is judged as one that overlaps.
A revert jbus opened for a red main goes through the line even where it overlaps in a repo that names guards: its path is "A revert jbus opened" below, and stays as it was.
GitHub's strict "up to date" rule is off on main (ruleset 25665226, `features/repo-guards/main-ruleset.json`, since 2026-11-04), so GitHub merges a pull request whose branch does not hold main's tip.
Were it on, GitHub would refuse each merge on an existing check, and each would wait as `the merge failed`.

`jmerge` asks for that update for one pull request at a time, the one going through the line that `jmerge` would merge next, as a merge queue does, so each merge costs one CI round and not one for every open pull request (2026-11-03: about 30 open, each merge set off a wave of reruns, about 80 branch updates in an hour and 4 merges in 90 minutes).
That pull request holds the line: of those whose only reason left to wait is that main moved after their check, it is the first `jmerge` gets to in merge order (each revert jbus opened for a red main first, then the order of their numbers, with "Migrations" ordering those that add one), with its review, findings, stack, migrations, `merge_after` and holds cleared.
Each base has a line of its own: a pull request into a stack branch or another merge base whose base moved holds no line for those into main, nor one into main for them.
`base-merges.json` keeps it on its record (`line`, with the record's `base`), so it keeps the line across runs while its check at the new head runs.
Every other pull request into that base that goes through the line waits with `it is in line behind #<n>: <base> moved after its check started, and GitHub merges <base> into the branch of one pull request at a time, the one to merge next`, on the `check` step, and GitHub is asked nothing for it until its turn.
That holds for one ahead of `#<n>` in merge order that comes ready later: the update `#<n>` has is not spent again.
The pull request at the head of the line gives it up when it merges, when a check of its fails (one whose failed check is what its turn is for keeps it until the check at its updated head ends), when GitHub keeps a run of its queued through a restart, when a restart of that run never took, or when it waits on anything but `jmerge`, GitHub and its check (`cli.IN_LINE`), such as a review, a finding or a hold; the next one in merge order then takes it, in that same run where it comes after.
It gives it up too when its head is still the one GitHub took the update of 20 minutes (`rejudge.HELD`) after GitHub took it: GitHub makes the new head within seconds, so no check is coming to end its wait.

A required run at the head of the line that GitHub queued and started none of for `ready.QUEUED_MINUTES` (30 minutes, above the p99 queue wait of every required check in `ci.jsonl`) gets one restart (`cli.Repo.unstuck`): `jmerge` closes and reopens the pull request (`rejudge.BaseMerge.restart`), which starts a new run of each workflow in its concurrency group, and logs one wait, `GitHub queued its <check> run at <head> <n> minutes ago and started none: jmerge closed and reopened it to start a new run`.
GitHub refuses to rerun a run it has not ended, and a cancel can leave it queued: on 2026-11-04 #1028 held the line for over an hour on a queued macos job while five pull requests waited behind it.
The restart is spent only once its close and its reopen both took.
`base-merges.json` keeps each step on the head's record (`stuck`) as it takes: the first try (`asked`) before the close, with the reopen owed, then `closed`, then `took`, so a run that stops between two steps leaves a record the next run goes on from.
A close that failed is tried again on each run, and once `ready.RESTART_MINUTES` (10 minutes) have passed since the first try, the pull request gives up the line and waits with `QUEUED_UNRESTARTED`, `GitHub queued its <check> run at <head> and started none, and jmerge could not close and reopen it in 10 minutes of tries (<why>): it gave the head of the line to the next pull request`.
While the close is still being tried, the wait is `QUEUED_UNCLOSED`, `GitHub queued its <check> run at <head> <n> minutes ago and started none: jmerge could not close and reopen it to start a new run (<why>)`.
A reopen that failed is owed, and `rejudge.BaseMerge.reopen` asks it again on each run for the same `ready.RESTART_MINUTES` from the first try, and then asks it no more (`unopened`): the pull request holds the line no more, and on each run `jmerge` says `QUEUED_UNREOPENED`, `GitHub queued its <check> run at <head> and started none: jmerge closed it to start a new run, and its reopen failed for 10 minutes of tries (<why>), so it asks no more and the pull request stays closed until a hand reopens it`, until GitHub lists it open again.
While the reopen is still being asked, the wait is `QUEUED_UNOPENED`, `GitHub queued its <check> run at <head> <n> minutes ago and started none: jmerge closed it to start a new run, and its reopen failed (<why>), which the next run asks again`.
One whose owed reopen took on a later run holds the line no more either, for another took it while it was closed.
Once a restart took, the pull request keeps the line for `ready.RESTART_MINUTES`, since GitHub lists the new run within seconds of the reopen and a run of `jmerge` in the same minute still sees the old one.
Where GitHub then lists no newer run, or the newer one is queued for `ready.QUEUED_MINUTES` too, the pull request gives up the line and waits with `GitHub queued its <check> run at <head> again after jmerge closed and reopened it, and started none in 30 minutes: it gave the head of the line to the next pull request` while that run stays queued.
No runner is at work on `QUEUED_GAVE_UP`, `QUEUED_UNRESTARTED` or `QUEUED_UNREOPENED`, so jbus's `clock.held` raises each to the home as a hold, even for a pull request that GitHub no longer lists open.
A run that started is never restarted, however long it runs.
That restart is the head of the line's only: jbus restarts a required run GitHub queued for `ready.QUEUED_MINUTES` on every open row's pull request, once for the head, by a cancel and a rerun (`jbus.cancelled.unqueue`), and finds the run with `ready.stuck_runs` from the head's workflow runs and their jobs, since the roll-up lists no check of a run with no jobs and `jmerge` then says the check has no run.
jbus's step runs after `jmerge` in a pass, so a run `jmerge` restarted is a new one that jbus does not touch, and a run jbus restarted is a new attempt that `jmerge` counts its 30 minutes from.
A pull request whose check ran over today's main, that overlaps none of main's changes since it, or that overlaps them and merges on its guards, is not in the line: it merges as before, while others wait.
A revert jbus opened for a red main, one that `reverts.json` names (`jmerge.reverts`), comes first in merge order, and takes its base's line from a pull request that holds it and is no revert.
That pull request then waits `in line behind` the revert, and its record in `base-merges.json` stays, with `line` off, so its update is not asked again at the same head and tip.
A revert branches from main's tip, so by number it came last: other pull requests keep merging onto a red main, each moved main past the revert's check, and the revert waited a turn behind every one of them.
`jmerge` asks for the update while `main.json` names main red as well, since the fix of a red main must run over it: a pull request that the red tip fails is then held by its own failed check, as "A failed check over a base that moved" says.
Main's own full run at the merge commit still runs the whole suite, which a pull request's check, of the tests its change selects, does not.
A pull request whose check failed at its own head is judged as "A failed check over a base that moved" says.
`jmerge` judges this only once the pull request has no other reason to wait.
`jmerge` reads no `fresh-check` file: that file names the check command a crew runs, and nothing of a merge.
Nothing pushes a `refs/jstack/green-tree/` ref, and nothing reads one: main's `full` job skips its suite only on a green run's artifact (`scripts/green_tree.py`), so a ref pushed by hand skips nothing.
`jmerge --sweep` removes such a ref once it is seven days old (`sweep.MARKER_DAYS`); the old ones still on the origin are the owner's to remove with it.

## The guards on the merged tree

Two pull requests can each pass their check alone and break main together, as #923 and #935 did with two `v007_` files.
The clash shows on the tree of one merged over the other, so before it merges a pull request whose head does not hold the tip of its base, `jmerge` checks the tree of that head merged over the tip (`features/jmerge/src/jmerge/treeguards.py`).
The command is the first line of the state's `merged-tree-guards` file that is not blank.
jstack's is `make check-fast PART=guards`: the lint, the cross-cutting tests, the catch-all and the changed test files, 385 s in one run on 2026-11-04.
They also run each test file of the selection that main changed or added since the pull request's merge base: the pull request's check ran over that merge base and never saw them.
#1584's check ran over 49695e849, #1588 then added `test_jbus_telemetry_spells.py`, which #1584's change reaches and broke, and the guards on its tree merged over 2380b181d passed without it in 81 s, so main went red for 18.5 minutes (spell 41, 2026-11-10).
Replayed on that merged tree, the guards hold 57 files instead of 50, the 7 main changed since the merge base, and take 144 s instead of 87 s at the desk: they fail on that test, as main's run did, and hold #1584.
They never run the whole suite, even where the change selects every test, as a deleted fixture (#1103) or a change to `scripts/select_tests.py` (#1118) does: the whole suite took 9 to 10 minutes at the desk's load on 2026-11-05, past `LIMIT_SECONDS`, and CI's check of the pull request runs it.
A repo with no such file runs no guards, and a pull request that overlaps none of main's changes merges on its existing check with nothing run on its merged tree, while one that overlaps goes through the line ("Merges cleanly over today's main").
In a repo that names them, the guards run on the merged tree of one that overlaps as of one that does not, and a pass merges either.

The guards run only on a tree no green check covers.

1. With the merge lock held and the base's tip read, `jmerge` merges the head over that tip with `git merge-tree`.
   Where a successful check of this repo already tested that tree over that tip, it merges with no guards run: CI's check runs a superset of the guards, plus the lint, on GitHub's merge of the head over the tip, and leaves an artifact named by the two trees, `checked-tree-<tip tree>-<merged tree>` (`green.checked`), which `jmerge` looks up with two `gh api` calls at most.
   The line of the merge says `CI's check passed its tree merged over <base> at <tip12> in <run url>, so no guards ran`.
   On 2026-11-06 to 11-08, 58 of 97 guard runs, 5318 of 9375 guard seconds, were over a tip CI's check at that head had already tested.
   A lookup that fails, or finds no such artifact, goes on to the guards.
2. It makes the tree a local commit whose parents are the tip and the head, as GitHub's merge ref is, and pushes nothing.
3. It checks the commit out at `merged-tree` in the state directory, runs the command there with `BASE` set to the tip and `MERGE_BASE` to the merge base of the head and the tip, and removes the worktree.
   `make check-fast` hands `MERGE_BASE` to `scripts/select_tests.py --part guards --since <merge base>`, which adds the test files of the selection that main changed between the merge base and `BASE`; with no `MERGE_BASE` the guards are those of the pull request's change alone.
   A worktree that a stopped run left there is removed first.
   The command runs inside a full test slot, through `jgauge test-slot`, as every other suite on the machine does: it is a suite at `-n 6`, and outside a slot it would be one the slot count does not see.
   A `jmerge` that already holds a slot (`JGAUGE_TEST_SLOT` set) runs it in that one, since a second would wait on its own.
4. Where the command exits 0, and the tip has not moved meanwhile, it merges.
   The line of the merge says `the guards passed on its tree merged over <base> at <tip12> in <s> s`, and `merge.log` keeps that line.

A head that already holds the tip is the tree its check ran on, so nothing is built for it.
A non-zero exit holds a pull request that overlaps none of main's changes with `merged over today's <base> at <tip12>, it fails <guard>: its crew rebases it onto <base>, runs the check, and fixes what fails`, on the `rebase` step.
One that overlaps goes through the line instead, as "Merges cleanly over today's main" says, and so does one that overlaps whose guards were stopped.
The guard is the first test pytest calls `FAILED`, else the make target the run stopped in, such as `lint`, else the last line the command printed.
A tip that moved while the guards ran waits as `<base> moved while it was judged`, and the next run builds the tree over the new tip.

The guards wait at most 15 s for a slot (`SLOT_SECONDS`).
With every full slot still taken, they do not start, and the pull request waits as `every full test slot stayed taken for 15 s, so the guards did not start on its tree merged over <base> at <tip12>: the next run tries again`.
That run tries no more trees, and keeps nothing: jbus's next pass runs `jmerge` again about a minute later (`jbus.tick` runs it sooner only when a check ends), so a skip costs a merge about a minute, where a wait inside the run would hold every other merge of it, for as long as a full suite holds a slot.
The guards run at most 10 minutes on one tree (`LIMIT_SECONDS`), counted from when they hold the slot, and stop with every process they started; that waits as `the guards on its tree merged over today's <base> at <tip12> ran past 10 minutes and were stopped`.
A stopped tree is kept like a pass or a failure: the pull request waits until its head or the tip moves (or, where it overlaps, through the line), and later runs go on to the other pull requests, since a tree run again on each run took every run's time on 2026-11-05 and left the rest waiting.
A run starts no guards once it has spent 4 minutes on them and their waits for a slot (`RUN_SECONDS`), so it ends inside the 17 minutes jbus gives it, and a pull request left over waits for the next run.
A tree that cannot be built waits with why, and a head that conflicts with the tip waits as `it conflicts with today's main`.
`merged-trees.json` in the state directory keeps a pass of the check's artifact, a pass, a failure, or a stop at the time limit of the guards on a head over a tip, so a held pull request is not run again until its head or the tip moves, and `--check`, which runs no guards, shows the held line too.
A held pull request gives up its base's line ("Merges cleanly over today's main"), since it waits on its crew.
A run drops the record of each pull request that is no longer open.

## Batches

Where the state has a `merge-batch` file, `jmerge` proves the pull requests main moved past together, on one tree, and merges them all on its pass (`features/jmerge/src/jmerge/batch.py`).
A repo with no such file merges each one alone, as "Merges cleanly over today's main" and "The guards on the merged tree" say.
How many members a run judges decides which proof their tree takes (`batch.kind_of`):

| Members judged in a run | Proof | Where it runs | Waits it makes |
|---|---|---|---|
| one | the single path: its own check, the artifact of its trees, or the guards on its merged tree | this machine, in the run | none |
| two to four (`batch.GUARDS_LEAST`, `batch.GUARDS_MOST`) | one run of the guards on main's tip with each merged in | this machine, in the run, with the merge lock held | none |
| five or more (`batch.LEAST`) | CI's check of that tree, on `jmerge/batch` | GitHub, across runs | `in-batch` and `batch-first` |

**Why each size takes its proof.**
A batch must make no pull request wait for what the single path does not.
CI's batch did: with the batch on from 2026-11-10 04:06 to 22:00 UTC (68 merges), `batch-first` held 184.9 min over 18 waits and `in-batch` 161.3 over 25, 5.1 min a merge, where the guards path's whole path part was 51 min for the same merges in replay (the scout po-batch-why).
A lone member's CI check took 213 s at the median (n 19), where the guards took 86 s (n 314, merge.log), so a batch CI proves waits on a slower proof and holds every other pull request while it runs.
A guards batch is the run the single path was about to make anyway, made once on the tree of every member ready in that run, with no timer to fill it: a wait is what the single path never has, and bors too takes what is ready when the last batch ends.
In a replay of the push's 161 merges (2026-11-09 09:54 to 23:05 EST), the path part's median and p90 in minutes:

| Load | guards one at a time | CI's batch from three | guards batch |
|---|---|---|---|
| as it came (12.3 an hour) | 1.40, 5.03 | 1.43, 4.45 | 1.35, 3.47 |
| twice as fast (24.5 an hour) | 12.27, 46.43 | 4.26, 6.73 | 2.17, 3.79 (2.81, 6.87 if a guards run grows 25% a member) |
| four times as fast (49 an hour) | not given | 6.01 (p90 8.26) | 3.02 to 16.61, by how a guards run grows with its members |

At four times the load CI's batch wins unless a guards run does not grow with its members, so five or more keep CI's batch.
A guards batch takes four at most: where a run grows by half its time a member, a run of four already costs 2.5 runs.
How a guards run grows is not measured yet: each guards batch's line in merge.log, `batch: guards on <n> members ...`, gives it, and the cap of four rests on it.

**A guards batch.**
Once every pull request is judged, two to four members are built as CI's batch is (`batch.build`, below), with the merge lock held from the read of main's tip to the last merge, as the single path holds it for its guards (`cli.Repo.guards_batch`).
The guards run once on that commit, under the rules of the single path's: in a full test slot, none once the run spent `treeguards.RUN_SECONDS`, none once a wait for a slot found none, and their seconds count toward the run's (`treeguards.Guards.on_batch`).
Their `MERGE_BASE` is the merge base of main's tip and every member's head, the oldest commit a member's check ran over, so they run what main changed since any of those checks.
The run says `batch: guards on <n> members over <base> at <tip12>, <passed|failed|stopped|no slot> in <s> s`, a line about no pull request, which merge.log keeps.
On a pass each member merges at its own head, in order, as a proven CI batch's do (`cli.Repo.merge_members`), and its merged line says `the guards passed on its batch of <n> over <base> at <tip12> in <s> s`.
Nothing is pushed to `jmerge/batch`, no batch pull request opens, `batch.json` keeps no batch, and no pull request waits `in-batch` or `batch-first`.
Guards that fail, are stopped or find no slot merge none of them: `batch.json` keeps each member's head under `failed` (`batch.Record.alone`), so none joins a batch again at that head, and each takes the single path in that run, whose guards on its own tree name the failing test for its crew, while `treeguards.RUN_SECONDS` lasts.
`merged-trees.json` keeps nothing of a guards batch: a member's record there is of its own tree, which the single path then runs, and a pass on the batch's tree is no proof of the member's tree alone.
A member that does not merge over those before it is left out of the tree and takes the single path after the batch, its head not under `failed`; where fewer than two merge over the tip, each member takes the single path.
Where the run spent its guards' time, or the guards' worktree could not be made, the run says `batch: not made` with why, and each member takes the single path with its head not under `failed`.
Where another run holds the merge lock, or the repo names no guards, each member takes the single path, as it would alone.

**CI's batch: five members at least.**
A run that judges five or more, past the suspects of a failed batch, builds CI's batch (`batch.LEAST`), which holds every other pull request while its check runs, as the rest of this section says.

**When a batch forms.**
A member is a pull request into the default branch that is ready by every rule but two: main moved after its check started, and the guards on its merged tree.
Its review, findings, Result lines, `Checked:` and `Proved:` lines, own required checks at its head, queue go, holds, protected paths and `merge-off` are all judged first, as for any merge, and a head that conflicts with today's main waits for its rebase.
These stay out, and take the path of today:

- a revert jbus opened for a red main, which still goes first;
- a second pull request that adds a migration, which waits as `it adds a migration, and #<n>, which merges before it, is merging`, so the two merge in their order;
- a pull request whose row merges after one not merged yet, which waits as `merges after` says;
- one whose check ran over today's main, which merges on that check;
- one accepted with `--accept`, and every pull request while `main.json` names main red.

Once every pull request is judged, `jmerge` builds main's tip with each member merged in, in merge order, with `git merge-tree`, each one over the last as its squash will land it, and leaves out one that conflicts with a member before it.
Where two to four are left in, they take a guards batch instead, and the members left out take the single path after it; where fewer than two are left in, it pushes nothing and sends every member down the single path, as a batch that cannot be made does.
A batch holds the most that `batch.json` keeps (`most`, `batch.Record.most`) at most.
The most starts at 12 (`batch.START`), doubles when a batch of that many proves, to 48 at most (`batch.MOST`), and halves when a batch of that many fails after its rerun, to 5 at least (`batch.LEAST`, which a most kept under it is read as).
A batch of fewer, a timeout, a batch that could not be made, and the first half of the suspects leave it: the half is sized by its suspects, not by the most.
A batch proven again in a later run, while another run held the merge lock, is no longer of that many, so it doubles the most once.
Setting `MOST` to 5 holds the most at 5; no setting holds it at 12 and still lets CI's batch of five form, since `batch.LEAST` is also the fewest it holds.
It makes the last tree one commit whose parent is the tip, force-pushes it to its own branch `jmerge/batch`, and opens one draft pull request for it where GitHub lists none open.
`batch.json` in the state directory keeps the tip, the tree, the commit, the members with their heads, when it was pushed, the rerun of its failed check where one was started, whether it is the first half of the suspects, and the most.
The run says `batch: built over <base> at <tip12>, <size> of <most> members at most`, a line about no pull request, which merge.log keeps.
Each member waits as `it is in jmerge's batch over <base> at <tip12>, whose check decides its merge`, with the code `in-batch`: jmerge's own work, which no crew can fix.

**What proves it.**
CI's check of the batch's pull request runs on GitHub's merge of its head over main, whose tree is the batch's tree, since the head holds the tip.
A pass leaves the artifact `checked-tree-<tip tree>-<batch tree>` (`green.checked`), and a later run of the same two trees that reuses the pass finds the artifact the first one left.
A run of `jmerge` that finds that artifact from a successful run of this repo, with main still at the batch's tip, takes the merge lock once and squash-merges each member at its own head, which GitHub must still have, in the batch's order, with no guards run.
Before each merge, main must be at the tip the merge before it left.
Each merge's line says `CI's check passed jmerge's batch over <base> at <tip12> in <run url>, so no guards ran`.
The merges stop at the first that does not land: GitHub refused it (`the merge failed`), it is no longer judged a member at that head, or another hand moved main.
Each member after it waits as `jmerge's batch over <base> at <tip12> stopped at #<n>, which did not merge: the next batch takes it`, with the code `batch-stopped`.
Where another run holds the merge lock, the batch stays proven for the next run.

Only the checks of `ready.REQUIRED`, `check` today, decide a batch: their run leaves the artifact of its tree, so they are what proves it, what fails it, and what its rerun starts again (`batch.failed_jobs`, `batch.state_of`).
The rest of a repo's `required-checks` file judges each member's own pull request, at its head, and never the batch's.
`borders` is one of them: it judges a pull request's diff, which features it touches, and not its tree, and a batch's diff is its members' diffs together, so a batch whose members touch two features fails it every time, though each member passed it alone.
Read as the batch's failure, it failed 13 of the 15 batches of two or more on 2026-11-10, and 14 of them merged no member.
A batch whose pull request fails `borders` is pending while `check` runs, and proven once `check`'s artifact is found.

While a batch is out (checked, or proven and not merged yet), a pull request that would merge alone waits as `jmerge's batch over <base> at <tip12> is checked and merges first: a merge before it would undo that check`, with the code `batch-first`, and so does a member that came ready after the batch was built.
`jmerge` decides that wait once every pull request is judged (`batch.Batching.held`): where a checked batch is not kept, since a member is no longer judged one at its head, the pull request merges alone in that run, before any batch is built again.
The run that merges a proven batch says no such wait: once the batch's merges end it, each pull request held for it is judged again over the tip they left (`cli.Repo.after_batch`), and goes on in that run, in merge order, with each member that came ready after the batch was built.
Main moved past its check with the batch's merges, so a held pull request still ready is a member now, and their count gives the path, as for any run: one takes the single path, two to four share one guards run, and five or more are CI's next batch.
One that falls short over the new tip says why, as any pull request does, and one whose check ran over that tip merges on it.
Only where another run holds the merge lock, so the batch stays proven, does each held pull request say its `batch-first` wait again, for the run that merges it.
A revert still merges first, and its merge ends the batch, which is built again over the new tip.
A batch still checked whose tip moved, whose pull request GitHub no longer lists at its commit, or whose member is no longer judged one at its head, is built again in that run, over today's tip.
The batch's pull request is `jmerge`'s own: it has no brief and no row, `jmerge` never judges it and never merges it, and it stays open from one batch to the next.
Like the guards, the batch runs no browser tests: browser.yml skips a draft.

**What a failed batch does.**
A flake or a runner fault is no evidence against a member either, so a batch of two or more (every batch built since the rule of three) whose check failed for the first time is not failed yet: in that run `jmerge` asks GitHub to start the failed jobs of its workflow run again, `gh run rerun <id> --failed`, once (`cli.Repo.rerun_batch`).
`batch.json` keeps the rerun with the batch, under `rerun`: the links of the failed jobs it was started for, each in the run it reran, and when it was started (`batch.Rerun`), kept before GitHub is asked, so a run that stops between the two never asks twice.
The batch is pending while the rerun runs, its members still `in jmerge's batch`, and its pass merges every member by batch with no suspects kept.
A listing whose failed jobs are all of those the rerun was started for is GitHub still showing the first attempt, since a job of a new attempt has a link of its own, so the batch stays pending.
A batch built anew has no rerun, as `rerun` goes with the batch it was started for.
A batch whose check failed after its rerun, whose rerun GitHub refused, whose failed check has no workflow run to rerun, or of one member, has failed.
One that went 30 minutes from its push, or from its rerun, with no artifact found (`batch.PENDING_MINUTES`) timed out: a check that passed with no artifact found waits for that limit, its members still `in jmerge's batch`, since the lookup reads a gh error, or a run not yet concluded a moment after its last job passed, as none, and the next run that finds the artifact merges the batch.
A timeout is no evidence against a member, as a GitHub or lookup outage times out every batch: a batch of two or more that timed out is built again whole (a half of the suspects as that same half), in that run, over today's tip, once (`again` in `batch.json`, `batch.Record.late`), and its pass merges every member by batch with no suspects kept.
Only a second timeout in a row has failed it, so an outage costs one more check limit before the narrowing, and a batch that never gets an artifact still ends; a batch of one that timed out has failed.
A failed batch of two or more runs no guards: `batch.json` keeps its members, in merge order, under `suspects` (`batch.Record.fail`).
The next batch, built in that run over today's tip on the same branch and pull request, is the first half of them (the larger half where their count is odd, `batch.narrow`), but only while that half holds five or more (`batch.Batching.chosen`).
So CI's checks of halves find the member that failed it, where the guards of every member ran one at a time on this machine.
A proven half merges as any batch does, and the next batch is the first half of the suspects that are left.
A failed half becomes the suspects in turn, and a suspect of the batch before that is not in it is one no more.
While suspects are kept, every other member waits as `batch-first`, and a suspect outside the half waits the same way.
Where the half would hold fewer than five, as for a failed batch of five to eight, or the one to eight suspects a proven half leaves, every suspect goes down the single path, and shares no guards run, since the suspects hold a failure in that run, in merge order: its merged tree's guards, which name the failing test for its crew, or the line ("The guards on the merged tree").
`batch.json` keeps the head of each under `failed` until it moves (`batch.Record.alone`), so none joins a batch again at that head, and the other members are judged as where no suspect is left: CI's batch where five or more remain, a guards batch where two to four do.
A failed batch of one, kept from before the rule of three, does the same with its member.
A suspect whose head moved, that is no longer open, or that is no longer judged a member leaves the suspects.
A batch that cannot be made, whose push or pull request GitHub refused, or a half of the suspects that holds fewer than five once the members that conflict are left out, sends every member down the single path in that run, after a line that starts `batch: not made`, and keeps the suspects' heads under `failed`.

## A failed check over a base that moved

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on that same merge.
So a check that failed while the base was red stays red after the base is fixed, though the pull request owes no change (`features/jmerge/src/jmerge/rejudge.py`).
`jmerge` judges such a pull request again when all that holds it is a required check that ran and failed, it merges cleanly, and its base (`baseRefName`) has moved since the check started.
That holds for every required check the `required-checks` file names, `borders` as much as `check`.
It judges the pull request as if the failed checks had passed, and a pull request that waits on anything else says that instead of `<check> has failed`.
So a crew is asked for what its pull request is short of, such as a scoped review of a push after its review, and its base is merged in once that is done.
It asks GitHub to merge the base into the branch, `PUT /repos/{owner}/{repo}/pulls/<n>/update-branch` with `expected_head_sha`, which rewrites no history.
The line is then `GitHub was asked to merge <base> at <tip12> into it: its check failed before <base> moved`, or `GitHub did not merge <base> at <tip12> into it: <what GitHub said>`.
It asks once for a head and a base tip, and keeps what GitHub said in `base-merges.json` in the state directory.
`--check` asks nothing, and says `its check failed before <base> moved: GitHub is to merge <base> at <tip12> into it`.
That update takes its place in the line "Merges cleanly over today's main" keeps, as a green pull request's does: GitHub merges the base into one branch at a time, red or green, the one first in merge order while no other holds the line.
Every other red pull request main moved past waits `in line behind #<n>`, and GitHub is asked nothing for it until its turn, so each merge costs one CI round and not one for each red pull request (2026-11-03, #1009's probe: with one green pull request in line and two red ones, GitHub was asked to update all three each time main moved).
A red one waits rather than going first: its update only guesses that main caused its failure, and the green one at the head of the line is nearer its merge.
Once its turn comes it holds the line until its check at the updated head ends, and gives it up when that check fails, as a green one does.
A red pull request whose update `jmerge` does not ask for at all, while `main.json` names main red or when its runs failed a same test twice (below), takes no place in the line and keeps the line `<check> has failed`.
GitHub's new check at the new head then decides by the normal path, and a change broken on its own fails there as its own.
A pull request broken on its own is not given its base again: when the last two runs of a required check it failed both failed a same pytest id, and main's run of that check at neither run's base failed it, `jmerge` asks GitHub nothing and keeps the line `<check> has failed`.
It reads the runs of each failed check's own workflow, and a run's ids from the `FAILED <id>` lines of `gh run view <id> --log-failed`.
Main's run at a run's base is main's latest run of the same check that started by the time the pull request's run started.
A check that main never runs, as `borders` runs on pull requests alone, has no such run, so its repeats are not known and the base is merged in as before.
That is on purpose: a test that main broke in such a check alone would otherwise read as the pull request's own, and hold it for good.
A pull request whose runs failed no test id, or a test that main's check also failed there, is asked for as before, and so is one whose runs or logs GitHub does not give.
It keeps that answer for a head and a base tip in `base-merges.json`, so the logs are read again only once either moves.
A run drops the record of each pull request that is no longer open, once it merged or closed, so the file holds open pull requests alone.
The review stands across the merge, as across a rebase: the range-diff of the reviewed head and the new head shows no content, since it leaves out the merge commit.

## A required check with no run at the head

A check that a repo requires before its workflow reaches the base gets no run at a head whose checks ran before then, and no rerun starts it.
`jmerge` tells it apart from a check still running: its line is `<check> has no run at <head12>`, not `<check> has not passed`.
When that is all that holds the pull request, it merges cleanly, and its base has moved since its check started, `jmerge` asks GitHub to merge the base into the branch, as for a green pull request whose base moved.
It waits its turn in the same line, behind the pull request at its head, as a red one does ("A failed check over a base that moved").
The line is then `GitHub was asked to merge <base> at <tip12> into it: <base> moved after its check started`, asked once for a head and a base tip, and GitHub runs the base's workflows at the new head.
With the base unmoved, the line stays `<check> has no run at <head12>`: that is no wait on the merge runner, so jbus wakes the home once it is held longer than `clock.HOLD_MINUTES` (`features/jbus/src/jbus/clock.py`).
A check that waits on other jobs of its workflow, as `check` waits on its eight parts, is not listed at the head until they end.
While GitHub runs a job of the workflow of the check's name there, the line is `<check>'s run at <head12> is running`, or `is queued` while they all wait, and not `has no run`.
That is a wait on the merge runner, and no base merge is asked for it.

## After a rebase

A crewmate writes nothing about its rebase.
`jmerge` compares the head it finds with the commit the review covers.
That commit is the `Fixed:` commit, or, when the Result has no `Fixed:` line, the head the last `## Review` saw.
A `Fixed:` line written above a later review round is read as no line for that round, so `jmerge` reads the line that round is owed from its `Checked:` line, as `features/jmerge/src/jmerge/ready.py` says of it: "Such a line is read as no line for the last round, so `unwritten_fixed` reads the one that round is owed".
A `Fixed:` commit that a later rebase made is compared from the head the crew kept before that rebase, as `features/jmerge/src/jmerge/cli.py` says of `before_rebase`: "Where a rebase made it, so it leaves `base` elsewhere than `reviewed` does, that is the head the crew kept before the rebase (`kept_fix`), else `reviewed`, as for a `Fixed:` line read from git".
`jmerge` reads the files that either patch changes.
`jmerge` reads a `Rebase:` line in a brief, in any shape, as no line, so no `Rebase:` line holds a pull request.

For a patch that changed, `jmerge` counts the lines main added to those files and the lines the pull request added before the rebase, and looks for each line in the head.
If no line is lost, `git range-diff` between the head the review saw and the rebased head decides whether the review still counts:

- **A clean range-diff carries the review over.**
  The `ready` and `merged` lines say `review carried over: range-diff <old> <new> clean, every line kept`.
- **A rebase with a content change keeps the review, and its checks verify it.**
  The `ready` and `merged` lines say `review kept: <old> rebased as <new>, which its checks verify, every line kept`.
- **Any other content change waits for one scoped review**, unless it is a push that changes only tests, docs or config (below).
  The line is `the rebase changed the content after its review; scoped review of git range-diff --no-color <old> <new>`.
  `jmerge` merges once a `## Review` names the rebased head.
  A range-diff that cannot run, or two patches git cannot compare file by file, count as a content change that waits.

`jmerge` compares the two patches, each from its fork from main, file by file, every line in order with its context, and keeps the files whose lines differ (`rangediff.Verdict.differ`).
A head is a rebase (`rangediff.Verdict.rebased`) where it does not descend from the head the review covers, has as many commits of its own as the reviewed range, and changes every file the reviewed patch changes.
The patch may then differ in any file: the user's word of 2026-11-11 is that CI verifies a rebase, so a rebase gets no scoped round.
A head with a commit more than the reviewed range, a rebase with a fix pushed on it, is no rebase: it is judged as a push.
So is a reviewed range that holds a stacked base's commits, whose files the head's patch does not change.
A rebased head still waits on its `Proved:` and `Checked:` lines at that head, and on a `Dropped on rebase` line where the rebase lost a line, as below.

Of the 277 rounds that waited on `content-changed` for rows merged from 2026-11-04 to 2026-11-11, 149 would have run no scoped round under these rules: 49 rebases as `jmerge` reads them, and 100 pushes whose patch differs in tests, docs or config alone (76 on the reviewed head, 24 on a rebase).
They cost $64.82 of the $129.03 of reviewer calls, and 1,237 minutes after the check with each wait capped at 60.
Those 149 rounds made 3 of the 18 real findings: desk-guards-first #998 round 3 (a rewritten test lost an assert), macos-quick-split-heavy-files #1211 (three cases back on the Mac list) and rt-doc-checks #1291 (a doc line false against main's check.yml).
The 64 other heads that do not descend from the reviewed one, with a commit more or fewer, or a file left out, and a change to code, still get their scoped round; those rounds made 10 of the 18, 7 of them of a fix pushed with the rebase.
`uv run rounds.py && uv run replay.py <checkout>` in `~/.local/state/home/jstack/reports/po-rebase-round-worth/` gives the rounds by push or rebase and by what differs.

The scoped review runs beside the check, not after it.
While a required check has no run at the head, is running, or has not passed, `jmerge` still reads the range-diff, and says the content change in the check's place, with the check's wait as the judgement's note.
jbus launches the scoped reviewer from that line, once for the head, as it does after the check.
The pull request merges only once both the check passed and a `## Review` names the head, in either order: a review that comes in first leaves the check's wait, and a check that passes first leaves the content change.
A failed check and a conflict are said before the content change, as before; a failed check that is all that holds the pull request is judged again as if it passed, and so says the content change too.
Said after the check, the two ran one after the other: 148 of 635 merges from 2026-11-03 to 2026-11-10 waited on `content-changed`, 4.18 minutes at the median, after a check of 5.2.

A review started beside the check is spent on a head whose check then fails.
That cost was mostly paid already: of the 341 heads that waited on `content-changed` over that week, 84 then failed their check, and 65 of those already had a scoped review, launched once the failed check was judged again as passed.
The crew's fix for the check is a new head, whose range-diff needs a scoped review of its own.

`merge-waits.jsonl` (`features/jmerge/src/jmerge/waits.py`) counts a wait from the second the check passed, so its `content-changed` seconds are now only what the scoped review took beyond the check, not the whole review: read the code's seconds before this change and after it as two measures.

The reviewed range leaves out the commits the rebased head's base already holds.
A stacked link's range can start below the link under it, and so hold that link's squash merge on main, which pairs with nothing in the new range.
`jmerge` starts the reviewed range at its fork from the new base instead, when git names one fork above the old start.
A commit of the pull request's own that the rebase changed or left out is still a change.

When the rebase drops a line, `jmerge` waits for the crewmate and prints `the rebase dropped <k> of main's lines in <file> ... with no Dropped on rebase line at <head12>`.
The crewmate puts the lines back, or adds `Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>` to its Result.
The scoped review then rules on each such file with a `Drops: upheld <files>` or `Drops: not upheld <file>: <why>` line.
Until a review covers that head, the pull request waits with `the scoped review has not ruled on the drops in <files>; scoped review of <range-diff>`.
The range-diff is the one the review was carried over by, or `nothing` where `jmerge` ran none, and jbus asks the crew for that scoped review.
Two outcomes need your decision.
When the review does not uphold a drop, the line is `hold <number> <url>: needs <user>, the review did not uphold the drop in <file>: <why>`.
When a review of that head does not rule on a file's drops, the line is `hold <number> <url>: needs <user>, the review of <head12> did not rule on the drops in <files>`.

`jmerge` treats the same way a push, made after the review, that fixes a failed check.
The crewmate writes no line about it: `jmerge` compares the head the review covers with the pushed head by `git range-diff`.
`jmerge` reads a `CI fix:` line as no line.

A push on top of the head the review covers that changes only tests, docs or config keeps the review, as a `Fixed:` head does, also where the crew merged main into the branch before or after it.
`jmerge` takes the files in which the head's patch differs from the reviewed one, as above, so main's own files in the merge are no part of the push, and asks whether every one is a test file (`proved.TEST_FILE`) or of a `proved.EXEMPT` kind, the same files a `tests only` `Proved:` line may change (`ready.first_code`).
Where that holds, the range-diff's content change is no wait and no scoped round is asked for: the pull request waits only on its checks and its `Proved:` and `Checked:` lines at the pushed head (`ready.kept_note`).
The `ready` and `merged` lines say `review kept: <covered12>..<head12> changes only tests, docs or config, every line kept`.
A push whose patch differs in any other file waits for its scoped review.

## Protected paths

`jmerge` reads one list from its own package directory, never from a pull request: `features/jmerge/src/jmerge/protected.txt`.
The list holds patterns and nothing else.

### Patterns

Each line holds one pattern.
A line that starts with `#` is a comment, and the shipped lists have none.

- A pattern that ends in `/` is a directory, and covers everything under it.
  With another `/` in it, or one at its start, it is a path from the root of the repo.
  With no other `/`, it is a directory of that name at any depth.
- Any other pattern is a file.
  With no `/` in it, it is a file name at any depth.
  With one, it is the whole path from the root of the repo: `features/jbus/src/jbus/merge.py`, `/Makefile`.
- `*` matches any run of characters between two `/`, and never a `/` itself.

`jmerge` merges nothing and exits non-zero while the list is missing or has a pattern it cannot read: `**`, a leading `!`, a `\`, or an empty, `.` or `..` part.
It prints `jmerge: <list> has a pattern that cannot be read, so nothing is merged: <pattern> (the grammar: features/jmerge/docs/jmerge.md#patterns)`.

### The lists

**Protected paths** are in `features/jmerge/src/jmerge/protected.txt`.
In every repo `jmerge` merges in, the list jstack ships protects these paths:

- `secrets/`, `.env`, `.env.*`, `*.pem` and `*.key`
- the directories `/policy/` and `/dns/` at the root of the repo
- `/features/jmerge/src/jmerge/protected.txt`, the list itself, which matches only in a repo laid out as jstack is.

`jmerge` holds a pull request that changes one of them, as `hold <number> <url>: needs <user>, touches <first matching path>`.
`jmerge` judges every file a pull request changes.
`gh pr list` lists at most 100 files.
For a longer pull request, `jmerge` reads the whole list, with each file's change type, from GitHub's files endpoint (`repos/{owner}/{repo}/pulls/<number>/files`).
That endpoint lists up to 3000 files.
`jmerge` holds a pull request whose whole list it cannot read, because it has more than 3000 files or the read failed, as `hold <number> <url>: needs <user>, GitHub listed <listed> of the <changed> files it changes`.

## Accept a held pull request

`jmerge --accept` merges, on your word, a pull request that `jmerge` holds.
Never run `gh pr merge` by hand: an agent's is refused by the `merge-command` hook, which prints the accept line in its place.

```sh
jmerge --accept <number> --as user --message <thread id>/<message id>
```

`--message` names your own message in T3 Code, which jbus reads for your words and their time, in place of `--by` and `--at`.
The typed form, `jmerge --accept <number> --by <user> --at "YYYY-MM-DD HH:MM <zone>"`, is still taken, and opens no door.
`<zone>` is your `timezone_label`, or your time zone's abbreviation at that time, such as `CEST`.
[Configuration](../../jinstall/docs/configuration.md#jstack) has both keys.

It lifts the hold at the head where `jmerge` reported it.
`jmerge` records that head in `holds.json` in the state directory.
It refuses a pull request that is not held, other than one waiting in line ("A pull request waiting in line" below), one whose head is not the head on record, and one with no proven safety fact at that head, unless its brief says `Review: none`.

It also lifts one kind of `wait`: a Result's `Proved:` line (the `proved-*` codes, `jmerge.judgement.WAIVED`), which your word stands in for as it does for `Review: none`.
No run keeps a record of a wait, so it lifts it at the head GitHub gives now, and the merge still names that head.
A plain `jmerge` still waits on that line for its crew to fix.
Every other wait but one in line ("A pull request waiting in line" below) is refused, `refused <number> <url>: it is not held, it waits: <reason>`, but for a pull request no brief names on your own message, below, and two of them end with why and the way through (`jmerge.judgement.UNLIFTED`):

| The wait | Why the accept refuses it |
|---|---|
| `no brief has a Result that names it` (`no-brief`) | with no brief, no `Review:` line, review or Result is there to stand on, so only your own message merges it: `jmerge --accept <number> --as user --message <thread id>/<message id>` |
| `its base is <base>, not <default>` (`base`) | `jbus project bases <project> --add <base>` names its base a merge base, and `jmerge` then merges it on main's rules |

**A proven safety fact.**
At the commit it saw, the review proved the one fact that makes the change safe.
That proof is the `Proof:` line of the `## Review` section, a command that ended `exit 0`.
The last review's proof carries over to a later head whose range-diff from the review's head is clean, in every review mode.
That head can be a rebase, a push for a failed check, or a merge of the base into the branch, such as the one `jmerge` asks GitHub for when the base moved after the check started.
It does not carry over a fix pushed for the review's findings, nor a merge of the base that changes the patch, since the range-diff of either is not clean.
Otherwise the reason is `no proven safety fact at <commit12> (blast-radius, review step 5)`.

`--by` takes only the `user` of `~/.config/jstack/config.toml`, which is `user` when that file names none.
It writes an `accepted` line to `merge.log` that records who accepted and when, and then judges the pull request as any other, so `merge-off` applies.
The `merged` line of an accept carries the word it rests on as a note before its revert command, `accepted by <user> at <when>`, with ` on <thread id>/<message id>` where `--message` named your message.
`jmerge --accept <number> --check` says what it would do.

**An accept that does not merge.**
An accept first judges the pull request as its `--check` does, with no run lock, and reads the party that accepts as the accept does.
One that would not merge ends there, at once, and exits 1.
It prints the line its `--check` prints: the `refused` line, or the `wait` or `hold` line of the reason it falls short of, such as `wait <number> <url>: the scoped review has not ruled on the drops in <paths>`.
That run writes nothing to `merge.log` and records no act.
Only an accept that would merge waits for the run lock, which jbus's merge run holds for as long as it runs, and is judged again once it holds the lock.
When that run merged other pull requests, main moved, and GitHub has not yet decided whether the accepted pull request merges.

**An accept waits for GitHub to decide.**
When the one thing an accept is short of is GitHub's answer to whether the pull request merges, on its first look or once it holds the lock, it asks GitHub again for the pull request at the head it judged: after 1, 2, 4, 8, 15 and 30 seconds, about a minute in all.
It judges again on the first answer that decides, so a ready pull request merges in that one run.
One that is short of anything else, such as `merge-off` or a scoped review, says that at once and asks nothing again, since GitHub's answer would not merge it.
When GitHub has still not decided after the last ask, the accept prints `wait <number> <url>: GitHub has not decided whether it merges` (`undecided`), merges nothing, and exits 1: run it again.
`jmerge --accept <number> --check` asks once and does not wait.

**A pull request no brief names.**
A dependabot bump, or a pull request opened by hand, has no brief, and a plain `jmerge` waits on it with `no brief has a Result that names it`.
Your own message merges it, `--message`, as `--as user` or carried by a home; typed words, `--by` and `--at`, are refused.
With no brief there is no review, Result or queue row to judge, so the accept judges it by every rule that needs no brief: its base is one `jmerge` merges into, its required checks passed at its head, it merges over today's base in its turn, a protected path is a door your message opens, and `merge-off` holds it.
It needs no hold on record and no proven safety fact: your word stands in for both, as it does for `Review: none`.
One that falls short of any of those merges nothing, and the accept prints its `wait` line and ends 1.
Its `merged` line names it `#<number>` for its slug, as jbus names a line with no slug, so a reader of `merge.log` finds no brief of it and the root home is told of it: `merged <number> #<number> <commit> "<title>", accepted by <user> at <when> on <thread id>/<message id>, revert: <command>`.

The accept of a held draft merges nothing and marks nothing ready: it prints the draft's wait and ends 1, and keeps no record, so the next run holds it again.

**A pull request waiting in line.**
A pull request whose only wait is its turn in line (`in-line`, "it is in line behind #<n>") is not held, and the accept merges it on no check from before its base moved.
On your own message (`--message`), the accept gives it the head of its base's line instead.
It asks GitHub to merge the base into the branch now and prints `accepted <number> <url>: it takes the head of the line of <base> from #<n>, accepted by <user> at <when> on <thread id>/<message id>`, followed by the pull request's `wait` line.
The pull request that held the head keeps the update GitHub made it and waits in line again.
A later run merges the accepted one once its check passes at the merged head, and its `merged` line carries the same `accepted by ...` note.
If GitHub does not take the update, the line stays as it was and the accept ends 1.
Typed words (`--by`, `--at`) do not move the line.
The word is kept on the pull request's record in `base-merges.json` and is dropped if the pull request gives the line up, for example when its check fails.
A push drops the hold, and so do the merge and a close.

Where the checkout is a project of jbus's, the accept is an act of jbus's, one line of the project's `acts.jsonl`, whatever came of it ([Who acts, and the acts log](../../jbus/docs/jbus/the-queue.md#who-acts-and-the-acts-log)).
`--as` names the party that accepts: `home`, the default, or `user`, which acts only on `--message` and is refused on typed words.
An accept opens a door when the brief holds for one, by a `Holds:` line or a command it runs, and when the pull request touches a protected path, the case "changes access or secrets".
Only you open a door, on your own message: `--as user` with `--message`.
Any other party's accept on a door, a home's or one on typed words, parks a gate for you, `may jmerge merge pull request <number> of <slug>? It holds for <cases>`, with no ` of <slug>` for a pull request no brief names, and merges nothing.
`--message` in a checkout that is no project of jbus's is refused, and there the accept runs on `--by` and `--at` alone and nothing logs it.
`--check` is no act and records nothing.

## Arguments

| Argument | What it does |
|---|---|
| `--check` | Prints `ready` lines in place of merging. It merges nothing, logs nothing and asks GitHub to update no branch. |
| `--accept <number>` | Lifts the hold of one pull request and merges it, on `--message <thread id>/<message id>` or on `--by` and `--at`, as the party `--as` names. |
| `--message <thread id>/<message id>` | With `--accept`, your own message in T3 Code, which jbus reads, in place of `--by` and `--at`. |
| `--as home\|user` | With `--accept`, the party that accepts: `home`, the default, or `user`, who acts on a `--message` alone. |
| `--sweep` | Merges nothing. It removes what each finished thread left once its work is all merged or pushed: the worktree and the branches. It also deletes each marker under `refs/jstack/green-tree/` on the origin whose commit is more than 7 days old. It prints what it removed and what it kept. It keeps a worktree while a process works in it, and also when it cannot read the list of processes to tell: `/proc` on Linux, `lsof` on macOS. With `--check` it prints what is removable and removes nothing. |
| `--claims` | Changes nothing. It prints one line per brief that still holds files, with its state, its home and its `Where:` line. |
| `--scope <slug>` | Changes nothing. It prints, for the brief's branch against the branch it left (the default branch, or for a link of a stack the branch it sits on), `outside: <path>` for each changed file the brief's `Where:` line does not cover, where `Where:` also holds the `docs/` of each feature whose source under `features/<f>/src/` it names, unless `Do not touch:` covers them (`jbriefs.parse.reach`). It prints nothing when every file is inside, and exits 1 with a reason on stderr when the brief's `Where:` names no path or neither the branch nor its pull request can be read. For a branch that is gone, it asks the branch's pull request. |
| `--checks [<pr>]` | Changes nothing. It prints the state of one pull request's checks in one line, each check counted by its latest run: `passed: every check passed at <head>`, `failed: ...`, `wait: ...` or `unrun: no check ran at <head>`. The pull request is a number, an address or a branch, and by default the current branch's. It is the one reading of a pull request's checks. The crew and pr-review skills call it, and jbus reads with the same code (`features/jmerge/src/jmerge/checks.py`). What `jmerge` merges on is narrower: the required checks alone, as the merge rule on green says. |
| `--range-diff <before>..<head>` | Changes nothing and prints `clean: <why>` when the rebase from `<before>` to `<head>` left the content as it was, by the range-diff `jmerge` carries a review over with (`features/jmerge/src/jmerge/rangediff.py`), else `changed: <why>`. |
| `--base <branch>` | With `--range-diff`, the branch both heads sit on, `main` by default. |
| `--remake` | Merges nothing. While a rebase is stopped in this worktree it prints the files to resolve by hand, under `resolve these by hand and git add them, then run this again:`. Once only generated files are left, it makes each one again: it takes the base's version and runs the command the `generated` key of the repo's `[[project]]` in jbus's config gives it (`generated = ["<file> -> <command>", ...]`), `uv lock` for `uv.lock` when the key names none or the config cannot be read, and prints `made again: <file>, by <command> over the base's version`, or `not made: ...` where the command did not write it. With no rebase stopped it prints `no rebase is stopped here: nothing to make again`, and with nothing left `nothing is left to resolve: git rebase --continue`. The crew skill's "A conflict" runs it each time the rebase stops. |
| `--if-free` | Does nothing and exits 75 while another run holds the repo's run lock, which every run that may merge or remove holds for the whole run, in place of waiting for it (jbus's pass and `jbus tick` run it so). |
| `--pulls PATH` | Takes the open pull requests and the default branch from the file jbus's pass read them into (`jbus.pulls`), in place of asking `gh pr list` and `gh repo view`, where the file holds the stamp `--pulls-at` gives; otherwise the run asks GitHub, as a run by hand does. jbus's pass runs it so, and the tick does not. |
| `--pulls-at STAMP` | With `--pulls`: the stamp of the pass that read the list. |
| `--home <id>` | The home that is asking: says what `jmerge` would do of that home's pull requests, as `--check` does, and merges nothing. |

`jmerge` stops most of the `git` and `gh` commands it runs after 120 seconds, or after `JMERGE_TIMEOUT` seconds when that variable is set, and counts such a command as failed.
The commands of a `git range-diff` get 60 seconds each, whatever the variable says.
