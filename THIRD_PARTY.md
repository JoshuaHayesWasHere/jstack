# Third-party material

jstack's own license is in `LICENSE`. This file credits what was taken from others.

## pstack

The files in `principles/` are adapted from the principle skills of pstack, by Lauren Tan.

- Source: https://github.com/cursor/plugins/tree/main/pstack
- Commit: 99743e9c151c8537cbbf1f98bb38f34ef3368453
- Taken from: `pstack/skills/principle-<name>/SKILL.md`, one file per principle
- Changed here: the frontmatter is gone and its description is the first paragraph, links between principles point at the files in this directory, and pointers to pstack skills that are not in this repo are dropped or reworded. Each file has pstack's name, `principles/principle-<name>.md`, so that a name on a brief's `Skills:` line reads the same in pstack and here; the name before the prefix still resolves (`src/jbriefs/skills.py`).
- Also covered, from the same commit: six playbook files, `authoring-a-skill.md`, `bug-fix.md`, `feature.md`, `opening-a-pr.md` and `refactoring.md` in `playbooks/` and `investigation.md` in `features/scout/playbooks/`, each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout, with `bug-fix.md` also drawing on `pstack/skills/tdd/SKILL.md` and `investigation.md` on `pstack/skills/how/SKILL.md` and `pstack/skills/why/SKILL.md`.
- Also covered, from the same commit: `skills/unslop/SKILL.md` and `skills/technical-writing/SKILL.md`, each taken whole from `pstack/skills/<name>/SKILL.md`. Changed here: each has a `tip:` line for `hooks/skill-tips.sh`, unslop's description says when it loads, and technical-writing names `templates/pr-body.md` and says where it is.
- Also covered, from the same commit: the things to look for under the fourth and fifth questions of the review, in the `SCOPE` text of `features/pr-review/SKILL.md`, shortened from `pstack/skills/interrogate/references/rubric.md` and the dimensions of `pstack/skills/interrogate/references/code-quality-review.md`; and the two endings of a finding in `skills/crew/SKILL.md` "The review", which stand in for the four buckets of `pstack/skills/interrogate/references/lead-judgment.md`.
- Also covered, from the same commit: `skills/correct/SKILL.md` and `playbooks/correct.md` (the playbook file `correct.md`), adapted from `pstack/skills/correct/SKILL.md`, and `skills/reflect/SKILL.md` with the four prompts in `skills/reflect/references/`, adapted from `pstack/skills/reflect/` and its `references/`, both rewritten for Claude Code and this repo's home, crewmate and brief.
- Also covered, from the same commit: `playbooks/authoring-a-playbook.md` (the playbook file `authoring-a-playbook.md`), drawn from the phases of `pstack/skills/figure-it-out/SKILL.md` (a falsifiable definition of done, the check built before the work, the riskiest unknown first, each unit an experiment, a recurring correction encoded as a check or a script) and narrowed from designing a workflow for one task to writing a playbook for a kind of task. The `skip: <reason>` rule that every playbook carries is from `pstack/skills/poteto-mode/SKILL.md`.
- Also covered, from the same commit: five more playbook files, `prototype.md`, `pause-safely.md`, `runtime-forensics.md` and `visual-parity.md` in `playbooks/` and `trace-forensics.md` in `features/scout/playbooks/`, each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout: the reply became the brief's Result or the scout's report, the control skill became the repo's verify skill where it has one, and the delegate on a named model, `/loop` and the throughput checkpoint are gone.
- Also covered, from the same commit: three more files in `playbooks/` (the playbook files `perf-issue.md`, `hillclimb.md` and `autonomous-run.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate, and the two skills they lean on, `features/show-me-your-work/SKILL.md` with `scripts/log.sh` and `features/benchmark-checklist/SKILL.md`, each adapted from `pstack/skills/<name>/`. Changed here: the delegate on a named model, `/loop`, the stack of pull requests and the review of the log by a second model are gone; the log lives in the worktree's git directory and has the same six columns for every playbook; `scripts/runs.sh` of the benchmark skill is new, and takes the runs that its fifth question asks for.
- Also covered, from the same commit: `features/how/SKILL.md`, `skills/why/SKILL.md`, `features/teach/SKILL.md`, `skills/blast-radius/SKILL.md`, `features/recall/SKILL.md`, `features/ketchup/SKILL.md`, `features/bro/SKILL.md` and `features/automate-me/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, with the files in `features/how/references/` and `skills/why/references/` taken whole from the same directories but for one sentence in `sources/slack.md`. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, Cursor's tools and paths are Claude Code's, `recall` and `ketchup` read the home's record and its gates, and each skill loads only when typed.
- Also covered, from the same commit: `features/arena-swarm/skills/arena/SKILL.md` and `features/arena-swarm/skills/swarm/SKILL.md`, adapted from `pstack/skills/arena/SKILL.md` and `pstack/skills/swarm/SKILL.md`, and three playbook files, `arena.md` and `swarm.md` under `features/arena-swarm/skills/<their skill>/playbooks/` and `eval.md` in `playbooks/`, the first two from the same two upstream files and the third from `pstack/skills/poteto-mode/playbooks/eval.md`, all rewritten for this repo. Changed here: `/arena` and `/swarm` are typed in a home and open their playbook, which the home runs, and the steps are in the playbook alone; every runner, judge, graft and worker is a thread of its own with its brief or request under the home's state directory, a crewmate that jbus launches from its queue row or a scout the home launches, and none is a subagent; the arena's judge is a read-only crewmate, and its graft is a crewmate that scores both candidates before it reads the judge's verdict and opens the one pull request; the swarm's table is the home's, built from its threads' Reports and Results, and a swarm that wrote files ends in one pull request of a last crewmate; ten threads at most in a step; the cloud workers, the model per seat (but for `eval`, whose brief names its models) and the raised effort are gone; `eval` is still a crewmate's playbook whose candidates are local subagents, takes its models from the brief, keeps the key from a directory to its model in one file, and reads a candidate's transcript with the blocks of `skills/reflect/SKILL.md`.
- Also covered, from the same commit: four more files in `playbooks/` (the playbook files `orchestrate.md`, `multi-phase-plan.md`, `autopilot-full.md` and `session-pickup.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's home, which reads only its state directory, launches threads and merges with `jmerge`. Changed here: the coordinator's store, ledger and inbox are the state directory, a brief's Result and Review and the home's gates; an owner is a crewmate, the verdict its one reviewer's and the merge `jmerge`'s; the hourly tick is a scheduled run of T3 Code in place of `/loop`, and a thread is picked up by a message or a launch on its worktree in place of a transcript; "state the plan, then wait for the operator's go" is the plan the user approved; and the sub-coordinators, the cloud workers, the verifier on another model family, the ten live lanes, the stack and its stacker, and `orch` are gone.
- Also covered, from the same commit: `features/architect/SKILL.md`, `skills/interrogate/SKILL.md`, `features/tdd/SKILL.md`, `features/no-comments/SKILL.md` and `features/typescript-best-practices/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, and `features/no-comments/SKILL.md` also from `pstack/agents/comment-sicko.md`. The files in `features/architect/references/`, `skills/interrogate/references/` and `features/typescript-best-practices/references/` are from the same directories: `design-red-flags.md` whole, `patterns.md` whole but for two sentences that name a principle, the rest adapted. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, `architect` sketches its two candidates in its own thread and asks the home for `/arena` where they need two writers apart, `tdd` runs `playbooks/bug-fix.md`, `interrogate` reads the checks that `features/pr-review/SKILL.md` already holds from that file, the comment hunter reports and the thread deletes, and each skill loads only when typed.
- Also covered, from the same commit: two more files in `playbooks/` (the playbook files `autopilot-stack.md` and `shipping.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's home. Changed here: the root that rebases every link and pushes with `--force-with-lease` is a home that touches no branch, so each link's own crewmate rebases its own; the order of the stack is a `Stack:` line the home writes in each link's brief; a verdict is the one reviewer's, and a link is added only on one; the landing is `jmerge --land`, run on the user's word, for the one link whose base is the default branch; the patch-id of a verdict is the crewmate's `Rebase:` line; and the forge choice, Origin, the cloud agent per owner, Bugbot triage, the slop strip, the decision trails, auto-merge and the watch on the queue are gone.
- Also covered, from the same commit: `features/in-your-own-words/SKILL.md`, from `pstack/skills/in-your-own-words/SKILL.md` (#602, #606), upstream's text, plus a `tip:` and a `card:` line in the frontmatter and a `Source:` line under it.
- Also covered, from pstack 0.15.29 (cursor/plugins 88d47514b82e7c44f00f2b2a72ff6dd12158038c, #729, which is after the commit above): `features/sharpen/SKILL.md`, from `pstack/skills/sharpen/SKILL.md`, upstream's text, plus a `tip:` and a `card:` line in the frontmatter and a `Source:` line under it. #729 makes `/sharpen` rewrite only: it asks the four questions of a deeper task, rewrites the prompt to ask for exactly that and does not do the task. That is what jstack's own `deeper` skill did, so that skill is retired with this copy, and its eval, the `deeper` directory under `evals/`, is kept as a record that nothing runs. #712 (75fabac), which dropped the ban on a rewritten prompt, is in the same file and is replaced whole by #729. The pin stays at the commit above, so `jdrift` still prints this file as `changed` by those two commits until the pin moves past them.
- Also covered, from pstack 0.15.26 (cursor/plugins 4382e68, which is after the commit above): `skills/create-formal-verification-skill/SKILL.md`, adapted from `pstack/skills/create-formal-verification-skill/SKILL.md`. Changed here: a `Source:` line, a `tip:` and a `card:` line, a section that says it runs in a durable thread (a crewmate, or a scout for the read-only part) and never in a subagent, the place a generated skill goes in this repo (`.cursor/skills/verify-<area>/`), and that the proof step's scratch break runs in the thread's own worktree and is dropped with `git restore`.
- Also covered, from the pin above: `skills/figure-it-out/SKILL.md`, adapted from `pstack/skills/figure-it-out/SKILL.md`, which is the same at e5136d8.
  Changed here: it is typed in a home and frames the task in `$H/reports/frame-<slug>.md`, then plans the units as entries by `playbooks/multi-phase-plan.md`, each brief naming `show-me-your-work`; in any other thread it writes the frame and points at `/home`.
  poteto-mode, the subagents, their reasoning levels and the in-thread loop are gone: each unit is a crewmate's durable thread, a one-way door goes to the home's `features/arena-swarm/skills/arena/playbooks/arena.md` once that playbook is the home's and is parked until then, and the loop and the log are the crewmate's.
- Also covered, from the commit above: `skills/create-verification-skill/` and `skills/maintain-verification-skill/SKILL.md`, adapted from `pstack/skills/create-verification-skill/` and `pstack/skills/maintain-verification-skill/SKILL.md`, with the three files of `references/feature-map-example/` taken whole. Changed here: a `Source:` line, a `tip:` and a `card:` line, prose broken at its sentence ends, and no em dash. A generated skill goes in `.claude/skills/verify-<app>/`, where Claude Code loads project skills, and not in `.cursor/skills/`. `create-verification-skill` runs in a crewmate under the `authoring-a-skill` playbook, and its proof run goes in the Result. `maintain-verification-skill` is typed in the home: in place of a read-only subagent per feature it writes one scout request per feature file, launched ten at a time, and in place of the coordinator's live pass it writes one crewmate brief from the scouts' reports, checked by the brief lint, which drives every feature and opens at most one pull request. `.cursor/skills/verify-jstack` moved to `.claude/skills/verify-jstack` with it, and the old path is a relative link.
- Also covered, from the same commit: `skills/make-bot-ui/SKILL.md`, adapted from `pstack/skills/make-bot-ui/SKILL.md`; changed here: a `Source:` line, a `tip:` and a `card:` line, a first section that sends the user to a Lavish page with `sendToClaude` or to `jbus view`'s one write when either is enough, Cursor's routine, panel and `SendToUser` card replaced by T3 Code's `schedule_task` webhook bound to the thread that is woken, `request_secret` and `signature.secretRef`, the key made on this machine by the skill's own server and copied to the card by the clipboard, the server built by a crewmate's brief (`Playbook: feature`), the `0.0.0.0` bind replaced by `jbus view`'s rule of `127.0.0.1` and the tailnet address only, and the Tailscale install and `tailscale up` steps dropped, since the node is already online; upstream's #702 (a968159), after the pin, names the skill for its folder, as it already is here, so `jdrift` prints it as `changed` until the pin moves.
- The pin was 1b6d44f (version 0.15.20) until it moved to e5136d8, which is 0.15.25 and #633, and then to the commit above, which is #634 and nothing else. These upstream changes, up to the commit above, are taken in part or not at all. #634 (99743e9) is read and taken in part: its cuts in `pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md` and `pstack/skills/principle-type-system-discipline/SKILL.md` are made in `principles/principle-migrate-callers-then-delete-legacy-apis.md` and `principles/principle-type-system-discipline.md`, and "refuse to lie to the compiler" leaves the type-system description with the bullet that backed it. Its cut in `pstack/skills/interrogate/references/lead-judgment.md` is not taken: with it, two runs of `evals/skill-cut/` ruled the port a regression, so `skills/interrogate/references/lead-judgment.md` keeps its intro, "Why This Step Matters" and "Verdict Calibration". `pstack/skills/swarm/SKILL.md` is read at this commit, after its cuts, for `features/arena-swarm/skills/swarm/SKILL.md` and `features/arena-swarm/skills/swarm/playbooks/swarm.md`: the skill has no intro paragraph to cut, and the playbook's step on the number of threads and its one table carry this repo's own rules, ten threads at most in a step and a gap that does not count as a pass. Its README row is not vendored. #597 (b93e811) lets poteto-agent find poteto-mode under `~/.cursor/plugins` and drops the `mode:` and `reminder:` frontmatter that Cursor ignores: it is for the Cursor plugin only. `pstack/agents/poteto-agent.md` is not vendored, and the frontmatter it drops from `pstack/skills/poteto-mode/SKILL.md` is not the skip rule that `playbooks/authoring-a-playbook.md` takes from that file. #577 (364a77e) tells agents the absolute path of the bundled leaf skills, in `pstack/agents/poteto-agent.md`, which is not vendored, and in one line of `pstack/skills/poteto-mode/SKILL.md` that is not its skip rule. Here the crew and home skills pass that path themselves, as `$T`. #633 (e5136d8) also rewrites `pstack/docs/guide/08-principles.md` and the README, which are not vendored, and the index of principles in `pstack/skills/poteto-mode/SKILL.md`, which is not its skip rule and has no copy here, since each principle here is its own file, and `skills/correct/SKILL.md` keeps its own clause on a test that only finds sentences in a file. From #613 (ce649c0) these pieces are not taken. The line that picks each subagent's reasoning level for the job, in about twenty skills and playbooks, is not added, because no role here is raised above medium (the effort line below). Its two edits to `pstack/skills/poteto-mode/SKILL.md`, the "Match the model to the job" paragraph and a sentence cut from the one on `poteto-agent` subagents, leave that file's skip rule, the one part taken here, as it was. The one full swarm per pull request, with a single verifier on a rebase or a small fix, has no place here: a pull request gets one reviewer and no swarm, and a rebase that changed the reviewed content gets one scoped review. Graphite is dropped from `orchestrate`, and this repo never used it. The cut of `autopilot-full`, `autopilot-stack` and `shipping` to principles is taken in spirit only, since those files are this repo's own rewrites for a home and `jmerge`. Its changes to the `orch`, `watch-pr` and `worktree-audit` scripts are in files that are not vendored. The `/visualize` chart of #628 (afd51cf) is a Mermaid chart in `features/ketchup/SKILL.md`, since this repo has no `/visualize`. The menu lines that #602, #595, #609 and #615 add to `pstack/skills/poteto-help` are on the `Not taken:` line, and so is #613's effort sentence in `worktree-cleanup.md`. The version bumps (#584, #605, #614, #617) change only `plugin.json` files, which are not vendored.
- Up to 1b6d44f, these upstream changes are taken in part or not at all. #486 (de2dba6) renames the Comment Sicko agent to `comment-sicko`. This repo has no agent, and the hunter's prompt is inline in `features/no-comments/SKILL.md`. #575 (2bd5dd4) makes the poteto-mode chat the runner and poteto-agent a delegate. Only the skip rule of `pstack/skills/poteto-mode/SKILL.md` is taken, because a home here runs its playbooks itself. #574 (cf9a111, worktree-audit), #536 (87c8103, check-plan), #484 (ff8f83d, watch-pr) and #576 (e5a02f8, the root `plugin.json`) change files that are not vendored. The cuts of #571 (08bd59b) in `babysit.md` and `worktree-cleanup.md` are in paths on the `Not taken:` line below. The change of #573 (c49b37a) to `pstack/skills/create-verification-skill`, that ready means usable, is in `skills/create-verification-skill/SKILL.md`. `features/ketchup/SKILL.md` has the before and after visuals of #570 (ea32d95) without the generated image, which this repo's threads have no tool for.
- #613 (ce649c0), the merge result: `autopilot-full.md` step 5 runs the patch's checks on the merge result when trunk changed a caller of the patch or something it depends on. `jmerge` does so. Its fresh check (`Fresh.check` in `src/jmerge/cli.py`) runs the repo's `fresh-check` command in a worktree of `git merge-tree` of today's main and the head, never on the head alone, and merges on a pass. Since this line it is asked for when main, after the pull request's check started, changed a file that imports one of the pull request's files or that one of them imports (Python imports, by the file's dotted path or any tail of it, so a test that imports a sibling counts, and a `conftest.py` for every Python file under its directory), or a file that names the other's path, a path the pull request's renames left included, as well as when main changed the pull request's own files or a CI path (`/uv.lock` and `/pyproject.toml` among them, in `src/jmerge/ci-paths.txt`). A repo with no `fresh-check` file waits for a rebase in its place. The frozen-install shortcut for a lockfile both sides changed is not taken: the fresh check runs the whole command on the merge, which installs from the lockfile that would land. Tested in `tests/test_jmerge_callers.py`.
- #613 (ce649c0), the effort: upstream picks each subagent's reasoning level for the job, raising it for hard work. Here no role is raised. A T3 Code launch does take an effort: `modelSelection.options`, a list of `{"id": "effort", "value": <level>}`, and with none T3 Code launches the model at its own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5. So `jroles` names the effort on every Claude selection it prints, `medium` unless the role map's line ends `effort=low`, and refuses any other level, so that the user's rule, no effort above medium anywhere, holds for every Claude line of the map. A Codex or Grok line takes no effort and launches at that provider's own default, which is not read here: both are disabled in this machine's T3 Code, which lists no models for them. A role the map does not name inherits the launching thread's model, its effort included.

Files:

- `principles/principle-attack-the-premise.md`
- `principles/principle-boundary-discipline.md`
- `principles/principle-build-the-lever.md`
- `principles/principle-encode-lessons-in-structure.md`
- `principles/principle-exhaust-the-design-space.md`
- `principles/principle-experience-first.md`
- `principles/principle-explain-the-number.md`
- `principles/principle-fix-root-causes.md`
- `principles/principle-foundational-thinking.md`
- `principles/principle-guard-the-context-window.md`
- `principles/principle-laziness-protocol.md`
- `principles/principle-make-operations-idempotent.md`
- `principles/principle-migrate-callers-then-delete-legacy-apis.md`
- `principles/principle-minimize-reader-load.md`
- `principles/principle-model-the-domain.md`
- `principles/principle-never-block-on-the-human.md`
- `principles/principle-outcome-oriented-execution.md`
- `principles/principle-prove-it-works.md`
- `principles/principle-redesign-from-first-principles.md`
- `principles/principle-separate-before-serializing-shared-state.md`
- `principles/principle-sequence-verifiable-units.md`
- `principles/principle-subtract-before-you-add.md`
- `principles/principle-test-behavior-not-implementation.md`
- `principles/principle-type-system-discipline.md`

Upstream map:

```
features/arena-swarm/skills/arena/playbooks/arena.md <- pstack/skills/arena/SKILL.md
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
features/scout/playbooks/investigation.md <- pstack/skills/poteto-mode/playbooks/investigation.md, pstack/skills/how/SKILL.md, pstack/skills/why/SKILL.md
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
features/arena-swarm/skills/swarm/playbooks/swarm.md <- pstack/skills/swarm/SKILL.md
features/scout/playbooks/trace-forensics.md <- pstack/skills/poteto-mode/playbooks/trace-forensics.md
playbooks/visual-parity.md <- pstack/skills/poteto-mode/playbooks/visual-parity.md
principles/principle-attack-the-premise.md <- pstack/skills/principle-attack-the-premise/SKILL.md
principles/principle-boundary-discipline.md <- pstack/skills/principle-boundary-discipline/SKILL.md
principles/principle-build-the-lever.md <- pstack/skills/principle-build-the-lever/SKILL.md
principles/principle-encode-lessons-in-structure.md <- pstack/skills/principle-encode-lessons-in-structure/SKILL.md
principles/principle-exhaust-the-design-space.md <- pstack/skills/principle-exhaust-the-design-space/SKILL.md
principles/principle-experience-first.md <- pstack/skills/principle-experience-first/SKILL.md
principles/principle-explain-the-number.md <- pstack/skills/principle-explain-the-number/SKILL.md
principles/principle-fix-root-causes.md <- pstack/skills/principle-fix-root-causes/SKILL.md
principles/principle-foundational-thinking.md <- pstack/skills/principle-foundational-thinking/SKILL.md
principles/principle-guard-the-context-window.md <- pstack/skills/principle-guard-the-context-window/SKILL.md
principles/principle-laziness-protocol.md <- pstack/skills/principle-laziness-protocol/SKILL.md
principles/principle-make-operations-idempotent.md <- pstack/skills/principle-make-operations-idempotent/SKILL.md
principles/principle-migrate-callers-then-delete-legacy-apis.md <- pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md
principles/principle-minimize-reader-load.md <- pstack/skills/principle-minimize-reader-load/SKILL.md
principles/principle-model-the-domain.md <- pstack/skills/principle-model-the-domain/SKILL.md
principles/principle-never-block-on-the-human.md <- pstack/skills/principle-never-block-on-the-human/SKILL.md
principles/principle-outcome-oriented-execution.md <- pstack/skills/principle-outcome-oriented-execution/SKILL.md
principles/principle-prove-it-works.md <- pstack/skills/principle-prove-it-works/SKILL.md
principles/principle-redesign-from-first-principles.md <- pstack/skills/principle-redesign-from-first-principles/SKILL.md
principles/principle-separate-before-serializing-shared-state.md <- pstack/skills/principle-separate-before-serializing-shared-state/SKILL.md
principles/principle-sequence-verifiable-units.md <- pstack/skills/principle-sequence-verifiable-units/SKILL.md
principles/principle-subtract-before-you-add.md <- pstack/skills/principle-subtract-before-you-add/SKILL.md
principles/principle-test-behavior-not-implementation.md <- pstack/skills/principle-test-behavior-not-implementation/SKILL.md
principles/principle-type-system-discipline.md <- pstack/skills/principle-type-system-discipline/SKILL.md
features/architect/SKILL.md <- pstack/skills/architect/SKILL.md
features/architect/references/design-red-flags.md <- pstack/skills/architect/references/design-red-flags.md
features/architect/references/rationale-template.md <- pstack/skills/architect/references/rationale-template.md
features/architect/references/runner-prompt.md <- pstack/skills/architect/references/runner-prompt.md
features/arena-swarm/skills/arena/SKILL.md <- pstack/skills/arena/SKILL.md
features/automate-me/SKILL.md <- pstack/skills/automate-me/SKILL.md
features/benchmark-checklist/SKILL.md <- pstack/skills/benchmark-checklist/SKILL.md
skills/blast-radius/SKILL.md <- pstack/skills/blast-radius/SKILL.md
features/bro/SKILL.md <- pstack/skills/bro/SKILL.md
skills/correct/SKILL.md <- pstack/skills/correct/SKILL.md
skills/create-formal-verification-skill/SKILL.md <- pstack/skills/create-formal-verification-skill/SKILL.md
skills/create-verification-skill/SKILL.md <- pstack/skills/create-verification-skill/SKILL.md
skills/create-verification-skill/references/feature-map-example/README.md <- pstack/skills/create-verification-skill/references/feature-map-example/README.md
skills/create-verification-skill/references/feature-map-example/create-note.md <- pstack/skills/create-verification-skill/references/feature-map-example/create-note.md
skills/create-verification-skill/references/feature-map-example/search.md <- pstack/skills/create-verification-skill/references/feature-map-example/search.md
skills/crew/SKILL.md <- pstack/skills/interrogate/references/lead-judgment.md
skills/figure-it-out/SKILL.md <- pstack/skills/figure-it-out/SKILL.md
features/how/SKILL.md <- pstack/skills/how/SKILL.md
features/how/references/explainer-prompt.md <- pstack/skills/how/references/explainer-prompt.md
features/how/references/explorer-prompt.md <- pstack/skills/how/references/explorer-prompt.md
features/in-your-own-words/SKILL.md <- pstack/skills/in-your-own-words/SKILL.md
skills/interrogate/SKILL.md <- pstack/skills/interrogate/SKILL.md
skills/interrogate/references/code-quality-review.md <- pstack/skills/interrogate/references/code-quality-review.md
skills/interrogate/references/lead-judgment.md <- pstack/skills/interrogate/references/lead-judgment.md
skills/interrogate/references/reviewer-prompt.md <- pstack/skills/interrogate/references/reviewer-prompt.md
skills/interrogate/references/rubric.md <- pstack/skills/interrogate/references/rubric.md
features/ketchup/SKILL.md <- pstack/skills/ketchup/SKILL.md
skills/maintain-verification-skill/SKILL.md <- pstack/skills/maintain-verification-skill/SKILL.md
skills/make-bot-ui/SKILL.md <- pstack/skills/make-bot-ui/SKILL.md
features/no-comments/SKILL.md <- pstack/skills/no-comments/SKILL.md, pstack/agents/comment-sicko.md
features/pr-review/SKILL.md <- pstack/skills/interrogate/references/rubric.md, pstack/skills/interrogate/references/code-quality-review.md
features/recall/SKILL.md <- pstack/skills/recall/SKILL.md
skills/reflect/SKILL.md <- pstack/skills/reflect/SKILL.md
skills/reflect/references/divergent-reviewer.md <- pstack/skills/reflect/references/divergent-reviewer.md
skills/reflect/references/judgment-reviewer.md <- pstack/skills/reflect/references/judgment-reviewer.md
skills/reflect/references/synthesizer.md <- pstack/skills/reflect/references/synthesizer.md
skills/reflect/references/tooling-reviewer.md <- pstack/skills/reflect/references/tooling-reviewer.md
features/sharpen/SKILL.md <- pstack/skills/sharpen/SKILL.md
features/show-me-your-work/SKILL.md <- pstack/skills/show-me-your-work/SKILL.md
features/show-me-your-work/scripts/log.sh <- pstack/skills/show-me-your-work/scripts/log.sh
features/arena-swarm/skills/swarm/SKILL.md <- pstack/skills/swarm/SKILL.md
features/tdd/SKILL.md <- pstack/skills/tdd/SKILL.md
features/teach/SKILL.md <- pstack/skills/teach/SKILL.md
skills/technical-writing/SKILL.md <- pstack/skills/technical-writing/SKILL.md
features/typescript-best-practices/SKILL.md <- pstack/skills/typescript-best-practices/SKILL.md
features/typescript-best-practices/references/patterns.md <- pstack/skills/typescript-best-practices/references/patterns.md
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

jstack's own: `principles/principle-depth-over-breadth.md`, `skills/make-bot-ui/scripts/bot_ui.py`, `skills/poteto-help/SKILL.md`

The files on that line sit beside the ones taken and are jstack's own: no upstream path fed them, so `jdrift` prints each as `own` and compares nothing for it. `principles/principle-depth-over-breadth.md` is from the Felix Rieseberg section below. `skills/poteto-help/SKILL.md` is jstack's own skill, written after the upstream file `pstack/skills/poteto-help/SKILL.md`: it keeps that file's name and its help-only answer, and takes none of its text, so the upstream path stays on the `Not taken:` line below. Its pick comes from `jbriefs pick`, not from a hand-kept table, and it points at the home, crew, scout and expert skills, never at a mode.
`skills/make-bot-ui/scripts/bot_ui.py` is the server that upstream's make-bot-ui describes in prose, written here so that its tests run it.

Not taken: `pstack/skills/poteto-help`, `pstack/skills/setup-pstack`, `pstack/skills/poteto-mode/playbooks/babysit.md`, `pstack/skills/poteto-mode/playbooks/worktree-cleanup.md`

`skills/setup-pstack/SKILL.md` has the name of `pstack/skills/setup-pstack` and none of its text, so the upstream skill stays on that line. Upstream writes a Cursor rule of a model and a budget for each role, up to `max`. Here the skill runs `install.sh --setup`, which writes `~/.config/jstack/roles` with every role `inherit`. It keeps upstream's shape: it detects, loads what is there, and leaves a rerun idempotent.

`make pstack-drift` lists what changed upstream since that commit, for the paths of the map:

- It keeps a clone of the source in `${XDG_CACHE_HOME:-~/.cache}/jstack/cursor-plugins`, fetches its `main`, and needs only `git` and the network: no token.
- It prints `same`, `changed` (with the lines added and removed, the files here that came from the path, and each upstream commit) or `gone` for each upstream path, then `own` for each file on the `jstack's own:` line, then `new` for each upstream skill or playbook that is neither in the map nor on `Not taken:`.
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

`features/grilling/SKILL.md` is taken from the grilling skill of Matt Pocock's skills.

- Source: https://github.com/mattpocock/skills
- Commit: 49dd158
- Taken from: `skills/productivity/grilling/SKILL.md`, whole
- Changed here: the frontmatter hides it from the model, so it loads when typed or when the home skill's "Planning" names it; the sub-agent that finds a fact is the `Explore` agent; and a section "In a home" says where the answers go and that a gate, not a round, is the rule once a task is out.

Files:

- `features/grilling/SKILL.md`

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

Two things a review looks for under its sixth question, in the `SCOPE` text of `features/pr-review/SKILL.md`, are adapted from the Karpathy guidelines, by Forrest Chang, written from Andrej Karpathy's remarks on how models go wrong when they code.

- Source: https://github.com/forrestchang/andrej-karpathy-skills
- Commit: 2c60614
- Taken from: `skills/karpathy-guidelines/SKILL.md`, section 3, "Surgical Changes": "Every changed line should trace directly to the user's request", and the rule that a change removes what it orphaned and only mentions dead code that was there before
- Changed here: reworded as two things a reviewer looks for in the changed lines. The rest of the file is not taken: its other three sections are covered by `principles/`, and "If uncertain, ask" is against `principles/principle-never-block-on-the-human.md`.
- License: the skill's frontmatter and the README say MIT. The repo has no license file, so there is no notice text to copy.

## axe-core

`tests/fixtures/jbus-view/axe.min.js` is axe-core, by Deque Systems, the accessibility engine the page tests of `jbus view` run in the browser. Only the tests read it: the view never serves it.

- Source: https://github.com/dequelabs/axe-core
- Version: 4.14.0, the file `axe.min.js` of the package `https://registry.npmjs.org/axe-core/-/axe-core-4.14.0.tgz`, integrity `sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==`
- Changed here: nothing. The file is taken whole, with its notice.
- License: the Mozilla Public License 2.0, whose text is at https://mozilla.org/MPL/2.0/, as the notice at the top of the file says.

## Atkinson Hyperlegible Next

`src/jbus/view/font.woff2` is Atkinson Hyperlegible Next, by The Atkinson Hyperlegible Next Project Authors, the one font of the page `jbus view` serves. The view serves it at `/font.woff2`.

- Source: https://github.com/googlefonts/atkinson-hyperlegible-next
- Version: commit 7925f50f649b3813257faf2f4c0b381011f434f1, the file `fonts/webfonts/AtkinsonHyperlegibleNext[wght].woff2`, 48,188 bytes, sha256 `abde1ad5cf78b9ac575ef90d991f2e9101eb0b3b6668bde9a00e2e1e27d99afd`
- Changed here: nothing. The file is taken whole and renamed.
- License: the SIL Open Font License 1.1, "Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors". Its text, the repo's `OFL.txt`, is shipped beside the font as `src/jbus/view/OFL.txt`.

## Felix Rieseberg

`principles/principle-depth-over-breadth.md` and the four questions of the home's deeper-version step (`skills/home/handing-a-task-to-a-crewmate.md`) are built on the Depth type of Felix Rieseberg's four types of ambition (Speed, Altitude, Depth and Range).

- Source: Felix Rieseberg, "How to be more ambitious: A tutorial for humans with models", 2026-10-13: https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/
- Taken from: the prompt the post gives for Depth, as the home step's four questions, and the Depth moves the principle names: the instruments the best in the field use, reproducing a number from the raw data, an ambitious target said to be reasonable, and an outside judge in place of the model judging itself.
- Changed here: the home answers each question for this repo and this machine, by path, command or query, and writes each answer on the line of the brief it names. Altitude and Range are not taken.
- Ties to pstack: since #729, pstack's `/sharpen` is the same prompt, and jstack's copy of it (the pstack section above) is the skill a user types for it. jstack's own `deeper` skill, which quoted the prompt whole, is retired.
- License: none is stated on the post. The prompt is quoted with this credit, and the rest is jstack's own text.
