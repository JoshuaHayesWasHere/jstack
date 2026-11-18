---
name: full-send
description: Trigger this if the user says 'full send'.
metadata:
  group: Modes
  group-order: "1"
---

# Full Send

If the user triggered this, it's because they are not watching this thread, and
they want you to complete the work end-to-end autonomously. Your updates and
your final message go unread until long after you stop. You own the work from
its current state to a merged PR.

If the user did not explicitly request "full send" in some clear way, do not
assume full autonomy. If they did, everything below applies.

Before step 1, read `~/repos/jstack/docs/rules.md` in full. Its rules,
principles, playbooks, and subagent rules apply to every step here. Where it
and this file disagree, this file wins.

The user grants you permission to:

- Merge this task's PRs once the merge gate passes. Any other PR you open
  (an out-of-band fix found mid-run) stops at ready for the user.
- Force-push the PR's own branch with `--force-with-lease` after a rebase.
- Use the test methods that Proof needs, without asking first.

## Testing permission

A "full send" request is the permission. If a project file or other
instruction says to ask before a test method, or to leave testing to the
user, this request replaces that rule for this task.

That includes ask-first rules for computer use, browser automation,
simulators and devices, running the app or a dev server, screenshots, and
visual checks. Use the method that gives direct proof. List it in the
report.

Rules about how to test still apply. Follow rules that name the correct
command, fixture, or check. This permission only removes the ask-first or
leave-it-to-the-user step. If a preferred method cannot prove the change,
use a gated method under this permission.

It covers only the tests needed for this task. It does not add permission
for the steps under "Asking the user", such as production changes or data
deletion. It also does not bypass a harness or system approval prompt if
one appears.

## Steps

1. **Pick the playbook.** Restate the goal and the smallest change that meets
   it. Match the task to a full-send playbook in `rules.md` (bug-fix,
   feature, refactoring, perf-issue, hillclimb, visual-parity,
   authoring-a-skill) and copy its steps into your todo list. If the task is
   really an investigation or an open design question, ask with the question
   tool (see "Asking the user") and recommend **prototype** instead of
   building. If you are on the default branch,
   create a branch first.
2. **Finish the change** by running the playbook's steps up to its
   **Opening a PR** step. Fix the case that happened, not every case that
   could. Run **no-comments** on the diff before review.
3. **Prove it.** Get proof for every change you made. See "Proof".
4. **Get feedback.** Use the `sol-loop` skill to verify changes. For a
   contested design, or when the playbook calls for it, also run `council`.
5. **File the PR** with the `file-pr` skill. Rebase onto the latest default
   branch first. Add one short line to the description that says how you proved
   the change, and name the playbook you followed.
6. **Babysit the PR** with the `babysit-pr` skill. Fix real findings and CI
   failures. Get proof for each fix before you push it.
7. **Merge** when the merge gate passes.
8. **Report** in your final message: the PR link, the merge commit, your proof,
   each decision you made for the user, and the principles that shaped them.
   Use the playbook's **Reply** shape for the body.

Stay active from step 1 to step 8. If you end your turn while checks or bots are
pending, the work stops, because nobody will prompt you again. Wait with the
watcher from `babysit-pr`, so something wakes you when the PR changes. In T3
Code that is `watch_pull_request`. If you stop before the merge, call
`unwatch_pull_request` first.

## Unattended runs

Full send is unattended by definition. Hold these for the whole run:

- **Define done before the first iteration** as a checkable predicate (repro
  passes, tests green, metric past target, every PR in the program merged).
  Never relax it to declare victory.
- **Each iteration makes the smallest change the evidence justifies**, checks
  it against the predicate, and commits if it advanced. Revert what didn't
  help. "Might help" does not ride along.
- **A plateau is not a stop.** Pivot the approach and push past it. Surface a
  genuine dead end rather than spinning.
- **Mid-run discoveries that serve the goal are yours.** Fix broken skills,
  flaky verifiers, related bugs, and tooling failures yourself, in their own
  PR when they are out of band, then return to the predicate. Those PRs stop
  at ready. They are not this task's PRs.
