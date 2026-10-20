# jmerge

`jmerge` merges every open pull request of the repo it runs in that is reviewed, fixed and green. No model reads anything. The rules are in `src/jmerge/ready.py`.

```sh
uv run --project <checkout> jmerge
```

For each ready pull request it runs `gh pr merge <number> --squash --match-head-commit <head>`, then `git pull --ff-only` in the main checkout. It removes the crewmate's worktree and its local and remote branch when the worktree is clean and the branch is at the merged head. It writes no plan: `jbus plan` counts an entry's status from its queue rows. It needs `gh` and `git`.

It prints one line per open pull request, and appends the lines to `merge.log`. It logs a `wait` or `hold` line that repeats from run to run once.

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", ..., revert: gh pr revert <url>` | Merged. The notes between say what was kept, that a review carried over (`review carried over: range-diff ... clean`), that a local check stood in (`fresh: <command> passed on <head12> over <main12>`), or the guarded path it changes (`guarded: <path>`). The last note is the command that opens a pull request reverting the merge. |
| `wait <number> <url>: <reason>` | Not merged. The reason is the first thing the pull request is short of. A later run merges it once the reason is gone. |
| `hold <number> <url>: needs <user>, <why>` | Not merged, and never by a plain `jmerge`. It is yours to accept. |
| `ready <number> <head> <branch> <slug>` | With `--check`: what a run would merge. |
| `wait: could not ask GitHub: gh exited <code>: <what gh said>` | GitHub did not give the open pull requests or the default branch. The line ends on `gh`'s exit code and the first line of its stderr (`it said nothing` where it had none). A `gh` that exited 0 with output that is not JSON says `gh exited 0: its output was not JSON`, and one that named no default branch says `gh exited 0: it named no default branch`. A token and the query of a URL are cut from the text, and it is at most 160 characters. The same text ends the sweep's `could not ask GitHub about its pull request` and the `could not ask GitHub whether a pull request is based on it` that keeps a branch. |

A pull request that waits is not a failure. `jmerge` exits non-zero when it could not do its job: outside a git repository, with no `gh`, when GitHub could not be asked, or when it refuses an `--accept`.

## What ready means

Each item below is a reason a pull request waits. `jmerge` prints one reason for a pull request. `Repo.waits` in `src/jmerge/cli.py` has their order. "Protected and guarded paths" adds a hold and a stricter gate.

- **A draft waits.** A draft is never merged, with any flag: `wait <number> <url>: draft`.
- **A brief names it.** A brief's Result has the pull request on its `Branch:` line. A brief that belongs to another home of the repo waits as `another home's`, unless `--all` is given.
- **Its base is the default branch.** A pull request based on another branch is never merged, and one whose brief has a `Stack:` line only with `--land <stack>`.
- **The review is done.** The brief has a `## Review` section with a verdict. After findings, the Result has a `Fixed:` line that names the head or says `none needed`. A `Second pass: needed since <head>` line waits for a review of a later head, and for a `Finding:` line for every finding. A brief that says `Review: none` waits with `its brief says Review: none, so it needs the user's word`.
- **The required check passed, and GitHub says it merges.** Green is the check named `check`, passed at the head, whatever the other checks say: `check has not passed`. A conflict is `it conflicts with its base`.
- **Its queue row lets it merge.** `jmerge` reads the `queue.json` of the jbus project whose checkout this is (`src/jmerge/rows.py`), once a run, and looks up the row whose slug is the brief's. A row `jbus queue hold` took the go from waits as `its queue row is held: approve it again to let it merge`: hold stops a merge as it stops a launch, and `--accept` does not lift it. A row that names others in `merge_after` waits as `merges after <slug> (#<n>), not merged yet` for the first of them that is not `merged` or `done`; it is judged on the next run after the one in which that pull request merges. A queue that is there and cannot be read leaves every pull request waiting, `its queue cannot be read, so its holds and merge order are not known`. A repo with no jbus config, or that no project names, has no queue and no such wait. These come after the review and rebase gates, so a pull request shows what it is short of first, and before the fresh check, so one that must wait never takes its single place.
- **Its migration is the next in line.** See "Migrations".
- **Its green covers today's main.** See "Fresh against main".
- **Its rebase kept every line.** See "After a rebase".
- **The repo's merge is on.** With `~/.local/state/home/<repo>/merge-off` there, `jmerge` merges nothing. A pull request that would have merged waits with `auto-merge is off for this repo`. `/nohome merge` makes the file and `/nohome merge on` removes it.

Before a merge, `jmerge` asks `git ls-remote` whether main is the commit the pull request was judged against, when the start of its check is known. Where main moved, `jmerge` judges the pull request again, at most twice, before it prints `main moved while it was judged`.

