# Third-party material

jstack's own license is in `LICENSE`. This file credits what was taken from others.

## pstack

The files in `principles/` are adapted from the principle skills of pstack, by Lauren Tan.

- Source: https://github.com/cursor/plugins/tree/main/pstack
- Commit: 1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def
- Taken from: `pstack/skills/principle-<name>/SKILL.md`, one file per principle
- Changed here: the frontmatter is gone and its description is the first paragraph, links between principles point at the files in this directory, and pointers to pstack skills that are not in this repo are dropped or reworded.
- Also covered, from the same commit: the six files in `playbooks/` (`authoring-a-skill.md`, `bug-fix.md`, `feature.md`, `investigation.md`, `opening-a-pr.md`, `refactoring.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout, with `bug-fix.md` also drawing on `pstack/skills/tdd/SKILL.md` and `investigation.md` on `pstack/skills/how/SKILL.md` and `pstack/skills/why/SKILL.md`.
- Also covered, from the same commit: `skills/unslop/SKILL.md` and `skills/technical-writing/SKILL.md`, each taken whole from `pstack/skills/<name>/SKILL.md`. Changed here: each has a `tip:` line for `hooks/skill-tips.sh`, unslop's description says when it loads, and technical-writing names `templates/pr-body.md` and says where it is.
- Also covered, from the same commit: the things to look for under the fourth and fifth questions of the review, in the `SCOPE` text of `skills/pr-review/SKILL.md`, shortened from `pstack/skills/interrogate/references/rubric.md` and the dimensions of `pstack/skills/interrogate/references/code-quality-review.md`; and the two endings of a finding in `skills/crew/SKILL.md` "The review", which stand in for the four buckets of `pstack/skills/interrogate/references/lead-judgment.md`.
- Also covered, from the same commit: `skills/correct/SKILL.md` and `playbooks/correct.md` (the playbook file `correct.md`), adapted from `pstack/skills/correct/SKILL.md`, and `skills/reflect/SKILL.md` with the four prompts in `skills/reflect/references/`, adapted from `pstack/skills/reflect/` and its `references/`, both rewritten for Claude Code and this repo's home, crewmate and brief.
- Also covered, from the same commit: `playbooks/authoring-a-playbook.md` (the playbook file `authoring-a-playbook.md`), drawn from the phases of `pstack/skills/figure-it-out/SKILL.md` (a falsifiable definition of done, the check built before the work, the riskiest unknown first, each unit an experiment, a recurring correction encoded as a check or a script) and narrowed from designing a workflow for one task to writing a playbook for a kind of task. The `skip: <reason>` rule that every playbook carries is from `pstack/skills/poteto-mode/SKILL.md`.
- Also covered, from the same commit: five more files in `playbooks/` (the playbook files `prototype.md`, `pause-safely.md`, `trace-forensics.md`, `runtime-forensics.md` and `visual-parity.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout: the reply became the brief's Result or the scout's report, the control skill became the repo's verify skill where it has one, and the delegate on a named model, `/loop` and the throughput checkpoint are gone.
- Also covered, from the same commit: three more files in `playbooks/` (the playbook files `perf-issue.md`, `hillclimb.md` and `autonomous-run.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate, and the two skills they lean on, `skills/show-me-your-work/SKILL.md` with `scripts/log.sh` and `skills/benchmark-checklist/SKILL.md`, each adapted from `pstack/skills/<name>/`. Changed here: the delegate on a named model, `/loop`, the stack of pull requests and the review of the log by a second model are gone; the log lives in the worktree's git directory and has the same six columns for every playbook; `scripts/runs.sh` of the benchmark skill is new, and takes the runs that its fifth question asks for.
- Also covered, from the same commit: `skills/how/SKILL.md`, `skills/why/SKILL.md`, `skills/teach/SKILL.md`, `skills/blast-radius/SKILL.md`, `skills/recall/SKILL.md`, `skills/ketchup/SKILL.md`, `skills/bro/SKILL.md` and `skills/automate-me/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, with the files in `skills/how/references/` and `skills/why/references/` taken whole from the same directories but for one sentence in `sources/slack.md`. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, Cursor's tools and paths are Claude Code's, `recall` and `ketchup` read the home's record and its gates, and each skill loads only when typed.
- Also covered, from the same commit: three more files in `playbooks/` (the playbook files `swarm.md`, `arena.md` and `eval.md`), the first two adapted from `pstack/skills/swarm/SKILL.md` and `pstack/skills/arena/SKILL.md`, which are skills in the source and playbooks here, and the third from `pstack/skills/poteto-mode/playbooks/eval.md`, all rewritten for this repo's crewmate. Changed here: a worker, runner, candidate or judge is a local subagent, ten at most in a step; the cloud workers, the model per seat (but for `eval`, whose brief names its models) and the raised effort are gone; `arena` has the reader score both candidates before the judge is started; `eval` takes its models from the brief, keeps the key from a directory to its model in one file, and reads a candidate's transcript with the blocks of `skills/reflect/SKILL.md`.
- Also covered, from the same commit: four more files in `playbooks/` (the playbook files `orchestrate.md`, `multi-phase-plan.md`, `autopilot-full.md` and `session-pickup.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's home, which reads only its state directory, launches threads and merges with `jmerge`. Changed here: the coordinator's store, ledger and inbox are the state directory, a brief's Result and Review and the home's gates; an owner is a crewmate, the verdict its one reviewer's and the merge `jmerge`'s; the hourly tick is a scheduled run of T3 Code in place of `/loop`, and a thread is picked up by a message or a launch on its worktree in place of a transcript; "state the plan, then wait for the operator's go" is the plan the user approved; and the sub-coordinators, the cloud workers, the verifier on another model family, the ten live lanes, the stack and its stacker, and `orch` are gone.
- Also covered, from the same commit: `skills/architect/SKILL.md`, `skills/interrogate/SKILL.md`, `skills/tdd/SKILL.md`, `skills/no-comments/SKILL.md` and `skills/typescript-best-practices/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, and `skills/no-comments/SKILL.md` also from `pstack/agents/comment-sicko.md`. The files in `skills/architect/references/`, `skills/interrogate/references/` and `skills/typescript-best-practices/references/` are from the same directories: `design-red-flags.md` whole, `patterns.md` whole but for two sentences that name a principle, the rest adapted. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, `architect` runs `playbooks/arena.md`, `tdd` runs `playbooks/bug-fix.md`, `interrogate` reads the checks that `skills/pr-review/SKILL.md` already holds from that file, the comment hunter reports and the thread deletes, and each skill loads only when typed.
- Also covered, from the same commit: two more files in `playbooks/` (the playbook files `autopilot-stack.md` and `shipping.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's home. Changed here: the root that rebases every link and pushes with `--force-with-lease` is a home that touches no branch, so each link's own crewmate rebases its own; the order of the stack is a `Stack:` line the home writes in each link's brief; a verdict is the one reviewer's, and a link is added only on one; the landing is `jmerge --land`, run on the user's word, for the one link whose base is the default branch; the patch-id of a verdict is the crewmate's `Rebase:` line; and the forge choice, Origin, the cloud agent per owner, Bugbot triage, the slop strip, the decision trails, auto-merge and the watch on the queue are gone.
- At this commit, which is version 0.15.20, these upstream changes are taken in part or not at all. #486 (de2dba6) renames the Comment Sicko agent to `comment-sicko`. This repo has no agent, and the hunter's prompt is inline in `skills/no-comments/SKILL.md`. #575 (2bd5dd4) makes the poteto-mode chat the runner and poteto-agent a delegate. Only the skip rule of `pstack/skills/poteto-mode/SKILL.md` is taken, because a home here runs its playbooks itself. #574 (cf9a111, worktree-audit), #536 (87c8103, check-plan), #484 (ff8f83d, watch-pr) and #576 (e5a02f8, the root `plugin.json`) change files that are not vendored. The cuts of #571 (08bd59b) in `babysit.md` and `worktree-cleanup.md`, and the change of #573 (c49b37a) to `pstack/skills/create-verification-skill`, are in paths on the `Not taken:` line below. `skills/ketchup/SKILL.md` has the before and after visuals of #570 (ea32d95) without the generated image, which this repo's threads have no tool for.

Files:

- `principles/attack-the-premise.md`
- `principles/boundary-discipline.md`
- `principles/build-the-lever.md`
- `principles/encode-lessons-in-structure.md`
- `principles/exhaust-the-design-space.md`
- `principles/experience-first.md`
- `principles/explain-the-number.md`
- `principles/fix-root-causes.md`
- `principles/foundational-thinking.md`
- `principles/guard-the-context-window.md`
- `principles/laziness-protocol.md`
- `principles/make-operations-idempotent.md`
- `principles/migrate-callers-then-delete-legacy-apis.md`
- `principles/minimize-reader-load.md`
- `principles/model-the-domain.md`
- `principles/never-block-on-the-human.md`
- `principles/outcome-oriented-execution.md`
- `principles/prove-it-works.md`
- `principles/redesign-from-first-principles.md`
- `principles/separate-before-serializing-shared-state.md`
- `principles/sequence-verifiable-units.md`
- `principles/subtract-before-you-add.md`
- `principles/test-behavior-not-implementation.md`
- `principles/type-system-discipline.md`

Upstream map:

```
playbooks/arena.md <- pstack/skills/arena/SKILL.md
playbooks/authoring-a-playbook.md <- pstack/skills/figure-it-out/SKILL.md, pstack/skills/poteto-mode/SKILL.md
playbooks/authoring-a-skill.md <- pstack/skills/poteto-mode/playbooks/authoring-a-skill.md
playbooks/autonomous-run.md <- pstack/skills/poteto-mode/playbooks/autonomous-run.md
playbooks/autopilot-full.md <- pstack/skills/poteto-mode/playbooks/autopilot-full.md
playbooks/autopilot-stack.md <- pstack/skills/poteto-mode/playbooks/autopilot-stack.md
playbooks/bug-fix.md <- pstack/skills/poteto-mode/playbooks/bug-fix.md, pstack/skills/tdd/SKILL.md
playbooks/correct.md <- pstack/skills/correct/SKILL.md
playbooks/eval.md <- pstack/skills/poteto-mode/playbooks/eval.md
playbooks/feature.md <- pstack/skills/poteto-mode/playbooks/feature.md
playbooks/hillclimb.md <- pstack/skills/poteto-mode/playbooks/hillclimb.md
playbooks/investigation.md <- pstack/skills/poteto-mode/playbooks/investigation.md, pstack/skills/how/SKILL.md, pstack/skills/why/SKILL.md
playbooks/multi-phase-plan.md <- pstack/skills/poteto-mode/playbooks/multi-phase-plan.md
playbooks/opening-a-pr.md <- pstack/skills/poteto-mode/playbooks/opening-a-pr.md
playbooks/orchestrate.md <- pstack/skills/poteto-mode/playbooks/orchestrate.md
playbooks/pause-safely.md <- pstack/skills/poteto-mode/playbooks/pause-safely.md
playbooks/perf-issue.md <- pstack/skills/poteto-mode/playbooks/perf-issue.md
playbooks/prototype.md <- pstack/skills/poteto-mode/playbooks/prototype.md
playbooks/refactoring.md <- pstack/skills/poteto-mode/playbooks/refactoring.md
playbooks/runtime-forensics.md <- pstack/skills/poteto-mode/playbooks/runtime-forensics.md
playbooks/session-pickup.md <- pstack/skills/poteto-mode/playbooks/session-pickup.md
playbooks/shipping.md <- pstack/skills/poteto-mode/playbooks/shipping.md
playbooks/swarm.md <- pstack/skills/swarm/SKILL.md
playbooks/trace-forensics.md <- pstack/skills/poteto-mode/playbooks/trace-forensics.md
playbooks/visual-parity.md <- pstack/skills/poteto-mode/playbooks/visual-parity.md
principles/attack-the-premise.md <- pstack/skills/principle-attack-the-premise/SKILL.md
principles/boundary-discipline.md <- pstack/skills/principle-boundary-discipline/SKILL.md
principles/build-the-lever.md <- pstack/skills/principle-build-the-lever/SKILL.md
principles/encode-lessons-in-structure.md <- pstack/skills/principle-encode-lessons-in-structure/SKILL.md
principles/exhaust-the-design-space.md <- pstack/skills/principle-exhaust-the-design-space/SKILL.md
principles/experience-first.md <- pstack/skills/principle-experience-first/SKILL.md
principles/explain-the-number.md <- pstack/skills/principle-explain-the-number/SKILL.md
principles/fix-root-causes.md <- pstack/skills/principle-fix-root-causes/SKILL.md
principles/foundational-thinking.md <- pstack/skills/principle-foundational-thinking/SKILL.md
principles/guard-the-context-window.md <- pstack/skills/principle-guard-the-context-window/SKILL.md
principles/laziness-protocol.md <- pstack/skills/principle-laziness-protocol/SKILL.md
principles/make-operations-idempotent.md <- pstack/skills/principle-make-operations-idempotent/SKILL.md
principles/migrate-callers-then-delete-legacy-apis.md <- pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md
principles/minimize-reader-load.md <- pstack/skills/principle-minimize-reader-load/SKILL.md
principles/model-the-domain.md <- pstack/skills/principle-model-the-domain/SKILL.md
principles/never-block-on-the-human.md <- pstack/skills/principle-never-block-on-the-human/SKILL.md
principles/outcome-oriented-execution.md <- pstack/skills/principle-outcome-oriented-execution/SKILL.md
principles/prove-it-works.md <- pstack/skills/principle-prove-it-works/SKILL.md
principles/redesign-from-first-principles.md <- pstack/skills/principle-redesign-from-first-principles/SKILL.md
principles/separate-before-serializing-shared-state.md <- pstack/skills/principle-separate-before-serializing-shared-state/SKILL.md
principles/sequence-verifiable-units.md <- pstack/skills/principle-sequence-verifiable-units/SKILL.md
principles/subtract-before-you-add.md <- pstack/skills/principle-subtract-before-you-add/SKILL.md
principles/test-behavior-not-implementation.md <- pstack/skills/principle-test-behavior-not-implementation/SKILL.md
principles/type-system-discipline.md <- pstack/skills/principle-type-system-discipline/SKILL.md
skills/architect/SKILL.md <- pstack/skills/architect/SKILL.md
skills/architect/references/design-red-flags.md <- pstack/skills/architect/references/design-red-flags.md
skills/architect/references/rationale-template.md <- pstack/skills/architect/references/rationale-template.md
skills/architect/references/runner-prompt.md <- pstack/skills/architect/references/runner-prompt.md
skills/automate-me/SKILL.md <- pstack/skills/automate-me/SKILL.md
skills/benchmark-checklist/SKILL.md <- pstack/skills/benchmark-checklist/SKILL.md
skills/blast-radius/SKILL.md <- pstack/skills/blast-radius/SKILL.md
skills/bro/SKILL.md <- pstack/skills/bro/SKILL.md
skills/correct/SKILL.md <- pstack/skills/correct/SKILL.md
skills/crew/SKILL.md <- pstack/skills/interrogate/references/lead-judgment.md
skills/how/SKILL.md <- pstack/skills/how/SKILL.md
skills/how/references/explainer-prompt.md <- pstack/skills/how/references/explainer-prompt.md
skills/how/references/explorer-prompt.md <- pstack/skills/how/references/explorer-prompt.md
skills/interrogate/SKILL.md <- pstack/skills/interrogate/SKILL.md
skills/interrogate/references/code-quality-review.md <- pstack/skills/interrogate/references/code-quality-review.md
skills/interrogate/references/lead-judgment.md <- pstack/skills/interrogate/references/lead-judgment.md
skills/interrogate/references/reviewer-prompt.md <- pstack/skills/interrogate/references/reviewer-prompt.md
skills/interrogate/references/rubric.md <- pstack/skills/interrogate/references/rubric.md
skills/ketchup/SKILL.md <- pstack/skills/ketchup/SKILL.md
skills/no-comments/SKILL.md <- pstack/skills/no-comments/SKILL.md, pstack/agents/comment-sicko.md
skills/pr-review/SKILL.md <- pstack/skills/interrogate/references/rubric.md, pstack/skills/interrogate/references/code-quality-review.md
skills/recall/SKILL.md <- pstack/skills/recall/SKILL.md
skills/reflect/SKILL.md <- pstack/skills/reflect/SKILL.md
skills/reflect/references/divergent-reviewer.md <- pstack/skills/reflect/references/divergent-reviewer.md
skills/reflect/references/judgment-reviewer.md <- pstack/skills/reflect/references/judgment-reviewer.md
skills/reflect/references/synthesizer.md <- pstack/skills/reflect/references/synthesizer.md
skills/reflect/references/tooling-reviewer.md <- pstack/skills/reflect/references/tooling-reviewer.md
skills/show-me-your-work/SKILL.md <- pstack/skills/show-me-your-work/SKILL.md
skills/show-me-your-work/scripts/log.sh <- pstack/skills/show-me-your-work/scripts/log.sh
skills/tdd/SKILL.md <- pstack/skills/tdd/SKILL.md
skills/teach/SKILL.md <- pstack/skills/teach/SKILL.md
skills/technical-writing/SKILL.md <- pstack/skills/technical-writing/SKILL.md
skills/typescript-best-practices/SKILL.md <- pstack/skills/typescript-best-practices/SKILL.md
skills/typescript-best-practices/references/patterns.md <- pstack/skills/typescript-best-practices/references/patterns.md
skills/unslop/SKILL.md <- pstack/skills/unslop/SKILL.md
skills/why/SKILL.md <- pstack/skills/why/SKILL.md
skills/why/references/epistemics.md <- pstack/skills/why/references/epistemics.md
skills/why/references/investigator-prompt.md <- pstack/skills/why/references/investigator-prompt.md
skills/why/references/source-playbook.md <- pstack/skills/why/references/source-playbook.md
skills/why/references/sources/code-archaeology.md <- pstack/skills/why/references/sources/code-archaeology.md
skills/why/references/sources/databricks.md <- pstack/skills/why/references/sources/databricks.md
skills/why/references/sources/datadog.md <- pstack/skills/why/references/sources/datadog.md
skills/why/references/sources/incident-postmortem.md <- pstack/skills/why/references/sources/incident-postmortem.md
skills/why/references/sources/linear.md <- pstack/skills/why/references/sources/linear.md
skills/why/references/sources/notion.md <- pstack/skills/why/references/sources/notion.md
skills/why/references/sources/sentry.md <- pstack/skills/why/references/sources/sentry.md
skills/why/references/sources/slack.md <- pstack/skills/why/references/sources/slack.md
skills/why/references/synthesizer-prompt.md <- pstack/skills/why/references/synthesizer-prompt.md
```

Each line is a file here and the upstream paths it was written from, at the commit above. A file added from pstack gets a line, and a move of the `Commit:` line follows a read of what changed.

Not taken: `pstack/skills/create-verification-skill`, `pstack/skills/maintain-verification-skill`, `pstack/skills/make-bot-ui`, `pstack/skills/poteto-help`, `pstack/skills/setup-pstack`, `pstack/skills/poteto-mode/playbooks/babysit.md`, `pstack/skills/poteto-mode/playbooks/worktree-cleanup.md`

`make pstack-drift` lists what changed upstream since that commit, for the paths of the map:

- It keeps a clone of the source in `${XDG_CACHE_HOME:-~/.cache}/jstack/cursor-plugins`, fetches its `main`, and needs only `git` and the network: no token.
- It prints `same`, `changed` (with the lines added and removed, the files here that came from the path, and each upstream commit) or `gone` for each upstream path, then `new` for each upstream skill or playbook that is neither in the map nor on `Not taken:`.
- `make pstack-drift ARGS=--diff` adds the diff under each `changed` line. `ARGS=--strict` exits 1 when anything drifted. Without it the exit is 0 whatever it finds. A run that cannot start, with no `git`, no pin, or a pin that is not in the upstream history, exits 2.
- The workflow `.github/workflows/pstack-drift.yml` runs it every Monday and puts the lines in the job's summary.

License of the source (MIT):

```
MIT License

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Matt Pocock's skills

`skills/grilling/SKILL.md` is taken from the grilling skill of Matt Pocock's skills.

- Source: https://github.com/mattpocock/skills
- Commit: 49dd158
- Taken from: `skills/productivity/grilling/SKILL.md`, whole
- Changed here: the frontmatter hides it from the model, so it loads when typed or when the home skill's "Planning" names it; the sub-agent that finds a fact is the `Explore` agent; and a section "In a home" says where the answers go and that a gate, not a round, is the rule once a task is out.

Files:

- `skills/grilling/SKILL.md`

License of the source (MIT):

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Karpathy guidelines

Two things a review looks for under its sixth question, in the `SCOPE` text of `skills/pr-review/SKILL.md`, are adapted from the Karpathy guidelines, by Forrest Chang, written from Andrej Karpathy's remarks on how models go wrong when they code.

- Source: https://github.com/forrestchang/andrej-karpathy-skills
- Commit: 2c60614
- Taken from: `skills/karpathy-guidelines/SKILL.md`, section 3, "Surgical Changes": "Every changed line should trace directly to the user's request", and the rule that a change removes what it orphaned and only mentions dead code that was there before
- Changed here: reworded as two things a reviewer looks for in the changed lines. The rest of the file is not taken: its other three sections are covered by `principles/`, and "If uncertain, ask" is against `principles/never-block-on-the-human.md`.
- License: the skill's frontmatter and the README say MIT. The repo has no license file, so there is no notice text to copy.