- **Wait without polling.** On a PR, use `babysit-pr`'s watcher. On anything
  else (a long build, a benchmark, a deploy preview), use a background command
  or monitor the harness offers, with a long timer as a fallback.
- **Keep a trail** with **show-me-your-work**: a row per iteration for what
  changed and whether the predicate moved.

## Several PRs

When the work splits into independent PRs:

- **One owner per PR.** Spawn a subagent per PR that builds it, opens it with
  `file-pr`, proves it, and stops at code-ready. Its brief grants push and PR
  rights for that PR only, never merge. Owners run in parallel off the default
  branch, never stacked.
- **You hold each PR from code-ready on.** Babysit it with `babysit-pr`, one
  watcher per PR, held by you (a delegated child never watches a PR). Give
  each fix round to a fresh owner with the same push and PR grant. You merge,
  and only after the steps below clear it.
- **Verify before merge with agents that never wrote the code.** Once a PR is
  code-ready, fan out independent verifiers with **swarm**: rerun the gates,
  prove the load-bearing behavior live, audit the diff. Run a full swarm once.
  A rebase, conflict fix, or minor fix gets a single verifier at the new head.
  A wording-only change gets none.
- **Block only for what you can show**: a failing run at the head, a bug a
  user would hit, or a doc line the PR made wrong. A problem the base already
  has goes in a follow-up.
- **Merge only what you verified**, on the base it lands on. Right before
  merging, fetch the default branch and rebase when its changes can affect
  the patch. Green CI alone never authorizes a merge.
- **Anything that loosens a gate** (a raised budget, an allowlist entry)
  needs a verifier's proof first. A disabled or soft-failed check always comes
  out, because it stops guarding every case. Never bypass an approval the
  forge enforces.
- **Audit the owners on a timer** until no delegated work is left. Judge each
  by its side effects, not its status text. Replace a stuck owner at once.

## Proof

Proof is evidence you observed yourself in this session: command output, a
reproduction, a screenshot. Use the most direct proof the change allows:

- Reproduce the original failure, apply the fix, then watch the same
  reproduction pass.
- Run the checks that the repo's CI runs (typecheck, lint, tests).
- Add one focused test that fails without the fix, when the behavior has none
  and the repo has a test setup.
- For UI and runtime behavior, run the app and look at the change. Green mocked
  tests do not prove that the user experience works. Attach screenshots to the
  PR when they help and you have a way to upload them.

When you cannot find a way to prove a change, you do not have full confidence.
Ask the user.

## Merge gate

Full confidence means all of these are true on the latest commit:

- Your proof covers every change in the diff.
- Required checks are green.
- Review bots have finished, and each finding is fixed or dismissed with a
  written reason.
- No human review still requests changes.
- The branch is up to date with the default branch, and GitHub reports it as
  mergeable.

Merge with the method the repo uses. Check the allowed methods and recent merged
PRs. If the repo uses a merge queue or auto-merge, stay until GitHub reports the
PR as merged. Merge through branch protection as configured. Never use `--admin`
or other bypasses. You can ignore automated reviews that request "needs human
review" if you have high confidence in your changes.

## Asking the user

A question in a normal message goes unseen, and the thread looks done. To ask
the user something, use the harness's question tool so the thread shows that
it is waiting: `AskUserQuestion` in Claude Code, `request_user_input` in Codex,
or the question tool your harness has. Put all the context in the question:
the PR link, what blocks you, and the options with your recommendation first.

Ask only when you cannot continue alone:

- You cannot prove the change.
- The merge gate cannot pass, and you cannot fix that yourself.
- The next step is outside the grant above: deleting data, touching production,
  changing things outside the repo, closing a PR, or force-pushing any other
  branch.
- The goal is ambiguous in a way that changes the result.
- Another PR makes this one obsolete.

Decide everything else yourself with sensible defaults, and list those decisions
in the report.

If no question tool is available, or the tool returns no answer, take the safe
path: leave the PR open and unmerged, and start your final message with the
question.