## Migrations

A numbered migration takes its number when the branch is cut and needs it when the branch lands, so two pull requests that were ready together take the same next number, and the one that merges second breaks main or needs a hand renumber. A repo that sets `migrations = "db/migrations"` in its project table in `~/.config/jbus/config.toml` ([Configuration](configuration.md#jbus)) has `jmerge` give the number at merge time. A pull request adds a migration when GitHub lists a file it adds directly in that directory. `0005_insulin.up.sql` and `0005_insulin.down.sql` are one migration, `0005_insulin`. A repo with no `migrations` key, and a pull request that adds none, is held for nothing here.

- **They merge in the repo's declared order.** The migration pull requests are judged in the order of `merge_after` in the queue (a row after the rows it names, also through a row that has no migration), and where no order is declared the older pull request first. `jmerge --check` shows them in that order, with one `ready` and the others waiting.
- **One is let through in a run.** The first migration pull request that is short of nothing else is let through; a second one that is ready waits as `it adds a migration, and #<n>, which merges before it, is merging`, since the merge changes the numbers the others are judged by. It is judged again on the next run. A pull request that adds no migration is not held.
- **One that is being rebased holds those behind it.** A migration pull request whose own reason to wait is that it conflicts with its base or with today's main, or that its number is taken, holds a ready one behind it in the order: `it adds a migration, and #<n>, which merges before it, is being rebased`. One that waits on anything else (a draft, no brief, another home's, a review) holds none behind it, since nobody is told to rebase it. One ahead of it in the order is never held by one behind it.
- **A taken number is renumbered by its crew.** After a fetch, `jmerge` reads the numbers of the default branch's migration directory. A migration whose number is there waits as `its migration <name> takes number <n>, which main has: renumber it to <free>`, where `<free>` is one more than the highest number main has, with as many digits as the migration has. `jbus` tells the crew the third pass it says the same (`renumber` in `src/jbus/expedite.py`): rebase with the crew skill's "A conflict" block run with `stale`, renumber the migration the reason names to the number it gives and each migration of the pull request after it to the numbers that follow, one each and in their order (files and every reference to an old number), and push. That rebase is counted like any other after fixed and green, so a third is held (`REBASE_HELD`) and its gate asks the user. The renumbered head is judged again, and the content change goes to the scoped review that "After a rebase" describes.
- **A repo can name its migrations by timestamp instead.** With `migration_names = "timestamped"` the names cannot collide and the check of the number is skipped. The pull requests still merge one at a time, in the same order.

Each reason is a constant of `src/jmerge/ready.py` (`MIGRATION_TAKEN`, `MIGRATION_MERGING`, `MIGRATION_REBASING`) with a rule in `merge.RULES`: the taken number is on the `rebase` step, and the two waits on another pull request are on `check`.

## Fresh against main

The check's start is the earliest start of the runs named `check` at the head. After a `git fetch` in the main checkout, `jmerge` lists the paths the first-parent commits of the default branch changed since then. A pull request waits when one of those paths is its own, is a CI path in `src/jmerge/ci-paths.txt` (`.github/workflows/`, `/pyproject.toml`, `/uv.lock`, `/Makefile`), or is a caller of its files or something they depend on. That last is read from the files, at the tip for main's and at the head for its own: one imports the other, Python's way, by the file's dotted path or any tail of it (a `conftest.py` counts for every Python file under its directory), or names the other's path where that path has a `/` in it:

```
wait <number> <url>: main changed <up to five paths, then "and <k> more"> after its check started at <HH:MM> <zone>; it needs a fresh check
```

`main` there is the name of the base branch. A main that moved only on other paths, none of them a caller or a dependency, leaves the check standing, and nothing is rebased for it.

A repo opts in to a local check with a `fresh-check` file in its state directory: one line, the command, such as `make check`. `jmerge` merges the head over today's main with `git merge-tree`, starts the check, and goes on: the line says `a fresh check is queued`. The check runs outside the run that started it, in a transient user unit `jmerge-fresh-<repo>-<number>` (`systemd-run --user`; `journalctl --user -u` it), or, run outside any systemd unit where systemd cannot start one, as a process in a session of its own. Inside a unit, where such a process would end with it, the line is `a fresh check could not be run (<what systemd-run said>)`. It holds `<state>/fresh.lock` for as long as it runs, runs the command in a worktree at `<state>/fresh/<number>` with a 15-minute limit, removes the worktree, and keeps the result in `<state>/fresh.json`, where the next run reads it. It never touches the crewmate's branch or worktree. A pass is said on the `ready` and `merged` lines. A pass is also the one thing it pushes: the merge that passed goes to `refs/jstack/green-tree/<tree>` on the origin, named for that merge's tree, before the pass is said. The merge that lands has the same tree, so the job `full` of main's run of the check finds the marker, runs `uv sync --locked`, and skips `make check`. A pull request's own job, `check`, runs `make check-fast BASE=HEAD^1`, the lint and the tests its change reaches, and leaves no marker: a marker says the full suite passed a tree. A marker that could not be pushed leaves the pass standing, and the note ends `, its tree is not marked (<why>)`. A fail is `wait <number> <url>: <command> fails on <head12> over today's main <main12>`. A command still running at the limit is stopped, and that says nothing of the tree, since the limit counts the wait for a test slot too: it is recorded as `timed out`, the line is `a fresh check is queued`, and the next run starts the check again. It is never a rebase. A head that does not merge there is `it conflicts with today's main`, and a command that could not start is `a fresh check could not be run (<why>)`. One run of `jmerge` starts one check, and none while another holds the lock: the other pull requests wait with `a fresh check is queued`. `--check` starts none. A jmerge that jbus stops leaves the check running to its end. The three limits keep that order: the check's own 15 minutes (`Fresh.TIMEOUT`), the 17 minutes a jbus pass allows `jmerge` (`JMERGE_TIMEOUT` in `src/jbus/wake.py`), and the unit's `TimeoutStartSec=20min`, and `tests/test_jbus.py` fails if they are reordered.

The check runs every test, and a change needs fewer: `python3 scripts/select_tests.py <base> <head>` prints the test files a diff needs, one per line, or `all`. It reads `git diff --name-only --no-renames <base> <head>`, where `<base>` is where the pull request left main or the parent of its merge commit, and the imports of the tree: a changed module selects the tests that import it, through any chain of modules, and a changed file that is no module selects the tests that spell its path. The map in `.cursor/skills/verify-jstack/features/` adds to it: each feature file names the paths it owns (`Paths:`) and the tests that read them in a way no import shows (`Tests:`), and the map's README names the test files that read the whole tree (`Cross-cutting:`), which every diff runs. An edit to a feature file selects that feature's tests, not `all`. Only `pyproject.toml`, `uv.lock`, `tests/conftest.py`, a test module that `tests/conftest.py` loads for every test, and a fixture no test names select `all`. It needs no package, so it runs before `uv sync`, and the same two commits give the same lines. When `$GITHUB_STEP_SUMMARY` is set it adds one line to it, `check-fast selection=<all|some> files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n> forced-by=<path or ->`: a collector reads the choice of every run from that line. A test module that marks itself `browser` is never printed: `make check-browser` runs it nightly and on a release. A test the selection missed fails the `full` job on main after the merge. `tests/test_select_tests.py` fails when a path is owned by no feature, or a test file is selected by no change.

## After a rebase

A crewmate writes nothing of its rebase. `jmerge` compares the head it finds with the commit the review covers: the `Fixed:` commit, or with none the head the last `## Review` saw. The files it reads are the ones either patch changes. A brief from before this rule may still say what its rebase did: `Rebase: patch unchanged, before <commit>, head <commit>`, or `Rebase: patch changed in <files>, before <commit>, head <commit>`. Such a line is read as it was: for `patch unchanged`, `jmerge` works out both patch-ids again from the two commits.

For a patch that changed, `jmerge` counts the lines main added to those files and the lines the pull request added before the rebase, and looks for each in the head. With none lost, `git range-diff` between the head the review saw and the rebased head decides whether the review stands:

- **A clean range-diff carries the review over.** The `ready` and `merged` lines say `review carried over: range-diff <old> <new> clean, every line kept`.
- **A range-diff with a content change waits for one scoped review.** The line is `the rebase changed the content after its review; scoped review of git range-diff --no-color <old> <new>`. `jmerge` merges once a `## Review` names the rebased head. A range-diff that cannot run counts as a content change.

A lost line waits for its crewmate: `the rebase dropped <k> of main's lines in <file> ... with no Dropped on rebase line at <head12>`. The crewmate puts the lines back, or adds `Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>` to its Result. The scoped review then rules on each such file with a `Drops: upheld <files>` or `Drops: not upheld <file>: <why>` line. Until a review covers that head, the pull request waits with `the scoped review has not ruled on the drops in <files>`. Two outcomes are yours. A drop the review does not uphold is `hold <number> <url>: needs <user>, the review did not uphold the drop in <file>: <why>`. A review of that head that rules on no drop of a file is `hold <number> <url>: needs <user>, the review of <head12> did not rule on the drops in <files>`.

A push that fixes a failed check after the review is read the same way. The crewmate adds `CI fix: <new head>, after the review of <reviewed head>` to its Result, and `jmerge` compares the two heads by `git range-diff`.

## Protected and guarded paths

`jmerge` reads three lists from its own package directory, never from a pull request. Each has one pattern per line and `#` for a comment. A pattern that ends in `/` is a directory. Any other pattern is a file: a name at any depth, or with a `/` in it the whole path from the root. `jmerge` merges nothing and exits non-zero while a list is missing or has a pattern it cannot read, such as `**` or a leading `!`.

**Protected paths** are in `src/jmerge/protected.txt`: `secrets/`, `.env`, `.env.*`, `*.pem`, `*.key`, the files `protected.txt` and `guarded.txt` themselves, and the directories `/policy/` and `/dns/` at the root of a repo, where a change applies to the live tailnet policy or DNS records. A pull request that changes one is printed as `hold <number> <url>: needs <user>, touches <first matching path>`. So is one whose file list GitHub cut short.

**Guarded paths** are in `src/jmerge/guarded.txt`: `acceptance/`, `.github/workflows/`, `src/jmerge/`, `src/jbus/` and `skills/`. `jmerge` merges a pull request that changes one under a stricter gate, and prints a part that does not hold as `wait <number> <url>: guarded (touches <first guarded path>), <reason>`:

- **A check with a start time.** `check` passed at the head, and the time its earliest run started there is known: `its check has no start time`.
- **A finished review of that head.** Every finding has its `Finding:` line. The head is the one the review saw, the `Fixed:` commit, a head the review carried over to, or in a brief from before the head of a `Rebase: patch unchanged` line whose patch-ids match: `its head is not the one its review saw`.
- **A rebase, and no local check.** Where main changed one of its paths, a CI path, or a caller or a dependency of its files since the check started, a guarded pull request gets no `fresh-check` run. Its line ends `it needs a rebase`.
- **A proven safety fact.** The review proved the one fact the change is safe because of, at the commit it saw. That is the `Proof:` line of the `## Review` section: a command that ended `exit 0`. A proof carries over a rebase, or a `CI fix:` push, whose range-diff is clean. It does not carry over a fix pushed for the review's findings. Otherwise the reason is `no proven safety fact at <commit12> (blast-radius, review step 5)`.
- **Rules that are main's.** Before it judges a guarded pull request, `jmerge` fetches the checkout that holds its own package. It goes on only if the package there has no uncommitted change and matches the default branch of `origin`. It pulls a checkout that is behind, and guarded pull requests wait for the next run: `jmerge pulled main's rules; judged on the next run`. After a merge that changes `src/jmerge/`, every later guarded pull request of that run waits: `jmerge's rules changed in this run`.

## Accept a held pull request

`jmerge --accept` is the hand-merge of a pull request `jmerge` holds. Never run `gh pr merge` by hand.

```sh
jmerge --accept <number> --by <user> --at "YYYY-MM-DD HH:MM <zone>"
```

`<zone>` is your `timezone_label`, or the word your time zone prints, such as `CEST`. [Configuration](configuration.md#jstack) has both keys.

It lifts the hold at the head the hold was said at, which `jmerge` keeps in `holds.json` in the state directory. It refuses a pull request that is not held, one whose head is not the head on record, and one with no proven safety fact at that head. `--by` takes the `user` of `~/.config/jstack/config.toml` and nothing else, which is `user` where that file names none. It writes an `accepted` line with who and when to `merge.log`, and then judges the pull request as any other: the guarded gate and `merge-off` apply. `jmerge --accept <number> --check` says what it would do.

## Arguments

| Argument | What it does |
|---|---|
| `--check` | Prints `ready` lines in place of merging. It merges nothing, logs nothing and runs no `fresh-check` command. |
| `--accept <number>` | Lifts the hold of one pull request and merges it, with `--by` and `--at`. |
| `--sweep` | Merges nothing. It removes what each finished thread left once its work is all merged or pushed: the worktree and the branches. It also deletes each `refs/jstack/green-tree/<tree>` marker on the origin whose commit is more than 7 days old. It prints what it removed and what it kept. With `--check` it prints what is removable and removes nothing. |
| `--claims` | Changes nothing. It prints one line per brief that still holds files, with its state, its home and its `Where:` line. |
| `--home <id>` | The home that is asking. Defaults to the id in the state directory's `home-id`. |
| `--all` | Merges the pull requests of the repo's other homes too. |
| `--land <stack>` | Merges the pull requests of a stack you said to land, each once its base is the default branch. |

`jmerge` ends most of the `git` and `gh` commands it runs after 120 seconds, or `JMERGE_TIMEOUT` seconds when that is set, and counts such a command as failed. The commands of a `git range-diff` have 60 seconds each, whatever the variable says.
