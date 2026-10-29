# Third-party material

jstack's own license is in `LICENSE`. This file credits what was taken from others.

## pstack

The principle skills of the `principles` feature are adapted from the principle skills of pstack, by Lauren Tan.

- Source: https://github.com/cursor/plugins/tree/main/pstack
- Commit: 4ec7ffa173eaa70d3d9467a627baf0954645a353
- Taken from: `pstack/skills/principle-<name>/SKILL.md`, one file per principle
- Changed here: the frontmatter keeps `name` and `disable-model-invocation: true`, its description is the first paragraph, which the body also keeps, links between principles point at the other principle skills, and pointers to pstack skills that are not in this repo are dropped or reworded. Each skill has pstack's name, `features/principles/skills/principle-<name>/SKILL.md`, so that a name on a brief's `Skills:` line reads the same in pstack and here; the name before the prefix still resolves (`jbriefs.skills`).
- Also covered, from the same commit: six playbook files, `bug-fix.md`, `feature.md` and `refactoring.md` in `features/crew/playbooks/`, `authoring-a-skill.md` in `features/skill-library/playbooks/`, `opening-a-pr.md` in `features/writing/playbooks/` and `investigation.md` in `features/scout/playbooks/`, each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout, with `bug-fix.md` also drawing on `pstack/skills/tdd/SKILL.md` and `investigation.md` on `pstack/skills/how/SKILL.md` and `pstack/skills/why/SKILL.md`.
- Also covered, from the same commit: `features/writing/skills/unslop/SKILL.md` and `features/writing/skills/technical-writing/SKILL.md`, each taken whole from `pstack/skills/<name>/SKILL.md`. Changed here: each has a `tip:` line for the tips hook, `skill-tips.sh`, unslop's description says when it loads, and technical-writing names `templates/pr-body.md` and says where it is.
- Also covered, from the same commit: the things to look for under the fourth and fifth questions of the review, in the `SCOPE` text of `features/pr-review/SKILL.md`, shortened from `pstack/skills/interrogate/references/rubric.md` and the dimensions of `pstack/skills/interrogate/references/code-quality-review.md`; and the two endings of a finding in `features/crew/SKILL.md` "The review", which stand in for the four buckets of `pstack/skills/interrogate/references/lead-judgment.md`.
- Also covered, from the same commit: `features/lessons/skills/correct/SKILL.md` and `features/lessons/skills/correct/playbooks/correct.md` (the playbook file `correct.md`), adapted from `pstack/skills/correct/SKILL.md`, and `features/lessons/skills/reflect/SKILL.md` with the four prompts in `features/lessons/skills/reflect/references/`, adapted from `pstack/skills/reflect/` and its `references/`, both rewritten for Claude Code and this repo's home, crewmate and brief.
- Also covered, from the same commit: `features/skill-library/playbooks/authoring-a-playbook.md` (the playbook file `authoring-a-playbook.md`), drawn from the phases of `pstack/skills/figure-it-out/SKILL.md` (a falsifiable definition of done, the check built before the work, the riskiest unknown first, each unit an experiment, a recurring correction encoded as a check or a script) and narrowed from designing a workflow for one task to writing a playbook for a kind of task. The `skip: <reason>` rule that every playbook carries is from `pstack/skills/poteto-mode/SKILL.md`.
- Also covered, from the same commit: five more playbook files, `prototype.md`, `pause-safely.md`, `runtime-forensics.md` and `visual-parity.md` in `features/crew/playbooks/` and `trace-forensics.md` in `features/scout/playbooks/`, each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate and scout: the reply became the brief's Result or the scout's report, the control skill became the repo's verify skill where it has one, and the delegate on a named model, `/loop` and the throughput checkpoint are gone.
- Also covered, from the same commit: three more files in `features/crew/playbooks/` (the playbook files `perf-issue.md`, `hillclimb.md` and `autonomous-run.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's crewmate, and the two skills they lean on, `features/show-me-your-work/SKILL.md` with `scripts/log.sh` and `features/benchmark-checklist/SKILL.md`, each adapted from `pstack/skills/<name>/`. Changed here: the delegate on a named model, `/loop`, the stack of pull requests and the review of the log by a second model are gone; the log lives in the worktree's git directory and has the same six columns for every playbook; `scripts/runs.sh` of the benchmark skill is new, and takes the runs that its fifth question asks for.
- Also covered, from the same commit: `features/how/SKILL.md`, `features/why/SKILL.md`, `features/teach/SKILL.md`, `features/skill-library/skills/blast-radius/SKILL.md`, `features/recall/SKILL.md`, `features/ketchup/SKILL.md`, `features/bro/SKILL.md` and `features/automate-me/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, with the files in `features/how/references/` and `features/why/references/` taken whole from the same directories but for one sentence in `sources/slack.md`. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, Cursor's tools and paths are Claude Code's, `recall` and `ketchup` read the home's record and its gates, and each skill loads only when typed.
- Also covered, from the same commit: `features/arena-swarm/skills/arena/SKILL.md` and `features/arena-swarm/skills/swarm/SKILL.md`, adapted from `pstack/skills/arena/SKILL.md` and `pstack/skills/swarm/SKILL.md`, and three playbook files, `arena.md` and `swarm.md` under `features/arena-swarm/skills/<their skill>/playbooks/` and `eval.md` in `features/evals/playbooks/`, the first two from the same two upstream files and the third from `pstack/skills/poteto-mode/playbooks/eval.md`, all rewritten for this repo. Changed here: `/arena` and `/swarm` are typed in a home and open their playbook, which the home runs, and the steps are in the playbook alone; every runner, judge, graft and worker is a thread of its own with its brief or request under the home's state directory, a crewmate that jbus launches from its queue row or a scout the home launches, and none is a subagent; the arena's judge is a read-only crewmate, and its graft is a crewmate that scores both candidates before it reads the judge's verdict and opens the one pull request; the swarm's table is the home's, built from its threads' Reports and Results, and a swarm that wrote files ends in one pull request of a last crewmate; ten threads at most in a step; the cloud workers, the model per seat (but for `eval`, whose brief names its models) and the raised effort are gone; `eval` is still a crewmate's playbook whose candidates are local subagents, takes its models from the brief, keeps the key from a directory to its model in one file, and reads a candidate's transcript with the blocks of `skills/reflect/SKILL.md`.
- Also covered, from the same commit: four more files in `features/home/skills/home/playbooks/` (the playbook files `orchestrate.md`, `multi-phase-plan.md`, `autopilot-full.md` and `session-pickup.md`), each adapted from `pstack/skills/poteto-mode/playbooks/<name>.md` and rewritten for this repo's home, which reads only its state directory, launches threads and merges with `jmerge`. Changed here: the coordinator's store, ledger and inbox are the state directory, a brief's Result and Review and the home's gates; an owner is a crewmate, the verdict its one reviewer's and the merge `jmerge`'s; the hourly tick is a scheduled run of T3 Code in place of `/loop`, and a thread is picked up by a message or a launch on its worktree in place of a transcript; "state the plan, then wait for the operator's go" is the plan the user approved; and the sub-coordinators, the cloud workers, the verifier on another model family, the ten live lanes, the stack and its stacker, and `orch` are gone.
- Also covered, from the same commit: `features/architect/SKILL.md`, `features/skill-library/skills/interrogate/SKILL.md`, `features/tdd/SKILL.md`, `features/no-comments/SKILL.md` and `features/typescript-best-practices/SKILL.md`, each adapted from `pstack/skills/<name>/SKILL.md`, and `features/no-comments/SKILL.md` also from `pstack/agents/comment-sicko.md`. The files in `features/architect/references/`, `features/skill-library/skills/interrogate/references/` and `features/typescript-best-practices/references/` are from the same directories: `design-red-flags.md` whole, `patterns.md` whole but for two sentences that name a principle, the rest adapted. Changed here: a subagent is an `Explore` agent on the session's model in place of a model per role, `architect` sketches its two candidates in its own thread and asks the home for `/arena` where they need two writers apart, `tdd` runs `features/crew/playbooks/bug-fix.md`, `interrogate` reads the checks that `features/pr-review/SKILL.md` already holds from that file, the comment hunter reports and the thread deletes, and each skill loads only when typed.
- Also covered, from the same commit: `features/in-your-own-words/SKILL.md`, from `pstack/skills/in-your-own-words/SKILL.md` (#602, #606), upstream's text, plus a `tip:` and a `card:` line in the frontmatter and a `Source:` line under it.
- Also covered, from pstack 0.15.29 (cursor/plugins 88d47514b82e7c44f00f2b2a72ff6dd12158038c, #729, which is after the commit above): `features/sharpen/SKILL.md`, from `pstack/skills/sharpen/SKILL.md`, upstream's text, plus a `tip:` and a `card:` line in the frontmatter and a `Source:` line under it. #729 makes `/sharpen` rewrite only: it asks the four questions of a deeper task, rewrites the prompt to ask for exactly that and does not do the task. That is what jstack's own `deeper` skill did, so that skill is retired with this copy, and its eval, the `deeper` eval of the evals feature, is kept as a record that nothing runs. #712 (75fabac), which dropped the ban on a rewritten prompt, is in the same file and is replaced whole by #729. The pin has since moved past both commits, to #779 (the `Commit:` line).
- Also covered, from pstack 0.15.26 (cursor/plugins 4382e68, #709), re-synced at the pin to take #721 (6b78e9f: TLA+ is the default model checker in any language, and with no verifier for the language the real code is tested with generated inputs) and #716 (7b353f7: the generated skill records the code each check covers and the sync commit, and the hand-off points at `/maintain-formal-verification-skill`): `features/skill-library/skills/create-formal-verification-skill/SKILL.md`, adapted from `pstack/skills/create-formal-verification-skill/SKILL.md`. Changed here: a `Source:` line, a `tip:` and a `card:` line, a section that says it runs in a durable thread (a crewmate, or a scout for the read-only part) and never in a subagent, the place a generated skill goes in this repo (a project skill of the feature that owns the verified code, `features/<feature>/project-skill/verify-<area>/`, named in its `feature.json` under `projectSkills`, which replaced `.cursor/skills/verify-<area>/` when jstack moved its project skills into its features), that the proof step's scratch break runs in the thread's own worktree and is dropped with `git restore`, and prose broken at its sentence ends where the re-sync touched it.
- Also covered, from the pin above: `features/skill-library/skills/figure-it-out/SKILL.md`, adapted from `pstack/skills/figure-it-out/SKILL.md`, which is the same at e5136d8.
  Changed here: it is typed in a home and frames the task in `$H/reports/frame-<slug>.md`, then plans the units as entries by `features/home/skills/home/playbooks/multi-phase-plan.md`, each brief naming `show-me-your-work`; in any other thread it writes the frame and points at `/home`.
  poteto-mode, the subagents, their reasoning levels and the in-thread loop are gone: each unit is a crewmate's durable thread, a one-way door goes to the home's `features/arena-swarm/skills/arena/playbooks/arena.md` once that playbook is the home's and is parked until then, and the loop and the log are the crewmate's.
- Also covered, from the commit above: `features/skill-library/skills/create-verification-skill/` and `features/skill-library/skills/maintain-verification-skill/SKILL.md`, adapted from `pstack/skills/create-verification-skill/` and `pstack/skills/maintain-verification-skill/SKILL.md`, with the three files of `references/feature-map-example/` taken whole. Changed here: a `Source:` line, a `tip:` and a `card:` line, prose broken at its sentence ends, and no em dash. A generated skill goes in `.claude/skills/verify-<app>/`, where Claude Code loads project skills, and not in `.cursor/skills/`. `create-verification-skill` runs in a crewmate under the `authoring-a-skill` playbook, and its proof run goes in the Result. `maintain-verification-skill` is typed in the home: in place of a read-only subagent per feature it writes one scout request per feature file, launched ten at a time, and in place of the coordinator's live pass it writes one crewmate brief from the scouts' reports, checked by the brief lint, which drives every feature and opens at most one pull request. `.cursor/skills/verify-jstack` moved to `.claude/skills/verify-jstack` with it, and the old path is a relative link.
- Also covered, from the same commit: `features/skill-library/skills/make-bot-ui/SKILL.md`, adapted from `pstack/skills/make-bot-ui/SKILL.md`; changed here: a `Source:` line, a `tip:` and a `card:` line, a first section that sends the user to a Lavish page with `sendToClaude` or to `jbus view`'s one write when either is enough, Cursor's routine, panel and `SendToUser` card replaced by T3 Code's `schedule_task` webhook bound to the thread that is woken, `request_secret` and `signature.secretRef`, the key made on this machine by the skill's own server and copied to the card by the clipboard, the server built by a crewmate's brief (`Playbook: feature`), the `0.0.0.0` bind replaced by `jbus view`'s rule of `127.0.0.1` and the tailnet address only, and the Tailscale install and `tailscale up` steps dropped, since the node is already online; upstream's #702 (a968159) names the skill for its folder, as it already was here, so the move of the pin to #779 takes nothing from it.
- Also covered, from the pin (#779, 4ec7ffa, which carries #741 eb4db2b, #776 7698375 and #779 itself): the `statechart` skill, `features/skill-library/skills/statechart/SKILL.md` and the scripts beside it, from `pstack/skills/statechart/`.
  `SKILL.md` is upstream's text broken at its sentence ends.
  The scripts are ported from Node to Python, so that `uv run` brings the Java that TLC needs and nobody installs it by hand, as the uv project `scripts/` (`pyproject.toml`, `uv.lock`, package `statechart/`): `lib.py`, `cli.py` (the `statechart` command), `tlc_to_chart.py`, `chart_to_tla.py` and `compare_charts.py` port `lib.mjs`, `statechart.mjs`, `tlc-to-chart.mjs`, `chart-to-tla.mjs` and `compare-charts.mjs` function for function, and on the bundled model they write the same `chart.mmd`, `stories.md`, `summary.json` and region proofs, byte for byte, as the Node scripts do.
  `features/skill-library/tests/test_statechart_charts.py`, `test_statechart_specs.py` and `test_statechart_runs.py` port `test/statechart.test.mjs`, one test for one, under the repo's cap on the length of a test file, with what they share in `statechart_support.py`, with `test/sync.mmd` and `test/upload.mmd` in `features/skill-library/tests/statechart/`.
  Changed here: the commands are `statechart`, `tlc-to-chart`, `chart-to-tla` and `compare-charts`, run with `uv run --project <skill dir>/scripts`; a mapping is a Python file, `SPEC.map.py`, with `reader_actions`, `region_names` and `group_colors` in place of `readerActions`, `regionNames` and `groupColors`, and a mapping's function may take fewer arguments than it is given, as a JavaScript function may; Java comes from the `jdk4py` wheel pinned in `pyproject.toml` (or `JAVA`), and `tla2tools.jar` 1.7.4 is downloaded once to `~/.cache/jstack/tla2tools/`, checked against the sha256 pinned in `statechart/tools.py` (or `TLA2TOOLS`), where upstream asks for both by hand; `--png` runs `@mermaid-js/mermaid-cli@12.0.0`, pinned in `tools.py`, where upstream runs npx's latest; the bundled model's action `KillNode`, the user killing the command's own process, is `KillPython`; and the tests live in the feature's `tests/` folder, where the repo's pytest runs them.
- Also covered, from #716 (7b353f7, before the pin): `features/skill-library/skills/maintain-formal-verification-skill/SKILL.md`, from `pstack/skills/maintain-formal-verification-skill/SKILL.md`, the same at the pin.
  Changed here: a `Source:` line, a `tip:` and a `card:` line, a section that says it runs in a durable thread, as `create-formal-verification-skill` does, where to find a verify skill in a repo that lists its project skills in `skills.json`, the break of step 5 made in the thread's own worktree and dropped with `git restore`, and prose broken at its sentence ends.
- The pin was 99743e9 (#634) until it moved to #779 with the statechart port.
  These upstream changes between the two, the 19 commits that touch `pstack/`, are read and taken in part or not at all.
  #741, #776 and #779 are the statechart skill, and #709, #721 and #716 the formal verification pair, each taken as its line above says.
  #729 and #712 are `sharpen`, taken as its line above says.
  #702 (a968159) names every skill after its folder: `make-bot-ui` already was, and in `pstack/skills/poteto-mode/SKILL.md` it changes the frontmatter, not the skip rule taken from that file.
  #692 (16541c6) and #708 (bc14437) make `pstack/skills/ketchup/SKILL.md` list every item waiting on the user, and never cut one to stay under a word count, and #700 (0317eb8) makes `pstack/skills/typescript-best-practices/SKILL.md` and its `references/patterns.md` build a brand with a type guard and not with `as`: neither is taken yet, `features/ketchup/SKILL.md`, `features/typescript-best-practices/SKILL.md` and `features/typescript-best-practices/references/patterns.md` keep the text of the pin before, and `jdrift` no longer prints them as `changed`, so this line is the record that they are behind.
  #637 (182f2ce) and #705 (1b80080) build and fix pstack's own Claude Code plugin tree, which is not vendored, since jstack installs its own.
  #704 (019a6a2), #715 (f9be7aa) and #724 (d457567) change the README, the guide, `poteto-help` and `setup-pstack`, which are not vendored or are on the `Not taken:` line, and the menu lines that #709, #716, #729 and #741 add to `pstack/skills/poteto-help` are there with them.
  #710 and #713 bump the version only.
- The pin was 1b6d44f (version 0.15.20) until it moved to e5136d8, which is 0.15.25 and #633, and then to 99743e9, which is #634 and nothing else. These upstream changes, up to 99743e9, are taken in part or not at all. #634 (99743e9) is read and taken in part: its cuts in `pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md` and `pstack/skills/principle-type-system-discipline/SKILL.md` are made in `features/principles/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md` and `features/principles/skills/principle-type-system-discipline/SKILL.md`, and "refuse to lie to the compiler" leaves the type-system description with the bullet that backed it. Its cut in `pstack/skills/interrogate/references/lead-judgment.md` is not taken: with it, two runs of the evals feature's skill-cut eval ruled the port a regression, so `features/skill-library/skills/interrogate/references/lead-judgment.md` keeps its intro, "Why This Step Matters" and "Verdict Calibration". `pstack/skills/swarm/SKILL.md` is read at this commit, after its cuts, for `features/arena-swarm/skills/swarm/SKILL.md` and `features/arena-swarm/skills/swarm/playbooks/swarm.md`: the skill has no intro paragraph to cut, and the playbook's step on the number of threads and its one table carry this repo's own rules, ten threads at most in a step and a gap that does not count as a pass. Its README row is not vendored. #597 (b93e811) lets poteto-agent find poteto-mode under `~/.cursor/plugins` and drops the `mode:` and `reminder:` frontmatter that Cursor ignores: it is for the Cursor plugin only. `pstack/agents/poteto-agent.md` is not vendored, and the frontmatter it drops from `pstack/skills/poteto-mode/SKILL.md` is not the skip rule that `features/skill-library/playbooks/authoring-a-playbook.md` takes from that file. #577 (364a77e) tells agents the absolute path of the bundled leaf skills, in `pstack/agents/poteto-agent.md`, which is not vendored, and in one line of `pstack/skills/poteto-mode/SKILL.md` that is not its skip rule. Here the crew and home skills pass that path themselves, as `$T`. #633 (e5136d8) also rewrites `pstack/docs/guide/08-principles.md` and the README, which are not vendored, and the index of principles in `pstack/skills/poteto-mode/SKILL.md`, which is not its skip rule and has no copy here, since each principle here is its own file, and `features/lessons/skills/correct/SKILL.md` keeps its own clause on a test that only finds sentences in a file. From #613 (ce649c0) these pieces are not taken. The line that picks each subagent's reasoning level for the job, in about twenty skills and playbooks, is not added, because no role here is raised above medium (the effort line below). Its two edits to `pstack/skills/poteto-mode/SKILL.md`, the "Match the model to the job" paragraph and a sentence cut from the one on `poteto-agent` subagents, leave that file's skip rule, the one part taken here, as it was. The one full swarm per pull request, with a single verifier on a rebase or a small fix, has no place here: a pull request gets one reviewer and no swarm, and a rebase that changed the reviewed content gets one scoped review. Graphite is dropped from `orchestrate`, and this repo never used it. The cut of `autopilot-full`, `autopilot-stack` and `shipping` to principles is taken in spirit only, since those files are this repo's own rewrites for a home and `jmerge`. Its changes to the `orch`, `watch-pr` and `worktree-audit` scripts are in files that are not vendored. The `/visualize` chart of #628 (afd51cf) is a Mermaid chart in `features/ketchup/SKILL.md`, since this repo has no `/visualize`. The menu lines that #602, #595, #609 and #615 add to `pstack/skills/poteto-help` are on the `Not taken:` line, and so is #613's effort sentence in `worktree-cleanup.md`. The version bumps (#584, #605, #614, #617) change only `plugin.json` files, which are not vendored.
- Up to 1b6d44f, these upstream changes are taken in part or not at all. #486 (de2dba6) renames the Comment Sicko agent to `comment-sicko`. This repo has no agent, and the hunter's prompt is inline in `features/no-comments/SKILL.md`. #575 (2bd5dd4) makes the poteto-mode chat the runner and poteto-agent a delegate. Only the skip rule of `pstack/skills/poteto-mode/SKILL.md` is taken, because a home here runs its playbooks itself. #574 (cf9a111, worktree-audit), #536 (87c8103, check-plan), #484 (ff8f83d, watch-pr) and #576 (e5a02f8, the root `plugin.json`) change files that are not vendored. The cuts of #571 (08bd59b) in `babysit.md` and `worktree-cleanup.md` are in paths on the `Not taken:` line below. The change of #573 (c49b37a) to `pstack/skills/create-verification-skill`, that ready means usable, is in `features/skill-library/skills/create-verification-skill/SKILL.md`. `features/ketchup/SKILL.md` has the before and after visuals of #570 (ea32d95) without the generated image, which this repo's threads have no tool for.
- #613 (ce649c0), the merge result: `autopilot-full.md` step 5 runs the patch's checks on the merge result when trunk changed a caller of the patch or something it depends on. `jmerge` does so. Its fresh check (`Fresh.check` in jmerge's `cli.py`) runs the repo's `fresh-check` command in a worktree of `git merge-tree` of today's main and the head, never on the head alone, and merges on a pass. It is asked for when main, after the pull request's check started, changed the pull request's own files or a CI path (`/uv.lock` and `/pyproject.toml` among them, in jmerge's `ci-paths.txt`). The trigger upstream names, trunk changing a caller of the patch or something it depends on, is not taken: jmerge read it as Python imports and path mentions until Josh's word 7314ddd67c62 (2026-10-28) dropped it, after merge-wait-2 found 88 reruns it alone caused in a week and no fault caught among them. A repo with no `fresh-check` file waits for a rebase in its place. The frozen-install shortcut for a lockfile both sides changed is not taken: the fresh check runs the whole command on the merge, which installs from the lockfile that would land. Tested in jmerge's `test_jmerge_callers.py`.
- #613 (ce649c0), the effort: upstream picks each subagent's reasoning level for the job, raising it for hard work. Here no role is raised. A T3 Code launch does take an effort: `modelSelection.options`, a list of `{"id": "effort", "value": <level>}`, and with none T3 Code launches the model at its own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5. So `jroles` names the effort on every Claude selection it prints, `medium` unless the role map's line ends `effort=low`, and refuses any other level, so that the user's rule, no effort above medium anywhere, holds for every Claude line of the map. A Codex or Grok line takes no effort and launches at that provider's own default, which is not read here: both are disabled in this machine's T3 Code, which lists no models for them. A role the map does not name inherits the launching thread's model, its effort included.

Files:

- `features/principles/skills/principle-attack-the-premise/SKILL.md`
- `features/principles/skills/principle-boundary-discipline/SKILL.md`
- `features/principles/skills/principle-build-the-lever/SKILL.md`
- `features/principles/skills/principle-encode-lessons-in-structure/SKILL.md`
- `features/principles/skills/principle-exhaust-the-design-space/SKILL.md`
- `features/principles/skills/principle-experience-first/SKILL.md`
- `features/principles/skills/principle-explain-the-number/SKILL.md`
- `features/principles/skills/principle-fix-root-causes/SKILL.md`
- `features/principles/skills/principle-foundational-thinking/SKILL.md`
- `features/principles/skills/principle-guard-the-context-window/SKILL.md`
- `features/principles/skills/principle-laziness-protocol/SKILL.md`
- `features/principles/skills/principle-make-operations-idempotent/SKILL.md`
- `features/principles/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md`
- `features/principles/skills/principle-minimize-reader-load/SKILL.md`
- `features/principles/skills/principle-model-the-domain/SKILL.md`
- `features/principles/skills/principle-never-block-on-the-human/SKILL.md`
- `features/principles/skills/principle-outcome-oriented-execution/SKILL.md`
- `features/principles/skills/principle-prove-it-works/SKILL.md`
- `features/principles/skills/principle-redesign-from-first-principles/SKILL.md`
- `features/principles/skills/principle-separate-before-serializing-shared-state/SKILL.md`
- `features/principles/skills/principle-sequence-verifiable-units/SKILL.md`
- `features/principles/skills/principle-subtract-before-you-add/SKILL.md`
- `features/principles/skills/principle-test-behavior-not-implementation/SKILL.md`
- `features/principles/skills/principle-type-system-discipline/SKILL.md`

Upstream map:

```
features/arena-swarm/skills/arena/playbooks/arena.md <- pstack/skills/arena/SKILL.md
features/skill-library/playbooks/authoring-a-playbook.md <- pstack/skills/figure-it-out/SKILL.md, pstack/skills/poteto-mode/SKILL.md
features/skill-library/playbooks/authoring-a-skill.md <- pstack/skills/poteto-mode/playbooks/authoring-a-skill.md
features/crew/playbooks/autonomous-run.md <- pstack/skills/poteto-mode/playbooks/autonomous-run.md
features/home/skills/home/playbooks/autopilot-full.md <- pstack/skills/poteto-mode/playbooks/autopilot-full.md
features/crew/playbooks/bug-fix.md <- pstack/skills/poteto-mode/playbooks/bug-fix.md, pstack/skills/tdd/SKILL.md
features/lessons/skills/correct/playbooks/correct.md <- pstack/skills/correct/SKILL.md
features/evals/playbooks/eval.md <- pstack/skills/poteto-mode/playbooks/eval.md
features/crew/playbooks/feature.md <- pstack/skills/poteto-mode/playbooks/feature.md
features/crew/playbooks/hillclimb.md <- pstack/skills/poteto-mode/playbooks/hillclimb.md
features/scout/playbooks/investigation.md <- pstack/skills/poteto-mode/playbooks/investigation.md, pstack/skills/how/SKILL.md, pstack/skills/why/SKILL.md
features/home/skills/home/playbooks/multi-phase-plan.md <- pstack/skills/poteto-mode/playbooks/multi-phase-plan.md
features/writing/playbooks/opening-a-pr.md <- pstack/skills/poteto-mode/playbooks/opening-a-pr.md
features/home/skills/home/playbooks/orchestrate.md <- pstack/skills/poteto-mode/playbooks/orchestrate.md
features/crew/playbooks/pause-safely.md <- pstack/skills/poteto-mode/playbooks/pause-safely.md
features/crew/playbooks/perf-issue.md <- pstack/skills/poteto-mode/playbooks/perf-issue.md
features/crew/playbooks/prototype.md <- pstack/skills/poteto-mode/playbooks/prototype.md
features/crew/playbooks/refactoring.md <- pstack/skills/poteto-mode/playbooks/refactoring.md
features/crew/playbooks/runtime-forensics.md <- pstack/skills/poteto-mode/playbooks/runtime-forensics.md
features/home/skills/home/playbooks/session-pickup.md <- pstack/skills/poteto-mode/playbooks/session-pickup.md
features/arena-swarm/skills/swarm/playbooks/swarm.md <- pstack/skills/swarm/SKILL.md
features/scout/playbooks/trace-forensics.md <- pstack/skills/poteto-mode/playbooks/trace-forensics.md
features/crew/playbooks/visual-parity.md <- pstack/skills/poteto-mode/playbooks/visual-parity.md
features/principles/skills/principle-attack-the-premise/SKILL.md <- pstack/skills/principle-attack-the-premise/SKILL.md
features/principles/skills/principle-boundary-discipline/SKILL.md <- pstack/skills/principle-boundary-discipline/SKILL.md
features/principles/skills/principle-build-the-lever/SKILL.md <- pstack/skills/principle-build-the-lever/SKILL.md
features/principles/skills/principle-encode-lessons-in-structure/SKILL.md <- pstack/skills/principle-encode-lessons-in-structure/SKILL.md
features/principles/skills/principle-exhaust-the-design-space/SKILL.md <- pstack/skills/principle-exhaust-the-design-space/SKILL.md
features/principles/skills/principle-experience-first/SKILL.md <- pstack/skills/principle-experience-first/SKILL.md
features/principles/skills/principle-explain-the-number/SKILL.md <- pstack/skills/principle-explain-the-number/SKILL.md
features/principles/skills/principle-fix-root-causes/SKILL.md <- pstack/skills/principle-fix-root-causes/SKILL.md
features/principles/skills/principle-foundational-thinking/SKILL.md <- pstack/skills/principle-foundational-thinking/SKILL.md
features/principles/skills/principle-guard-the-context-window/SKILL.md <- pstack/skills/principle-guard-the-context-window/SKILL.md
features/principles/skills/principle-laziness-protocol/SKILL.md <- pstack/skills/principle-laziness-protocol/SKILL.md
features/principles/skills/principle-make-operations-idempotent/SKILL.md <- pstack/skills/principle-make-operations-idempotent/SKILL.md
features/principles/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md <- pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md
features/principles/skills/principle-minimize-reader-load/SKILL.md <- pstack/skills/principle-minimize-reader-load/SKILL.md
features/principles/skills/principle-model-the-domain/SKILL.md <- pstack/skills/principle-model-the-domain/SKILL.md
features/principles/skills/principle-never-block-on-the-human/SKILL.md <- pstack/skills/principle-never-block-on-the-human/SKILL.md
features/principles/skills/principle-outcome-oriented-execution/SKILL.md <- pstack/skills/principle-outcome-oriented-execution/SKILL.md
features/principles/skills/principle-prove-it-works/SKILL.md <- pstack/skills/principle-prove-it-works/SKILL.md
features/principles/skills/principle-redesign-from-first-principles/SKILL.md <- pstack/skills/principle-redesign-from-first-principles/SKILL.md
features/principles/skills/principle-separate-before-serializing-shared-state/SKILL.md <- pstack/skills/principle-separate-before-serializing-shared-state/SKILL.md
features/principles/skills/principle-sequence-verifiable-units/SKILL.md <- pstack/skills/principle-sequence-verifiable-units/SKILL.md
features/principles/skills/principle-subtract-before-you-add/SKILL.md <- pstack/skills/principle-subtract-before-you-add/SKILL.md
features/principles/skills/principle-test-behavior-not-implementation/SKILL.md <- pstack/skills/principle-test-behavior-not-implementation/SKILL.md
features/principles/skills/principle-type-system-discipline/SKILL.md <- pstack/skills/principle-type-system-discipline/SKILL.md
features/architect/SKILL.md <- pstack/skills/architect/SKILL.md
features/architect/references/design-red-flags.md <- pstack/skills/architect/references/design-red-flags.md
features/architect/references/rationale-template.md <- pstack/skills/architect/references/rationale-template.md
features/architect/references/runner-prompt.md <- pstack/skills/architect/references/runner-prompt.md
features/arena-swarm/skills/arena/SKILL.md <- pstack/skills/arena/SKILL.md
features/automate-me/SKILL.md <- pstack/skills/automate-me/SKILL.md
features/benchmark-checklist/SKILL.md <- pstack/skills/benchmark-checklist/SKILL.md
features/skill-library/skills/blast-radius/SKILL.md <- pstack/skills/blast-radius/SKILL.md
features/bro/SKILL.md <- pstack/skills/bro/SKILL.md
features/lessons/skills/correct/SKILL.md <- pstack/skills/correct/SKILL.md
features/skill-library/skills/create-formal-verification-skill/SKILL.md <- pstack/skills/create-formal-verification-skill/SKILL.md
features/skill-library/skills/create-verification-skill/SKILL.md <- pstack/skills/create-verification-skill/SKILL.md
features/skill-library/skills/create-verification-skill/references/feature-map-example/README.md <- pstack/skills/create-verification-skill/references/feature-map-example/README.md
features/skill-library/skills/create-verification-skill/references/feature-map-example/create-note.md <- pstack/skills/create-verification-skill/references/feature-map-example/create-note.md
features/skill-library/skills/create-verification-skill/references/feature-map-example/search.md <- pstack/skills/create-verification-skill/references/feature-map-example/search.md
features/crew/SKILL.md <- pstack/skills/interrogate/references/lead-judgment.md
features/skill-library/skills/figure-it-out/SKILL.md <- pstack/skills/figure-it-out/SKILL.md
features/how/SKILL.md <- pstack/skills/how/SKILL.md
features/how/references/explainer-prompt.md <- pstack/skills/how/references/explainer-prompt.md
features/how/references/explorer-prompt.md <- pstack/skills/how/references/explorer-prompt.md
features/in-your-own-words/SKILL.md <- pstack/skills/in-your-own-words/SKILL.md
features/skill-library/skills/interrogate/SKILL.md <- pstack/skills/interrogate/SKILL.md
features/skill-library/skills/interrogate/references/code-quality-review.md <- pstack/skills/interrogate/references/code-quality-review.md
features/skill-library/skills/interrogate/references/lead-judgment.md <- pstack/skills/interrogate/references/lead-judgment.md
features/skill-library/skills/interrogate/references/reviewer-prompt.md <- pstack/skills/interrogate/references/reviewer-prompt.md
features/skill-library/skills/interrogate/references/rubric.md <- pstack/skills/interrogate/references/rubric.md
features/ketchup/SKILL.md <- pstack/skills/ketchup/SKILL.md
features/skill-library/skills/maintain-verification-skill/SKILL.md <- pstack/skills/maintain-verification-skill/SKILL.md
features/skill-library/skills/maintain-formal-verification-skill/SKILL.md <- pstack/skills/maintain-formal-verification-skill/SKILL.md
features/skill-library/skills/statechart/SKILL.md <- pstack/skills/statechart/SKILL.md
features/skill-library/skills/statechart/scripts/model/OutputFolder.cfg <- pstack/skills/statechart/scripts/model/OutputFolder.cfg
features/skill-library/skills/statechart/scripts/model/OutputFolder.map.py <- pstack/skills/statechart/scripts/model/OutputFolder.map.mjs
features/skill-library/skills/statechart/scripts/model/OutputFolder.tla <- pstack/skills/statechart/scripts/model/OutputFolder.tla
features/skill-library/skills/statechart/scripts/statechart/chart_to_tla.py <- pstack/skills/statechart/scripts/chart-to-tla.mjs
features/skill-library/skills/statechart/scripts/statechart/cli.py <- pstack/skills/statechart/scripts/statechart.mjs
features/skill-library/skills/statechart/scripts/statechart/compare_charts.py <- pstack/skills/statechart/scripts/compare-charts.mjs
features/skill-library/skills/statechart/scripts/statechart/lib.py <- pstack/skills/statechart/scripts/lib.mjs
features/skill-library/skills/statechart/scripts/statechart/tlc_to_chart.py <- pstack/skills/statechart/scripts/tlc-to-chart.mjs
features/skill-library/skills/statechart/scripts/statechart/tools.py <- pstack/skills/statechart/scripts/lib.mjs, pstack/skills/statechart/scripts/statechart.mjs
features/skill-library/tests/statechart/sync.mmd <- pstack/skills/statechart/scripts/test/sync.mmd
features/skill-library/tests/statechart/upload.mmd <- pstack/skills/statechart/scripts/test/upload.mmd
features/skill-library/tests/statechart_support.py <- pstack/skills/statechart/scripts/test/statechart.test.mjs
features/skill-library/tests/test_statechart_charts.py <- pstack/skills/statechart/scripts/test/statechart.test.mjs
features/skill-library/tests/test_statechart_runs.py <- pstack/skills/statechart/scripts/test/statechart.test.mjs
features/skill-library/tests/test_statechart_specs.py <- pstack/skills/statechart/scripts/test/statechart.test.mjs
features/skill-library/skills/make-bot-ui/SKILL.md <- pstack/skills/make-bot-ui/SKILL.md
features/no-comments/SKILL.md <- pstack/skills/no-comments/SKILL.md, pstack/agents/comment-sicko.md
features/pr-review/SKILL.md <- pstack/skills/interrogate/references/rubric.md, pstack/skills/interrogate/references/code-quality-review.md
features/recall/SKILL.md <- pstack/skills/recall/SKILL.md
features/lessons/skills/reflect/SKILL.md <- pstack/skills/reflect/SKILL.md
features/lessons/skills/reflect/references/divergent-reviewer.md <- pstack/skills/reflect/references/divergent-reviewer.md
features/lessons/skills/reflect/references/judgment-reviewer.md <- pstack/skills/reflect/references/judgment-reviewer.md
features/lessons/skills/reflect/references/synthesizer.md <- pstack/skills/reflect/references/synthesizer.md
features/lessons/skills/reflect/references/tooling-reviewer.md <- pstack/skills/reflect/references/tooling-reviewer.md
features/sharpen/SKILL.md <- pstack/skills/sharpen/SKILL.md
features/show-me-your-work/SKILL.md <- pstack/skills/show-me-your-work/SKILL.md
features/show-me-your-work/scripts/log.sh <- pstack/skills/show-me-your-work/scripts/log.sh
features/arena-swarm/skills/swarm/SKILL.md <- pstack/skills/swarm/SKILL.md
features/tdd/SKILL.md <- pstack/skills/tdd/SKILL.md
features/teach/SKILL.md <- pstack/skills/teach/SKILL.md
features/writing/skills/technical-writing/SKILL.md <- pstack/skills/technical-writing/SKILL.md
features/typescript-best-practices/SKILL.md <- pstack/skills/typescript-best-practices/SKILL.md
features/typescript-best-practices/references/patterns.md <- pstack/skills/typescript-best-practices/references/patterns.md
features/writing/skills/unslop/SKILL.md <- pstack/skills/unslop/SKILL.md
features/why/SKILL.md <- pstack/skills/why/SKILL.md
features/why/references/epistemics.md <- pstack/skills/why/references/epistemics.md
features/why/references/investigator-prompt.md <- pstack/skills/why/references/investigator-prompt.md
features/why/references/source-playbook.md <- pstack/skills/why/references/source-playbook.md
features/why/references/sources/code-archaeology.md <- pstack/skills/why/references/sources/code-archaeology.md
features/why/references/sources/databricks.md <- pstack/skills/why/references/sources/databricks.md
features/why/references/sources/datadog.md <- pstack/skills/why/references/sources/datadog.md
features/why/references/sources/incident-postmortem.md <- pstack/skills/why/references/sources/incident-postmortem.md
features/why/references/sources/linear.md <- pstack/skills/why/references/sources/linear.md
features/why/references/sources/notion.md <- pstack/skills/why/references/sources/notion.md
features/why/references/sources/sentry.md <- pstack/skills/why/references/sources/sentry.md
features/why/references/sources/slack.md <- pstack/skills/why/references/sources/slack.md
features/why/references/synthesizer-prompt.md <- pstack/skills/why/references/synthesizer-prompt.md
```

Each line is a file here and the upstream paths it was written from, at the commit above. A file added from pstack gets a line, and a move of the `Commit:` line follows a read of what changed.

jstack's own: `features/principles/skills/principle-depth-over-breadth/SKILL.md`, `features/skill-library/skills/make-bot-ui/scripts/bot_ui.py`, `features/skill-library/skills/poteto-help/SKILL.md`, `features/skill-library/skills/statechart/scripts/pyproject.toml`, `features/skill-library/skills/statechart/scripts/uv.lock`, `features/skill-library/skills/statechart/scripts/statechart/__init__.py`, `features/skill-library/skills/statechart/scripts/statechart/__main__.py`, `features/skill-library/skills/statechart/scripts/statechart/mapping.py`

The files on that line sit beside the ones taken and are jstack's own: no upstream path fed them, so `jdrift` prints each as `own` and compares nothing for it. `features/principles/skills/principle-depth-over-breadth/SKILL.md` is from the Felix Rieseberg section below. `features/skill-library/skills/poteto-help/SKILL.md` is jstack's own skill, written after the upstream file `pstack/skills/poteto-help/SKILL.md`: it keeps that file's name and its help-only answer, and takes none of its text, so the upstream path stays on the `Not taken:` line below. Its pick comes from `jbriefs pick`, not from a hand-kept table, and it points at the home, crew, scout and expert skills, never at a mode.
`features/skill-library/skills/make-bot-ui/scripts/bot_ui.py` is the server that upstream's make-bot-ui describes in prose, written here so that its tests run it.
`features/skill-library/skills/statechart/scripts/pyproject.toml` with its `uv.lock`, the package's `__init__.py` and `__main__.py`, and `mapping.py`, which loads a mapping file from its path, are the uv project around the Python port of the statechart scripts, which has no such files in Node.

Not taken: `pstack/skills/poteto-help`, `pstack/skills/setup-pstack`, `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`, `pstack/skills/poteto-mode/playbooks/babysit.md`, `pstack/skills/poteto-mode/playbooks/shipping.md`, `pstack/skills/poteto-mode/playbooks/worktree-cleanup.md`

`features/jinstall/skills/setup-pstack/SKILL.md` has the name of `pstack/skills/setup-pstack` and none of its text, so the upstream skill stays on that line. Upstream writes a Cursor rule of a model and a budget for each role, up to `max`. Here the skill runs `install.sh --setup`, which writes `~/.config/jstack/roles` with every role `inherit`. It keeps upstream's shape: it detects, loads what is there, and leaves a rerun idempotent.

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
- Changed here: reworded as two things a reviewer looks for in the changed lines. The rest of the file is not taken: its other three sections are covered by the principles, and "If uncertain, ask" is against `features/principles/skills/principle-never-block-on-the-human/SKILL.md`.
- License: the skill's frontmatter and the README say MIT. The repo has no license file, so there is no notice text to copy.

## axe-core

`features/jbus/tests/fixtures/jbus-view/axe.min.js` is axe-core, by Deque Systems, the accessibility engine the page tests of `jbus view` run in the browser. Only the tests read it: the view never serves it.

- Source: https://github.com/dequelabs/axe-core
- Version: 4.14.0, the file `axe.min.js` of the package `https://registry.npmjs.org/axe-core/-/axe-core-4.14.0.tgz`, integrity `sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==`
- Changed here: nothing. The file is taken whole, with its notice.
- License: the Mozilla Public License 2.0, whose text is at https://mozilla.org/MPL/2.0/, as the notice at the top of the file says.

## Atkinson Hyperlegible Next

`features/jbus/src/jbus/view/font.woff2` is Atkinson Hyperlegible Next, by The Atkinson Hyperlegible Next Project Authors, the one font of the page `jbus view` serves. The view serves it at `/font.woff2`.

- Source: https://github.com/googlefonts/atkinson-hyperlegible-next
- Version: commit 7925f50f649b3813257faf2f4c0b381011f434f1, the file `fonts/webfonts/AtkinsonHyperlegibleNext[wght].woff2`, 48,188 bytes, sha256 `abde1ad5cf78b9ac575ef90d991f2e9101eb0b3b6668bde9a00e2e1e27d99afd`
- Changed here: nothing. The file is taken whole and renamed.
- License: the SIL Open Font License 1.1, "Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors". Its text, the repo's `OFL.txt`, is shipped beside the font as `features/jbus/src/jbus/view/OFL.txt`.

## Felix Rieseberg

`features/principles/skills/principle-depth-over-breadth/SKILL.md` and the four questions of the home's deeper-version step (`features/home/skills/home/handing-a-task-to-a-crewmate.md`) are built on the Depth type of Felix Rieseberg's four types of ambition (Speed, Altitude, Depth and Range).

- Source: Felix Rieseberg, "How to be more ambitious: A tutorial for humans with models", 2026-10-13: https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/
- Taken from: the prompt the post gives for Depth, as the home step's four questions, and the Depth moves the principle names: the instruments the best in the field use, reproducing a number from the raw data, an ambitious target said to be reasonable, and an outside judge in place of the model judging itself.
- Changed here: the home answers each question for this repo and this machine, by path, command or query, and writes each answer on the line of the brief it names. Altitude and Range are not taken.
- Ties to pstack: since #729, pstack's `/sharpen` is the same prompt, and jstack's copy of it (the pstack section above) is the skill a user types for it. jstack's own `deeper` skill, which quoted the prompt whole, is retired.
- License: none is stated on the post. The prompt is quoted with this credit, and the rest is jstack's own text.
