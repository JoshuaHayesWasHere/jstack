---
name: correct
description: Find the mistakes agents keep repeating in a repo and make each one impossible - structure first, then types, then a test, and a written rule last - and prove each check fails on a real past mistake. Runs only when the user types /correct or $correct, or a brief names it.
tip: makes a mistake agents keep repeating impossible | same mistake again | keeps making the same mistake | keep making the same mistake | made this mistake before
disable-model-invocation: true
card: "Make the lesson stick | 1 | Finds the mistakes agents keep repeating in a repo and makes each one impossible: structure first, then types, then a test, a written rule last. Each check is proven to fail on a real past mistake. | Reach for it when the same correction has been given twice. | op: the operator; plain: a brief with the `correct` playbook"
---

# correct

The user keeps correcting agents in this repo for the same mistakes. Change the repo so the next agent cannot make them.

Assume every contributor is an agent that sees only the files it opened, copies the nearest example, and takes the shortest path that passes. Design the repo so a change that looks right from one file is right for the whole repo.

Who is reading decides how far this goes:

- A **home** (the user typed `/correct` in it) finds the classes and picks the level for each, and stops there.
  It writes no code: each class becomes a proposed plan entry, put to the user, and a class the user takes is handed out as a brief that names `features/lessons/skills/correct/playbooks/correct.md`.
- A **crewmate** whose brief names this skill or that playbook does one correction, the class the brief names, start to finish. The playbook holds its steps.
- An ordinary thread (no home for the repo) does both, on a branch.

A path such as `features/lessons/skills/correct/playbooks/correct.md` or `principles/<name>.md` is from the root of the repo this skill lives in: `realpath ~/.claude/skills/correct/../..`.

## Find the mistake classes

Read where corrections are written down. This prints the first two sources, for the repo the thread is in:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
echo "## commits that fix or revert"
git log -n 300 -i -E --grep='^(revert|fix)' --format='%h %s' | head -n 60
echo "## steers, things noticed and review findings in the briefs"
grep -HE '^(Steers:|Noticed:|- (error|warning|info) )' "$H"/tasks/*.md 2> /dev/null |
    grep -vE ':(Steers|Noticed): none$' | sed "s|^$H/tasks/||" | head -n 120
```

A `Steers:` line is the user correcting a crewmate.
A finding line is a reviewer correcting one.
Then read the rest: the repo's `$H/standing.md` (a standing rule there is a correction the user gave, and one with nothing enforcing it is a candidate), its `CLAUDE.md` or `AGENTS.md`, and the comments in the code that explain a workaround.
In a repo with no home, the second list is empty: the commits, the pull request reviews (`gh pr list --state merged`, `gh pr view <n> --comments`) and the instruction files are the sources.

Group the mistakes into classes. A class counts once it has happened twice. Once is a one-off: leave it.

## Fix each class at the highest level that works

Take the levels in this order, and take a lower one only when you can say why the one above does not work (`principles/principle-encode-lessons-in-structure.md`).

1. **Structure.** Give each piece of state one owner and each task one supported way. Hide internals so the wrong import fails. Replace lists kept in step by hand with one source of truth. Delete the old way and the dead code an agent would copy (`principles/principle-subtract-before-you-add.md`). In a skill, the same move is a rule that became a shell block the reader runs, or a script that does the step with no model.
2. **Types.** Make the bad state one that cannot be written (`principles/principle-type-system-discipline.md`). If the bad code still passes, add a lint or a check to the repo's check command whose error names the file, type or function to use in its place. If the pattern is already common, fail only when a change adds more.
3. **A test.** Test the behaviour (`principles/principle-test-behavior-not-implementation.md`). A test executes something: fix or delete any test that still passes when the behavior it checks breaks, or that fails when only the internals change, and any that only finds sentences in a file.
4. **A written rule, last, and only for a judgment call.** Nothing fails when an agent skips it.

## Where each lands in this flow

- Levels 1 to 3 are a change to the repo: a check or a test in it, run by its check command, locally and in CI. It goes the way every change goes: a brief, a crewmate, a pull request, one review. Nobody edits the default branch to "just add the check".
- Level 4 is a queued row that codes the rule: a brief that turns the judgment call into a check, a block or a skill's text, which the home queues with `jbus queue add`, as `standing.md` already says of a standing rule.
  A crewmate gives that row's task in its Result under "Noticed", for the home to queue.
  No rule is a line in a file of the home's state, and none goes in `~/.claude/CLAUDE.md`: that file is about the machine and stays short.
- A class that is too big for one pull request, or that needs the user's word, is a plan entry: a heading, what holds when it is done, and the evidence, in the shape of `templates/plan-entry.md`. The home proposes it and the user decides.

There is no rule table.
When the user corrects you, fix the mistake and code the rule at the highest level that works.
A rule written down with nothing enforcing it is a repeat waiting to happen: code it in the same change.

## Fix and prove

Fix the most frequent classes first, one pull request each. Prove each new check fails on a real past mistake: put the mistake back (the reverted commit's change, the line the reviewer flagged), see the check fail with an error that names the fix, undo it, and say in the pull request which break was used (`principles/principle-prove-it-works.md`). An exception goes on the offending line with a reason and the user's approval, never in a list somewhere else.

## What comes back

For each class: its evidence (the commits, steers or findings, at least two), the level picked, and why no higher level works. Then where it landed or should land: the pull request, the queued row, or the proposed plan entry.
