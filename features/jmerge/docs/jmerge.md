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
If the file names a check that your repo's CI never runs, every pull request waits.

## Accept a pull request it holds

Run `jmerge --accept <number> --by <user> --at "YYYY-MM-DD HH:MM <zone>"` from the main checkout.
The section "Accept a held pull request" lists what `jmerge` checks before it merges.

## What a merge does

For each ready pull request, `jmerge` runs `gh pr merge <number> --squash --match-head-commit <head>`, then `git pull --ff-only` in the main checkout.
The landing of an integration branch is a merge commit or a squash, as the repo allows ("Integration branches").
`jmerge` writes the squash commit's message itself.
The subject is the pull request's title and ` (#<number>)`.
The body lists the branch's commit messages as GitHub's default does.
`jmerge` removes every AI co-author trailer line from each message (`jmerge.trailers`).
A landing's merge commit keeps GitHub's subject, and its body is the title.
A landing that is a squash gets the squash's message.
When the crewmate's worktree is clean and its branch is at the merged head, `jmerge` removes the worktree, the local branch and the remote branch.
It writes no plan, because `jbus plan` works out an entry's status from its queue rows.
It needs `gh` and `git`.

It prints one line per open pull request, and appends the lines to `merge.log`.
It takes the open pull requests lowest number first, the oldest first, so an older pull request is not passed over by newer ones that became ready with it.
The migration order ("Migrations") and `merge_after` still come before the number.
When a `wait` or `hold` line repeats from run to run, it logs the line only once.

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", ..., revert: gh pr revert <url>` | Merged. The notes between say what was kept, that a review carried over (`review carried over: range-diff ... clean`), that a check over today's main already passed on the same merge tree (`fresh: skipped, tree <tree> passed in <run url>, on <head12> over <main12>`), the guarded path it changes (`guarded: <path>`), or that the repo's merge gate passed (`gate: ok`). The last note is the command that opens a pull request reverting the merge. |
| `wait <number> <url>: <reason>` | Not merged. The reason is the first thing the pull request is short of. A later run merges it once the reason is gone. |
| `hold <number> <url>: needs <user>, <why>` | Not merged, and never by a plain `jmerge`. It is yours to accept. |
| `hold <number> <url>: its merge gate failed: <its first line>` | Not merged: the repo's merge gate did not pass at the head. A gate that passes lifts it, and `--accept` does not. See "Merge gate". |
| `ready <number> <head> <branch> <slug>` | With `--check`: what a run would merge. |
| `wait: could not ask GitHub: gh exited <code>: <what gh said>` | GitHub did not give the open pull requests or the default branch. The line ends on `gh`'s exit code and the first line of its stderr (`it said nothing` where it had none). A `gh` that exited 0 with output that is not JSON says `gh exited 0: its output was not JSON`, and one that named no default branch says `gh exited 0: it named no default branch`. A token and the query of a URL are cut from the text, and it is at most 160 characters. The same text ends the sweep's `could not ask GitHub about its pull request` and the `could not ask GitHub whether a pull request is based on it` that keeps a branch. |

A pull request that waits does not make `jmerge` exit non-zero.
`jmerge` exits non-zero when it runs outside a git repository, when `gh` is missing, when it could not ask GitHub, or when it refuses an `--accept`.

## What ready means

Each item below is a reason a pull request waits.
`jmerge` prints one reason for each pull request, the first one in the order that `Repo.judge` in `features/jmerge/src/jmerge/cli.py` sets.
The section "Protected and guarded paths" describes one more hold and a stricter gate.

- **A draft waits.**
  `jmerge` never merges a draft, whatever flags you pass.
  A crew opens its pull request as a draft, and CI runs no check on one, so a draft is judged as any other pull request but for its checks, and waits on the first reason that holds: its review, its fix, its queue row, a red main, a drop or a hold.
  Once none holds, a run without `--check` marks it ready (`gh pr ready`) and prints `wait <number> <url>: reviewed and fixed, so marked ready, and CI runs its check at <head>`, so its one check runs on the head that merges.
  With `--check`, or where GitHub refuses the mark, it prints `wait <number> <url>: draft`, never a wait on its check.
  A draft whose brief says `Review: none` is marked ready too, so the user's word has a check to go by, and it still holds for that word.
- **A brief names it.**
  A brief's Result has the pull request on its `Branch:` line.
  jbus is the only merger: it runs `jmerge` for every home of the repo, whatever `home-thread` holds, and a scoped home's pull request merges as the root home's does.
  A home's own run, with `--home`, merges nothing, and a brief of another home of the repo is `another home's` to it alone.
- **Its base is the default branch or an integration branch.**
  `jmerge` never merges a pull request based on another branch (`its base is <base>, not <default>`).
  It merges a pull request whose brief has a `Stack:` line only when you pass `--land <stack>`.
  A link jbus stacked, whose brief has a `Stacked on:` line, is no such hold: it waits as `it is stacked on <branch>, and merges after <slug> merged and jbus moved it onto <default>` while its line names its base's branch, whatever base GitHub gives it.
  Once jbus wrote the commit its base merged as, it waits as `<slug> merged as <sha>, which its head does not hold: it merges after its crew rebased it onto <default>` until its head holds that commit.
  An integration branch is one the project's `integration` file names ("Integration branches").
- **The review is done.**
  The brief has a `## Review` section with a verdict.
  If the review had findings, the Result has a `Fixed:` line that names the head or says `none needed`.
  A `Second pass: needed since <head>` line makes the pull request wait for a review of a later head.
