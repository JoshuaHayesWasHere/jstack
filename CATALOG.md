# Catalog

This page lists what every feature holds, in one place.
Each feature declares its own in `features/<name>/feature.json` and the files under its folder, and `python3 scripts/generate-jstack-trees.py` writes the two tables below from them.
No feature owns this page.
A new skill, playbook or hook changes only its own feature and the generated files.

## Every skill, principle and playbook

This table lists each feature's skills, principles and playbooks, with a link to each file.
[Playbooks, principles and templates](features/home/docs/playbooks.md) says how a brief names one.

<!-- generated: catalog by scripts/generate-jstack-trees.py from features/*/feature.json; do not edit, rerun it -->
| Feature | What it does | Skills and principles | Playbooks |
|---|---|---|---|
| `architect` | Sketches types, signatures and module structure before any code. | [architect](features/architect/SKILL.md) |  |
| `arena-swarm` | Runs one task as several threads that do not see each other, and judges or merges what they make. | [arena](features/arena-swarm/skills/arena/SKILL.md), [swarm](features/arena-swarm/skills/swarm/SKILL.md) | [arena](features/arena-swarm/skills/arena/playbooks/arena.md), [swarm](features/arena-swarm/skills/swarm/playbooks/swarm.md) |
| `automate-me` | Turns how you work into a skill named `<you>-mode`, such as `jay-mode`, that agents follow. | [automate-me](features/automate-me/SKILL.md) |  |
| `benchmark-checklist` | Vets a measured number before it is reported or acted on. | [benchmark-checklist](features/benchmark-checklist/SKILL.md) |  |
| `bro` | Restates the last message in plain words, with no jargon. | [bro](features/bro/SKILL.md) |  |
| `crew` | The crewmate: does the one task of a brief in its own worktree and opens its pull request. | [crew](features/crew/SKILL.md) | [autonomous-run](features/crew/playbooks/autonomous-run.md), [bug-fix](features/crew/playbooks/bug-fix.md), [feature](features/crew/playbooks/feature.md), [hillclimb](features/crew/playbooks/hillclimb.md), [pause-safely](features/crew/playbooks/pause-safely.md), [perf-issue](features/crew/playbooks/perf-issue.md), [prototype](features/crew/playbooks/prototype.md), [refactoring](features/crew/playbooks/refactoring.md), [runtime-forensics](features/crew/playbooks/runtime-forensics.md), [visual-parity](features/crew/playbooks/visual-parity.md) |
| `evals` | Measures a skill's effect against a baseline, with runs a grader scores. |  | [eval](features/evals/playbooks/eval.md) |
| `expert` | Makes a thread the expert of one subject, which answers from its context pack. | [expert](features/expert/SKILL.md) | [expert-answer](features/expert/playbooks/expert-answer.md), [expert-check](features/expert/playbooks/expert-check.md), [expert-refresh](features/expert/playbooks/expert-refresh.md), [expert-research](features/expert/playbooks/expert-research.md), [expert-study](features/expert/playbooks/expert-study.md) |
| `grilling` | Questions a plan until nothing is left assumed, with a page for each round. | [grilling](features/grilling/SKILL.md) |  |
| `home` | The home: plans with the user, writes each brief and launches its thread. | [handoff](features/home/skills/handoff/SKILL.md), [home](features/home/skills/home/SKILL.md), [new-home](features/home/skills/new-home/SKILL.md), [nohome](features/home/skills/nohome/SKILL.md) | [autopilot-full](features/home/skills/home/playbooks/autopilot-full.md), [multi-phase-plan](features/home/skills/home/playbooks/multi-phase-plan.md), [orchestrate](features/home/skills/home/playbooks/orchestrate.md), [session-pickup](features/home/skills/home/playbooks/session-pickup.md) |
| `how` | Explains how a subsystem works before you change it. | [how](features/how/SKILL.md) |  |
| `in-your-own-words` | Plays back what you are after before any work starts. | [in-your-own-words](features/in-your-own-words/SKILL.md) |  |
| `jinstall` | Installs, checks and removes jstack on a machine: install.sh in a checkout, and the jinstall command from a release. | [setup-pstack](features/jinstall/skills/setup-pstack/SKILL.md) |  |
| `ketchup` | Catches you up on this chat since your last message. | [ketchup](features/ketchup/SKILL.md) |  |
| `lessons` | Turns a mistake agents keep making into a rule they cannot break. | [correct](features/lessons/skills/correct/SKILL.md), [reflect](features/lessons/skills/reflect/SKILL.md) | [correct](features/lessons/skills/correct/playbooks/correct.md) |
| `no-comments` | Hunts down every comment that has no reason to stay. | [no-comments](features/no-comments/SKILL.md) |  |
| `pr-review` | Has a finished pull request reviewed in a fresh thread. | [pr-review](features/pr-review/SKILL.md) |  |
| `principles` | One skill per working principle, which a playbook step cites. | [principle-attack-the-premise](features/principles/skills/principle-attack-the-premise/SKILL.md), [principle-boundary-discipline](features/principles/skills/principle-boundary-discipline/SKILL.md), [principle-build-the-lever](features/principles/skills/principle-build-the-lever/SKILL.md), [principle-depth-over-breadth](features/principles/skills/principle-depth-over-breadth/SKILL.md), [principle-encode-lessons-in-structure](features/principles/skills/principle-encode-lessons-in-structure/SKILL.md), [principle-exhaust-the-design-space](features/principles/skills/principle-exhaust-the-design-space/SKILL.md), [principle-experience-first](features/principles/skills/principle-experience-first/SKILL.md), [principle-explain-the-number](features/principles/skills/principle-explain-the-number/SKILL.md), [principle-fix-root-causes](features/principles/skills/principle-fix-root-causes/SKILL.md), [principle-foundational-thinking](features/principles/skills/principle-foundational-thinking/SKILL.md), [principle-guard-the-context-window](features/principles/skills/principle-guard-the-context-window/SKILL.md), [principle-laziness-protocol](features/principles/skills/principle-laziness-protocol/SKILL.md), [principle-make-operations-idempotent](features/principles/skills/principle-make-operations-idempotent/SKILL.md), [principle-migrate-callers-then-delete-legacy-apis](features/principles/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md), [principle-minimize-reader-load](features/principles/skills/principle-minimize-reader-load/SKILL.md), [principle-model-the-domain](features/principles/skills/principle-model-the-domain/SKILL.md), [principle-never-block-on-the-human](features/principles/skills/principle-never-block-on-the-human/SKILL.md), [principle-outcome-oriented-execution](features/principles/skills/principle-outcome-oriented-execution/SKILL.md), [principle-prove-it-works](features/principles/skills/principle-prove-it-works/SKILL.md), [principle-redesign-from-first-principles](features/principles/skills/principle-redesign-from-first-principles/SKILL.md), [principle-separate-before-serializing-shared-state](features/principles/skills/principle-separate-before-serializing-shared-state/SKILL.md), [principle-sequence-verifiable-units](features/principles/skills/principle-sequence-verifiable-units/SKILL.md), [principle-subtract-before-you-add](features/principles/skills/principle-subtract-before-you-add/SKILL.md), [principle-test-behavior-not-implementation](features/principles/skills/principle-test-behavior-not-implementation/SKILL.md), [principle-type-system-discipline](features/principles/skills/principle-type-system-discipline/SKILL.md) |  |
| `recall` | Rebuilds where you left off from your chat history and the home's record. | [recall](features/recall/SKILL.md) |  |
| `scout` | The scout: answers a question with read-only tool calls before a task is briefed. | [scout](features/scout/SKILL.md) | [investigation](features/scout/playbooks/investigation.md), [trace-forensics](features/scout/playbooks/trace-forensics.md) |
| `sharpen` | Rewrites a task's prompt to ask for the deeper version, and does not do the task. | [sharpen](features/sharpen/SKILL.md) |  |
| `show-me-your-work` | Keeps a decision log you can review after stepping away. | [show-me-your-work](features/show-me-your-work/SKILL.md) |  |
| `skill-library` | The skills any thread may load by name, and the tips hook that suggests them. | [blast-radius](features/skill-library/skills/blast-radius/SKILL.md), [create-formal-verification-skill](features/skill-library/skills/create-formal-verification-skill/SKILL.md), [create-verification-skill](features/skill-library/skills/create-verification-skill/SKILL.md), [figure-it-out](features/skill-library/skills/figure-it-out/SKILL.md), [interrogate](features/skill-library/skills/interrogate/SKILL.md), [maintain-formal-verification-skill](features/skill-library/skills/maintain-formal-verification-skill/SKILL.md), [maintain-verification-skill](features/skill-library/skills/maintain-verification-skill/SKILL.md), [make-bot-ui](features/skill-library/skills/make-bot-ui/SKILL.md), [poteto-help](features/skill-library/skills/poteto-help/SKILL.md), [statechart](features/skill-library/skills/statechart/SKILL.md) | [authoring-a-playbook](features/skill-library/playbooks/authoring-a-playbook.md), [authoring-a-skill](features/skill-library/playbooks/authoring-a-skill.md) |
| `tdd` | Fixes a bug test-first, with a regression test that fails before the fix. | [tdd](features/tdd/SKILL.md) |  |
| `teach` | Explains a body of work plainly until you understand it. | [teach](features/teach/SKILL.md) |  |
| `typescript-best-practices` | Loads the TypeScript rules before a .ts or .tsx edit. | [typescript-best-practices](features/typescript-best-practices/SKILL.md) |  |
| `why` | Finds why the code is the way it is, with cited evidence. | [why](features/why/SKILL.md) |  |
| `writing` | Holds every page and pull request to one writing standard. | [technical-writing](features/writing/skills/technical-writing/SKILL.md), [unslop](features/writing/skills/unslop/SKILL.md) | [opening-a-pr](features/writing/playbooks/opening-a-pr.md) |
<!-- generated: end -->

## Hooks

This table lists each hook, status line and git hook that the install adds, and the feature whose `feature.json` declares it.
The feature's own docs say what its script does and show the entry the install writes.
[jinstall](features/jinstall/docs/jinstall.md#hook-entries) says which file of each harness the entries go in.

<!-- generated: hooks by scripts/generate-jstack-trees.py from features/*/feature.json; do not edit, rerun it -->
| Hook | Script | Harnesses | Feature |
|---|---|---|---|
| `SessionStart`, matcher `startup` | [features/home/hooks/home-start.sh](features/home/hooks/home-start.sh) | claude-code, codex | `home` |
| `PreToolUse` | [features/home/hooks/home-gauge.sh](features/home/hooks/home-gauge.sh) | claude-code | `home` |
| `PostToolUse` | [features/home/hooks/home-gauge.sh](features/home/hooks/home-gauge.sh) | claude-code | `home` |
| `PreToolUse`, matcher `mcp__t3[-_]code__t3_thread_send`, refuses | [features/home/hooks/agent-sends.sh](features/home/hooks/agent-sends.sh) | claude-code | `home` |
| the status line | [features/jgauge/hooks/limits.sh](features/jgauge/hooks/limits.sh) | claude-code | `jgauge` |
| `PreToolUse`, matcher `Bash`, refuses | [features/jleak/hooks/outbound-command.sh](features/jleak/hooks/outbound-command.sh) | claude-code | `jleak` |
| `PreToolUse`, matcher `Bash`, refuses | [features/jleak/hooks/ai-trailer.sh](features/jleak/hooks/ai-trailer.sh) | claude-code, codex | `jleak` |
| `PreToolUse`, matcher `Bash|Write|Edit|MultiEdit|NotebookEdit`, refuses | [features/jleak/hooks/infra-files.sh](features/jleak/hooks/infra-files.sh) | claude-code | `jleak` |
| git `pre-push` | [features/jleak/hooks/pre-push.sh](features/jleak/hooks/pre-push.sh) | git | `jleak` |
| git `commit-msg` | [features/jleak/hooks/commit-msg.sh](features/jleak/hooks/commit-msg.sh) | git | `jleak` |
| `UserPromptSubmit` | [features/skill-library/hooks/skill-tips.sh](features/skill-library/hooks/skill-tips.sh) | claude-code | `skill-library` |
<!-- generated: end -->