- **Every blocking finding is answered.**
  Each blocking finding needs an answer that counts, for every pull request and not only after a second pass.
  `jbriefs --findings` reads every `## Review` section into one list.
  Its parser, `features/jbriefs/src/jbriefs/findings.py`, is the one the crew skill and jbus use too.
  Each finding gets an id, `F1`, `F2`, ..., in the order it appears.
  Two reviewers' findings share one id when they are at the same head, in the same file within 5 lines (`NEAR`), and cite the same principle.
  Three kinds of finding block: an `(bucket: Act on)` finding, a finding written before the buckets existed, and a finding tagged `(risk: <area>)` in any bucket.
  A `Consider` finding does not block, and a finding's severity does not change whether it blocks.
  An answer is `Finding F<n>: fixed, ...` or `Finding F<n>: not fixed, ..., because <reason>`.
  A decline counts only if its reason cites a `path:line`, a command in backticks, or a gate the Result names (`Gate: question <n>`).
  It also counts only if no other finding was declined for the same reason.
  A finding tagged `(risk: <area>)` covers security, auth, billing, data, migrations or concurrency.
  A decline of such a finding counts only if it cites a gate.
  The crew parks that gate with the default "fix it".
  The pull request waits with one of these: `its findings are not handled: F1, F3 have no answer by id`, `... the decline of F2 cites no path:line, command or gate`, `... the decline of F2 gives the reason of F1`, `... F1 on auth declined with no gate question`.
  A brief written before findings had ids answers them with `Finding: fixed, ...` lines that have no id.
  `jmerge` matches those answers to the findings by count, in order.
  Such a brief waits with `its findings are not handled: <k> of <n> have no Finding line`.
  A decline that says `because .` is not an answer.
  jbus's `expedite` tells the crew about each of these waits, with the ids.
- A brief that says `Review: none` waits with `its brief says Review: none, so it needs the user's word`.
- A brief that says `Review: after` skips the review's gates.
  `jmerge` asks for no `## Review`, verdict, `Fixed:` line or answered finding.
  A review written while the pull request is open does not change its wait reason (`ready.after`).
  Its reviewer still runs, and turns the findings into one queue row, `cleanup-<slug>` (`jbus cleanup`), a follow-up that jbus approves by the follow-up rule, when it is queued or on the next pass, where `<slug>`'s go holds.
  The pull request merges once its required checks pass, and its `Skills run:`, `Rebase:` and `Dropped on rebase:` lines meet their rules.
  A pull request that changes a guarded path still waits for a review of its head.
- A brief that says `Review: twice` first waits for three things: its first review, answers by id to that review's findings, and a `Fixed:` line that names a pushed head.
  It then waits for a second review, written at a head later than the first review's (`its second review is not written at <head>`).
  The second review's findings block no merge, since its reviewer files the `warning` and `error` ones as a cleanup row (`jbus cleanup`).
  `jmerge` asks for no scoped review, no ruling on a decline, and no range-diff review after a rebase.
  A brief whose first review was clean, or whose Result says `Fixed: none needed`, needs no second review.
- **The required checks passed, and GitHub reports that the pull request can merge.**
  Green means that the latest run of each required check at the head passed, whatever the other checks say.
  A repo names its required checks in a `required-checks` file in its state directory, beside `fresh-check` and `integration`.
  The file has one check name per line, and `jmerge` ignores blank lines and the spaces around a name.
  With no such file, or one that names no check, the only required check is `check` (`ready.REQUIRED`).
  A check that the repo's workflows never run then blocks no merge.
  For example, jstack's own state directory names `check` (the suite) and `borders` (the border lint), so its pull requests wait for both.
  A pull request waits with `<check> has not passed` for the first required check that has not passed, and with `it conflicts with its base` for a conflict.
  Where GitHub lists no run of that check at the head, the line is `<check> has no run at <head12>` instead: no runner is at work on it, as for a workflow that reached the base after the head's checks ran.
  A pull request into an integration branch has no check of its own to wait on: CI runs the pull request check into main alone, and the branch's red hold stands for it (`ready.unchecked_into`).
- **Its queue row lets it merge.**
  Once each run, `jmerge` reads the `queue.json` of the jbus project that the current checkout belongs to (`features/jmerge/src/jmerge/rows.py`).
  It looks up the row whose slug is the brief's slug.
  When `jbus queue hold` has withdrawn a row's approval, the pull request waits as `its queue row is held: approve it again to let it merge`.
  A hold stops a merge as it stops a launch, and `--accept` does not lift it.
  A row with no go waits as `its queue row has no go: the user's go, or the bot's, lets it merge (jbus queue approve)`, and a go given with `jbus queue approve`, or the bot's over `POST /act`, lets it merge.
  When a row names other rows in `merge_after`, its pull request waits as `merges after <slug> (#<n>), not merged yet` for the first of them that is not `merged` or `done`.
  `jmerge` judges it again on the run after the one in which that other pull request merges.
  A pull request built on another open pull request's branch carries that one's commits, and a merge of it lands them too.
  So when its head contains the head of another open pull request, and its base does not, it waits on that one's `merge_after` as on its own: `carries <slug>'s commits (#<n>), which merges after <slug> (#<n>), not merged yet`.
  That holds while the carried row is not `merged` or `done`, and also for a pull request whose brief has no queue row.
  When either head cannot be read, even from `refs/pull/<n>/head`, it waits as `its head or <slug>'s (#<n>) cannot be read to see whether it carries it`.
  A link of a stack, whose brief has a `Stack:` line, keeps the stack's own rule instead.
  When the queue exists but cannot be read, every pull request waits with `its queue cannot be read, so its holds and merge order are not known`.
  A repo with no jbus config, or that no project names, has no queue and no such wait.
  `jmerge` judges these after the review and rebase gates, so it reports a missing review or rebase line first.
  It judges them before the fresh check, so a run never asks GitHub to update a pull request that must wait.
- **Main is not red, or it is the fix of a red main.**
  jbus records main's red tip as `broken` in `main.json` beside the queue, and that file is the one record of it (`features/jbus/docs/jbus.md`).
  While `main.json` names a red tip and main's tip is not green, `jmerge` merges only a fix of it.
  Every other pull request waits as `main is red at <sha12>, its fix merges first`.
  A fix is known by what its own check proved, whatever its slug, since the row that writes the code is often not the one jbus filed: on 2026-10-27 the fixes were two flow rows, held behind a red whose `main-red-` row closed with no pull request.
  A pull request is the fix when its head contains the red tip, every check at that head passed, and the jobs of its `check` ran each test that failed at the red tip.
  The browser run's jobs do not count: its `pytest -m browser` names no path, yet it ran only the browser tests.
  `main.json` keeps those tests as `failed`, read once from the red run's logs (`jbus.mainmoved.failed_at`).
  A job's log says what it ran by its one pytest command: the test files and folders it names, or with none the whole suite.
  A log with no such command, or more than one, or one that leaves tests out by name (`-k`, `--deselect`, `--lf`), says nothing.
  A test the fix deleted or skipped counts as passed, as it does for main's own check.
  Where the red run's logs name no failed test, or fewer than they count (a part that ran out of time, a lint), nothing proves the fix but its slug.
  The brief `main-red-<sha12>` that jbus files for the red is still a fix by its slug.
  A pull request whose check ran other tests, failed, or ran at a head without the red tip waits.
  `jmerge` reads the logs only for a green pull request into a red main, once a run for each head, and stops once they cover every failed test.
  `jmerge` judges this after the queue row's wait and before the fresh check.
  The wait ends when jbus sees a green tip.
  After the fix merges and the check of main's new tip passes, the other pull requests stop waiting on the next run.
  A repo with no jbus config, no project or no `main.json` has no such wait.
  If `jmerge` cannot read the file, it reports that main's state is not known.
  `jmerge` checks main's state only for a pull request into main.
  A pull request into an integration branch waits when that branch's tip is red instead, unless it is the fix of that red ("Integration branches").
  jbus checks every commit that was main's tip since jbus's last pass.
  So jbus counts a failed tip as red even while the check of a newer tip is still running.
  A tip's check is its push run's: the check runs of the workflow runs a push to main started (`jbus.watch._check`).
  A run dispatched by hand, on a schedule or for a tag at the same commit, of browser.yml or any other workflow, does not make main red: browser.yml's red takes the path of "Its own browser run did not fail".
  A later green tip ends the red state.
  It does so whether or not jbus delivered its message to the crews of the pull requests that were waiting.
- **Its own browser run did not fail.**
  browser.yml runs on a pull request that changes the view, and is no required check, so a head with no run of it waits for none.
  A run still going at the head waits as any pending run does: `browser has not passed`.
  A run that ended and failed holds the pull request as `its browser run failed at <head12>`, and jbus tells its crew to fix it (`features/jbus/src/jbus/expedite.py`, `TABLE`).
  #557 merged with its browser run red on 2026-10-27 and turned main red, since no rule read that run.
  When main's last browser run on main failed too, the red is main's, and the pull request waits as `main is red at <sha12>, its fix merges first`, the sha12 being that run's commit.
  It is main's only while the row jbus filed for the fix of that run is open, since browser.yml runs on main only nightly and its last run there stays red until the next one.
  Once that fix merged, or where jbus filed no fix for the run, the red is the pull request's, and its crew is told.
  The fix of that red is held by its own red as any other pull request is: the row jbus files as `browser-red-<date>`, or a pull request whose browser run, at a head that contains the commit of main's red run, passed each test main's run failed.
  `jmerge` reads those tests from the logs of main's red run's jobs, and what the pull request's run ran and failed from its own log, as for a red main.
  `jmerge` asks GitHub for main's browser runs only for a pull request whose browser run failed, once a run, and where GitHub gives no answer the red is the pull request's.
  A draft's browser run is waived as its failed checks are, and a reviewed draft is marked ready.
  `jmerge` judges this after main's red, so a pull request short of a review or a rebase line says that first.
- **Its migration is the next in line.** See "Migrations".
- **Its passing check still counts over today's main.**
  See "Fresh against main".
- **Its rebase kept every line.** See "After a rebase".
- **The repo's merge is on.**
  While `~/.local/state/home/<repo>/merge-off` exists, `jmerge` merges nothing.
  A pull request that would have merged waits with `auto-merge is off for this repo`.
  `/nohome merge` makes the file and `/nohome merge on` removes it.
- **Its merge gate passes.**
  `jmerge` checks this last, so that a gate runs only for a pull request that is otherwise ready ("Merge gate").

Before a merge, when the start of the pull request's check is known, `jmerge` runs `git ls-remote` to see whether main is still the commit it judged against.
If main moved, `jmerge` judges the pull request again, at most twice, before it prints `main moved while it was judged`.
For a pull request into an integration branch it checks that branch instead, and the line names it: `<branch> moved while it was judged`.

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

Each reason is a constant of `features/jmerge/src/jmerge/ready.py` (`MIGRATION_TAKEN`, `MIGRATION_MERGING`, `MIGRATION_REBASING`) with a rule in `merge.RULES`.
The rule for a taken number is on the `rebase` step, and the rules for the two waits on another pull request are on the `check` step.

## Fresh against main

A check starts when the earliest run of the first required check at the head starts.
When the repo names no required checks, that check is `check`.
After a `git fetch` in the main checkout, `jmerge` lists the paths that the first-parent commits of the default branch changed since that start.
A pull request waits when one of those paths is one of these:

- a path the pull request also changes
- a CI path in `features/jmerge/src/jmerge/ci-paths.txt` (`.github/workflows/`, `/pyproject.toml`, `/uv.lock`, `/Makefile`)
- a caller of the pull request's files, or a file they depend on

`jmerge` finds callers and dependencies by reading main's files at the tip and the pull request's own files at the head.
One file is linked to another in two cases.
It imports the other as Python does, by the other file's dotted path or any tail of it.
Or it names the other file's path, and that path contains a `/`.
A `conftest.py` counts for every Python file under its directory.
The wait reads:

```
wait <number> <url>: main changed <up to five paths, then "and <k> more"> after its check started at <HH:MM> <zone>; it needs a fresh check
```

`main` there is the name of the base branch.
If main moved only on other paths, none of them a caller or a dependency, the check still counts, and nobody rebases for it.

A caller or a dependency holds the merge only in a repo with a `fresh-check` file, where GitHub's check proves the head over today's main.
A repo with no such file has no way to test that, and a rebase would move the reviewed head for a file the pull request does not change.
So when every changed path main brought is a caller or a dependency, and none is the pull request's own or a CI path, the check still counts there.
The pull request merges on it, and the `ready` and `merged` lines, and `merge.log`, carry this note:

```
fresh: none, main changed related <up to five paths, then "and <k> more">; no fresh-check file
```

A path the pull request also changes, or a CI path, still makes it wait.

A repo opts in to proving a pull request over today's main with a `fresh-check` file in its state directory.
`jmerge` reads only that the file is there: no suite runs on this machine for a merge, and the command in the file is not run.
`jmerge` merges the head over today's main with `git merge-tree`.
It first asks GitHub for a green marker of that merge's tree (`features/jmerge/src/jmerge/green.py`).
A green marker is one of two things:

- a `green-tree-<tree>` artifact of a successful run of the repo's own `.github/workflows/check.yml`, not a fork's
- the ref `refs/jstack/green-tree/full/<tree>` or `refs/jstack/green-tree/selected/<tree>` on the origin

A marker counts only for the exact tree it names.
With a marker, the pull request merges on it, and the `ready` and `merged` lines say `fresh: skipped, tree <tree> passed in <run url or desk commit>, on <head12> over <main12>`.
`merge.log` keeps that note, and jbus logs it in `events.jsonl` as that line's `jmerge` event.
When the marker is for another tree, when a red run left it, when there is none, or when GitHub could not answer, `jmerge` asks GitHub to merge main into the branch, as "A failed check over a base that moved" says.
The line is then `GitHub was asked to merge <base> at <tip12> into it: <base> moved after its check started`.
`--check` asks nothing, and says `<base> moved after its check started: GitHub is to merge <base> at <tip12> into it`.
GitHub's check at the updated head decides by the normal path: it waits while that check runs, waits while it is red, and merges once it passed there.
That check runs on the merge result, so a caller main added that the pull request breaks fails there.
A head that does not merge over today's main waits with `it conflicts with today's main`, and GitHub is not asked.
A pull request that waits on something else, such as a line its rebase dropped or a hold that only the user can lift, asks GitHub nothing.
`jmerge` judges whether it is fresh only once it has no other reason to wait.
`jmerge` pushes no marker: the desk refs it pushed before fl-gh-recheck are only read, and `jmerge --sweep` removes them after seven days.
Nothing writes `fresh.json` or `fresh.lock` in the state directory any more, and nothing reads them.

## A failed check over a base that moved

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on that same merge.
So a check that failed while the base was red stays red after the base is fixed, though the pull request owes no change (`features/jmerge/src/jmerge/rejudge.py`).
`jmerge` judges such a pull request again when all that holds it is a required check that ran and failed, it merges cleanly, and its base (`baseRefName`, main or an integration branch) has moved since the check started.
That holds for every required check the `required-checks` file names, `macos` as much as `check`.
It judges the pull request as if the failed checks had passed, and a pull request that waits on anything else says that instead of `<check> has not passed`, a red base included.
So a crew is asked for what its pull request is short of, such as a scoped review of a push after its review, and its base is merged in once that is done (#529, 2026-10-27: ten hours on `macos has not passed` while it was short of a scoped review that nobody was asked for).
It asks GitHub to merge the base into the branch, `PUT /repos/{owner}/{repo}/pulls/<n>/update-branch` with `expected_head_sha`, which rewrites no history.
The line is then `GitHub was asked to merge <base> at <tip12> into it: its check failed before <base> moved`, or `GitHub did not merge <base> at <tip12> into it: <what GitHub said>`.
It asks once for a head and a base tip, and keeps what GitHub said in `base-merges.json` in the state directory.
`--check` asks nothing, and says `its check failed before <base> moved: GitHub is to merge <base> at <tip12> into it`.
GitHub's new check at the new head then decides by the normal path, and a change broken on its own fails there as its own.
A pull request broken on its own is not given its base again: when the last two runs of a required check it failed both failed a same pytest id, and main's run of that check at neither run's base failed it, `jmerge` asks GitHub nothing and keeps the line `<check> has not passed`.
It reads the runs of each failed check's own workflow, and a run's ids from the `FAILED <id>` lines of `gh run view <id> --log-failed`.
Main's run at a run's base is main's latest run of the same check that started by the time the pull request's run started.
A check that main never runs, as `macos` and `borders` run on pull requests alone, has no such run, so its repeats are not known and the base is merged in as before.
That is on purpose: a test that main broke on macOS alone would otherwise read as the pull request's own, and hold it for good.
A pull request whose runs failed no test id, or a test that main's check also failed there, is asked for as before, and so is one whose runs or logs GitHub does not give.
It keeps that answer for a head and a base tip in `base-merges.json`, so the logs are read again only once either moves (#494, 2026-10-26: nine merges of main, each red on the same test of its own).
The review stands across the merge, as across a rebase: the range-diff of the reviewed head and the new head shows no content, since it leaves out the merge commit.

## A required check with no run at the head

A check that a repo requires before its workflow reaches the base gets no run at a head whose checks ran before then, and no rerun starts it.
`jmerge` tells it apart from a check still running: its line is `<check> has no run at <head12>`, not `<check> has not passed`.
When that is all that holds the pull request, it merges cleanly, and its base has moved since its check started, `jmerge` asks GitHub to merge the base into the branch, as for a green pull request whose base moved.
The line is then `GitHub was asked to merge <base> at <tip12> into it: <base> moved after its check started`, asked once for a head and a base tip, and GitHub runs the base's workflows at the new head.
With the base unmoved, the line stays `<check> has no run at <head12>`: that is no wait on the merge runner, so jbus wakes the home once it is held longer than `clock.HOLD_MINUTES` (`features/jbus/src/jbus/clock.py`).

## Merge gate

A repo opts in to a merge gate with a `merge-gate` file in its state directory, beside `fresh-check`: one line, the command, such as `~/repos/demo/scripts/receipt-check`.
Name it by an absolute path in the main checkout.
A path relative to the head runs the pull request's own copy of the script, and the pull request's author can change that copy so that it passes.
A gate holds `<state>/gate.lock` while it runs.
When a run finds that another run's gate is still running, its pull request waits with `its merge gate waits for another run's gate to end`.
`jmerge` runs the gate before every merge of that repo, once the pull request has no other reason to wait.
It runs the gate in a detached worktree of the head at `<state>/gate/<number>`, and removes the worktree after.
`jmerge` runs it as `sh -c '<command> "$@"' merge-gate <base> <head>`.
So `<base>` and `<head>` are its last two arguments, and they are also `BASE` and `HEAD` in its environment.
`<base>` is the merge base of the head and today's main, and `<head>` is the head `jmerge` would merge.
A green-tree marker never makes `jmerge` skip the gate, and `jmerge` keeps no answer from one run to the next.
It runs the gate again on every run, so it always sees a new head, a moved main or a fix outside git.
`--check` runs it too, and prints its output under the line, each line after `  | `.
On exit 0 the merge goes on and the `merged` or `ready` line ends its notes with `gate: ok`.
On any other exit `jmerge` merges nothing, and the line is `hold <number> <url>: its merge gate failed: <the first line it printed>`, or `exit <code>` where it printed nothing.
`merge.log` keeps the whole output under the hold line, with `  | ` before each line, so that no reader of the log takes it for a line of its own.
When a gate cannot start, the pull request holds with `its merge gate could not start: <why>`.
The causes are a command that is not found or not executable (the shell's exit 126 or 127), or a head that cannot be checked out.
`jmerge` stops a gate that runs over 10 minutes (`Gate.TIMEOUT`), with its process group, and holds with `its merge gate ran over 10 minutes and was stopped`.
jbus's `expedite` tells the crew about each of these holds (`gate`), as it does for the other holds a crew can lift.
The user handles the hold only if the crew does not act.
`--accept` refuses a gate's hold, and `holds.json` does not keep it.
Only a gate that passes lifts it.
A run starts no more gates after its gates have used 5 minutes in total (`Gate.BUDGET`).
So one more gate, stopped at 10 minutes, still ends inside the 17 minutes jbus gives `jmerge`.
A pull request whose gate did not start waits with `its merge gate waits for the next run: this run's gates used their time`.
A repo with no `merge-gate` file runs no gate.
The reviewer runs the same gate on the head it reviews with `jmerge --gate <head>` (the pr-review skill, "The merge gate").

## Integration branches

A series of pull requests can merge into one branch of its own, and that branch lands on the default branch once, when the work is done.
A project names such branches in an `integration` file in its state directory, beside `fresh-check` and `merge-gate`.
The file has one branch name per line, and `jmerge` ignores blank lines and the spaces around a name.
`jmerge` merges a pull request based on one of them the same way it merges one into the default branch.
Every review, check, gate and hold applies, and the merge is a squash.
For such a pull request, read that branch wherever this page says main.
`jmerge` judges its staleness, its fresh check, its rebase and its migration numbers against the branch, and its merge gate gets the merge base with the branch.
The `merged` line names the base after the title, `merged <number> <slug> <commit> "<title>", into <branch>, ...`, and jbus reads and sends it like any other merge.
A merge into the default branch prints no such note.

`jmerge` does not read main's red record (`main.json`) for such a pull request.
Instead, it holds the pull request when the latest run of a check on that branch's tip ended without passing.
The line is `<branch> is red at <sha12>: its latest check failed` (`BASE_RED`, on the `check` step).
`jmerge` asks GitHub for the check runs of the tip once per run (`gh api repos/{owner}/{repo}/commits/<branch>/check-runs`).
As on main, none of these holds the pull request: a cancelled run, a run still going, a tip with no run, or no answer from GitHub.
This hold never applies to the fix of a red main, nor to the fix of this branch's red at its tip.
That fix is the row jbus files for the red, `integration-red-<branch>-<sha12>` (`INTEGRATION_FIX`, `jbus.sidered.integration_branches`), whose `<branch>` is the branch's name in lower case, with each run of other characters than letters, digits, `.`, `_` and `-` made one `-`.
It is also any row whose brief says so in its head, above its first `## ` heading, with one line: `Fixes red: <branch> at <sha>`, where `<sha>` is the red tip, its first 12 characters or more (`FIXES`).
A main sync that brings the fix of a test the branch fails on is such a row.
The exemption holds only for the red it names.
A fix row or a `Fixes red:` line for another branch, or for an older red tip of this one, is held as every other pull request into the branch is.
Once the tip is green, every pull request into the branch is judged again, its fix's included.
If a repo's CI runs only on pushes to the default branch, an integration branch's tip has no check run, and this hold never applies.
jstack's own check workflow runs on each push to a branch under `integration/`, so a branch of its `integration` file is named that way.

The landing is the pull request whose head is an integration branch and whose base is the default branch.
It needs a brief whose Result names it, and `jmerge` judges it like any other pull request.
It lands the way the repo allows merges, which `jmerge` reads once per run (`gh api repos/{owner}/{repo}`, its `allow_merge_commit` and `allow_squash_merge`).
Where the repo allows merge commits, `jmerge` merges with one, `gh pr merge <number> --merge --match-head-commit <head>`.
The branch's commits then keep their history on main, and the `merged` line says `landed with a merge commit`.
Where the repo allows only squashes, `jmerge` squashes, `gh pr merge <number> --squash --match-head-commit <head>`, with the subject and the cleaned body of any squash ("What a merge does").
Main then gets one commit for the whole branch, and each unit's pull request into the branch stays its own record.
The `merged` line then says `landed as a squash: each unit's pull request into <branch> is its own record`.
A repo that allows neither makes the landing wait with `the repo allows rebase merges only, not a merge commit or a squash` (`LANDING_UNALLOWED`, on the `hold` step).
When GitHub does not give the settings, the landing waits too, with `the repo's merge settings could not be read: <what gh said>` (`NO_SETTINGS`, on the `check` step).
`jmerge` never removes its branch, whichever way it landed.
The `merged` line says `kept: <branch> is an integration branch`, and `--sweep` keeps it with the same reason.
If the repo's GitHub settings delete a head branch after its merge, GitHub still deletes the branch, and that setting is the repo's, not `jmerge`'s.

`--sweep` counts a pull request merged into an integration branch as merged.
A project with no `integration` file has no integration branches.

## After a rebase

A crewmate writes nothing about its rebase.
`jmerge` compares the head it finds with the commit the review covers.
That commit is the `Fixed:` commit, or, when the Result has no `Fixed:` line, the head the last `## Review` saw.
`jmerge` reads the files that either patch changes.
A brief from before this rule may still say what its rebase did, with `Rebase: patch unchanged, before <commit>, head <commit>` or `Rebase: patch changed in <files>, before <commit>, head <commit>`.
`jmerge` still reads such a line.
For `patch unchanged`, it works out both patch-ids again from the two commits.

For a patch that changed, `jmerge` counts the lines main added to those files and the lines the pull request added before the rebase, and looks for each line in the head.
If no line is lost, `git range-diff` between the head the review saw and the rebased head decides whether the review still counts:

- **A clean range-diff carries the review over.**
  The `ready` and `merged` lines say `review carried over: range-diff <old> <new> clean, every line kept`.
- **A range-diff with a content change waits for one scoped review.**
  The line is `the rebase changed the content after its review; scoped review of git range-diff --no-color <old> <new>`.
  `jmerge` merges once a `## Review` names the rebased head.
  A range-diff that cannot run counts as a content change.

When the rebase drops a line, `jmerge` waits for the crewmate and prints `the rebase dropped <k> of main's lines in <file> ... with no Dropped on rebase line at <head12>`.
The crewmate puts the lines back, or adds `Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>` to its Result.
The scoped review then rules on each such file with a `Drops: upheld <files>` or `Drops: not upheld <file>: <why>` line.
Until a review covers that head, the pull request waits with `the scoped review has not ruled on the drops in <files>; scoped review of <range-diff>`.
The range-diff is the one the review was carried over by, or `nothing` where `jmerge` ran none, and jbus asks the crew for that scoped review.
Two outcomes need your decision.
When the review does not uphold a drop, the line is `hold <number> <url>: needs <user>, the review did not uphold the drop in <file>: <why>`.
When a review of that head does not rule on a file's drops, the line is `hold <number> <url>: needs <user>, the review of <head12> did not rule on the drops in <files>`.

`jmerge` treats the same way a push, made after the review, that fixes a failed check.
The crewmate adds `CI fix: <new head>, after the review of <reviewed head>` to its Result, and `jmerge` compares the two heads by `git range-diff`.

## Protected and guarded paths

`jmerge` reads three lists from its own package directory, never from a pull request: `protected.txt`, `guarded.txt` and `features/jmerge/src/jmerge/ci-paths.txt`.
The last list holds the paths that decide whether a check still counts ([Fresh against main](#fresh-against-main)).
Each list holds patterns and nothing else.

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

`jmerge` merges nothing and exits non-zero while a list is missing or has a pattern it cannot read: `**`, a leading `!`, a `\`, or an empty, `.` or `..` part.
It prints `jmerge: <list> has a pattern that cannot be read, so nothing is merged: <pattern> (the grammar: features/jmerge/docs/jmerge.md#patterns)`.

### The lists

**Protected paths** are in `features/jmerge/src/jmerge/protected.txt`.
In every repo `jmerge` merges in, the list jstack ships protects these paths:

- `secrets/`, `.env`, `.env.*`, `*.pem` and `*.key`
- the directories `/policy/` and `/dns/` at the root of the repo
- `/features/jmerge/src/jmerge/protected.txt` and `/features/jmerge/src/jmerge/guarded.txt`, the two lists themselves, which match only in a repo laid out as jstack is.

`jmerge` holds a pull request that changes one of them, as `hold <number> <url>: needs <user>, touches <first matching path>`.
`jmerge` judges every file a pull request changes.
`gh pr list` lists at most 100 files.
For a longer pull request, `jmerge` reads the whole list, with each file's change type, from GitHub's files endpoint (`repos/{owner}/{repo}/pulls/<number>/files`).
That endpoint lists up to 3000 files.
`jmerge` holds a pull request whose whole list it cannot read, because it has more than 3000 files or the read failed, as `hold <number> <url>: needs <user>, GitHub listed <listed> of the <changed> files it changes`.

**Guarded paths** are in `features/jmerge/src/jmerge/guarded.txt`, which is empty.
No path is guarded, and a ready pull request merges with no proven safety fact at its head.
Adding a pattern to the file guards that path again.
The file is protected, so the user merges that change.
`jmerge` merges a pull request that changes a guarded path only under a stricter gate.
For each part of the gate that fails, it prints `wait <number> <url>: guarded (touches <first guarded path>), <reason>`:

- **A check with a start time.**
  `check` passed at the head, and `jmerge` knows when its earliest run there started.
  Otherwise the reason is `its check has no start time`.
- **A finished review of that head.**
  Every blocking finding has its answer, as the rule above asks of every pull request.
  The head is the one the review saw, the `Fixed:` commit, or a head that a clean range-diff carried the review over to ("After a rebase").
  In a brief from before the current rule, it can also be the head named on a `Rebase: patch unchanged` line, when the patch-ids of its two commits match.
  Otherwise the reason is `its head is not the one its review saw`.
- **A rebase, and no local check.**
  If main changed one of its paths, a CI path, or a caller or a dependency of its files since the check started, a guarded pull request waits for a rebase, and GitHub is not asked to update it.
  Its line ends `it needs a rebase`.
- **A proven safety fact.**
  At the commit it saw, the review proved the one fact that makes the change safe.
  That proof is the `Proof:` line of the `## Review` section, a command that ended `exit 0`.
  A proof carries over a rebase, or a `CI fix:` push, whose range-diff is clean.
  It does not carry over a fix pushed for the review's findings.
  Otherwise the reason is `no proven safety fact at <commit12> (blast-radius, review step 5)`.
- **Rules that are main's.**
  Before it judges a guarded pull request, `jmerge` runs `git fetch` in the checkout that contains its own package.
  It goes on only if the package there has no uncommitted change and matches the default branch of `origin`.
  If that checkout is behind, `jmerge` pulls it, and guarded pull requests wait for the next run: `jmerge pulled main's rules; judged on the next run`.
  After a merge that changes `features/jmerge/src/jmerge/`, every later guarded pull request of that run waits: `jmerge's rules changed in this run`.

## Accept a held pull request

`jmerge --accept` merges, on your word, a pull request that `jmerge` holds.
Never run `gh pr merge` by hand.

```sh
jmerge --accept <number> --by <user> --at "YYYY-MM-DD HH:MM <zone>"
```

`<zone>` is your `timezone_label`, or your time zone's abbreviation at that time, such as `CEST`.
[Configuration](../../jinstall/docs/configuration.md#jstack) has both keys.

It lifts the hold at the head where `jmerge` reported it.
`jmerge` records that head in `holds.json` in the state directory.
It refuses a pull request that is not held, one whose head is not the head on record, and one with no proven safety fact at that head.
`--by` takes only the `user` of `~/.config/jstack/config.toml`, which is `user` when that file names none.
It writes an `accepted` line to `merge.log` that records who accepted and when, and then judges the pull request as any other, so the guarded gate and `merge-off` apply.
`jmerge --accept <number> --check` says what it would do.

## Arguments

| Argument | What it does |
|---|---|
| `--check` | Prints `ready` lines in place of merging. It merges nothing, logs nothing and asks GitHub to update no branch. It does run the merge gate, and prints its hold. |
| `--accept <number>` | Lifts the hold of one pull request and merges it, with `--by` and `--at`. |
| `--sweep` | Merges nothing. It removes what each finished thread left once its work is all merged or pushed: the worktree and the branches. It also deletes each marker under `refs/jstack/green-tree/` on the origin whose commit is more than 7 days old. It prints what it removed and what it kept. It keeps a worktree while a process works in it, and also when it cannot read `/proc` to tell. With `--check` it prints what is removable and removes nothing. |
| `--claims` | Changes nothing. It prints one line per brief that still holds files, with its state, its home and its `Where:` line. For a brief with an open pull request, the line goes on with `Diff:` and each file that pull request changes, or that its last Result's `Wider:` line names, which its `Where:` does not cover, in backticks. GitHub lists up to 100 files of each pull request here. jbus reads the lines on each pass to tell an `overlap`. |
| `--scope <slug>` | Changes nothing. It prints, for the brief's branch against the branch it left (the default branch, or for a link of a stack the branch it sits on), `outside: <path>` for each changed file the brief's `Where:` line does not cover, and `wider: <path>: <why>` for each one the last Result's `Wider: <path>: <why>` line gives a reason for. It prints nothing when every file is inside, and exits 1 with a reason on stderr when the brief's `Where:` names no path or neither the branch nor its pull request can be read. For a branch that is gone, it asks the branch's pull request. |
| `--checks [<pr>]` | Changes nothing. It prints the state of one pull request's checks in one line, each check counted by its latest run: `passed: every check passed at <head>`, `failed: ...`, `wait: ...` or `unrun: no check ran at <head>`. The pull request is a number, an address or a branch, and by default the current branch's. It is the one reading of a pull request's checks. The crew and pr-review skills call it, and jbus reads with the same code (`features/jmerge/src/jmerge/checks.py`). What `jmerge` merges on is narrower: the required checks alone, as the merge rule on green says. |
| `--range-diff <before>..<head>` | Changes nothing and prints `clean: <why>` when the rebase from `<before>` to `<head>` left the content as it was, by the range-diff `jmerge` carries a review over with (`features/jmerge/src/jmerge/rangediff.py`), else `changed: <why>`. |
| `--base <branch>` | With `--range-diff`, the branch both heads sit on, `main` by default. |
| `--remake` | Merges nothing. While a rebase is stopped in this worktree it prints the files to resolve by hand, under `resolve these by hand and git add them, then run this again:`. Once only generated files are left, it makes each one again: it takes the base's version and runs the command the `Generated: <file> -> <command>` lines of the state's `notes.md` give it, `uv lock` for `uv.lock` where no line does, and prints `made again: <file>, by <command> over the base's version`, or `not made: ...` where the command did not write it. With no rebase stopped it prints `no rebase is stopped here: nothing to make again`, and with nothing left `nothing is left to resolve: git rebase --continue`. The crew skill's "A conflict" runs it each time the rebase stops. |
| `--gate <head>` | Merges nothing. It runs the repo's merge gate in this worktree on `<head>`, as the reviewer does: with where the pull request left its base and `<head>` as its last two arguments and as `BASE` and `HEAD`, and a limit of 9 minutes. It prints nothing for a repo with no gate or a gate that passes, and one `error` finding for a gate that fails or runs over. It exits 1, with why on stderr, when that base could not be worked out. |
| `--pr <pr>` | With `--gate`, the pull request whose base the gate takes: a number, an address or a branch, and by default the current branch's. |
| `--home <id>` | The home that is asking: says what `jmerge` would do of that home's pull requests, as `--check` does, and merges nothing. |
| `--land <stack>` | Merges the pull requests of a stack you said to land, each once its base is the default branch. |

`jmerge` stops most of the `git` and `gh` commands it runs after 120 seconds, or after `JMERGE_TIMEOUT` seconds when that variable is set, and counts such a command as failed.
The commands of a `git range-diff` get 60 seconds each, whatever the variable says.
