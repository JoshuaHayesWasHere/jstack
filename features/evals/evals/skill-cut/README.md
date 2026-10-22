# The skill-cut eval

Does cutting text out of a skill, a reference or a principle change what an agent does under it? pstack's #634 cut sections "agents follow just as well without the text", and named no evidence. This eval is that evidence for jstack: it runs the same questions over a file as it is on a base revision and as it is on a variant revision, and says whether the variant regresses. It lands before any cut, and each cut branch reruns it with one command.

## What it does

Two families of cases, both committed in `cases/` before the first run.

- **`lead`**: a pull request review's lead judgment, from real reviews (`cases/lead/<slug>.md`). Each case is one pull request's first review: the intent the reviewer was given and the readers' findings, word for word, as the reviewer thread holds them, with the private patterns of `jleak` taken out. The model is the lead: it gets step 5 of `skills/interrogate/SKILL.md` and `skills/interrogate/references/lead-judgment.md` as they are at the revision under test, judges the findings, and buckets each one as Act on, Consider, Noted or Dismissed. The key (`cases/lead/<slug>.key.json`) is that review as it shipped in the brief's `## Review` section: each finding was sent (Act on or Consider become the section's `Findings:` lines), noted (counted, not listed) or dismissed (one line each), and whether the crewmate fixed it. A finding the shipped review dropped as outside the diff is in the case and not scored. Each key entry says which line of the shipped Review it was matched to, so a person can check it.
- **`steps`**: a thread in a state, and the question "what do you do next" (`cases/steps.json`). Three or more scenarios for each file the cut briefs name: the home, crew, scout, pr-review, handoff and expert skills, and the two principles #634 cuts (`type-system-discipline`, `migrate-callers-then-delete-legacy-apis`). The model gets the file as it is at the revision under test, the state, and the question. The key is the step or command the file prescribes, as prose (`expect`) and as regular expressions (`must`, all of which must match).

Each run has three arms: **base**, **base again** (the same prompts at the same revision, which is the noise floor), and **variant**. Every case runs three times in each arm. The candidate is `claude-opus-5-5` at medium effort with no tools, the model homes, crewmates and reviewers run on.

The files under test are read from the two revisions with `git show <rev>:<path>`, never from the working tree.

## Blind scoring

Each answer is saved in `run-<name>/answers.json` under a random id. Which case it answers is in `run-<name>/which.json`, and which arm and trial wrote it only in `run-<name>/key.json`. `score.py` scores an answer from its text and its case's key alone: it never sees the arm, and it is a script, not a model.

- `lead`: the answer ends with a `BUCKETS` block, one line per finding id. A finding scores 1 when the answer sends it (Act on, Consider) and the shipped review sent it, or holds it back (Noted, Dismissed) and the shipped review held it back; else 0. The answer's score is the mean over the case's scored findings.
- `steps`: 1 when every `must` expression matches the answer, else 0.

A model judge, `claude-sonnet-5-5` at medium effort, is used only for an answer the key cannot settle, and is told neither the arm nor the revision:

- a `lead` answer that leaves a finding with no bucket line `score.py` can read: the judge reads the answer and says which bucket it gave that finding, or none;
- a `steps` answer where a `must` expression fails while the case's `near` expression matches: the answer is about the right thing in words the expression did not foresee, and the judge says whether it does what `expect` says.

What the judge said is kept in `run-<name>/judge.json`, and `results.md` counts the answers it settled. A rescore of a kept run reads that file and calls no model.

## The rule

Fixed before the first run, and not changed after it. For each family, a case's score in an arm is the mean of its trials, and an arm's score is the mean over the family's cases.

- The **noise floor** of a family is the base-against-base spread: the absolute difference between the base arm's score and the base-again arm's.
- The variant **does not regress** in a family when both hold:
  1. its score is no lower than the base arm's score minus the noise floor;
  2. the two-sided sign test of the variant against base over the family's cases (a case counts as a loss when its variant score is below its base score, a win when above, ties left out) does not show a loss under 0.05: it is not true that losses outnumber wins with p under 0.05.
- The variant does not regress when it does not regress in either family. Otherwise the variant **regresses**, and that is the finding: the eval is not tuned until it passes.

The `lead` family reads only the interrogate step and its reference, and the `steps` family only its eight files: a variant that changes none of the files a family reads ties base on that family by construction, and `results.md` says which files differ between the two revisions.

## Run it

From the root of the repo, on a machine with `claude` and the private patterns of `jleak`:

```sh
uv run python features/evals/evals/skill-cut/eval.py --base main --variant HEAD
```

It resolves the two revisions, writes a new run, `run-<the variant's first 12 characters>/` or the name `--name run-<name>` gives, so that two branches that each add a run never write the same directory, in one rename once every answer and the key are written (a failed call leaves nothing, and no kept run is touched), scores it, asks the judge for what the key cannot settle, and writes `results.md`. It makes 3 x 3 calls per case (about 400 for the committed cases), six at a time. A cut branch commits the run it adds.

`uv run python features/evals/evals/skill-cut/eval.py --run run-1` rescores and reports a kept run with no model call: its `results.md` comes out byte for byte as committed. A run is scored only against the cases it was answered against: its `run.json` holds a hash of `cases/`, and `--run` refuses a run whose cases have changed since. A change to a case is a new case set, and a new run from base.

`uv run python features/evals/evals/skill-cut/eval.py cases <staging dir>` rebuilds `cases/lead/` from the JSON files the extraction wrote (one per pull request, `<slug>.json`), with the private patterns taken out. The extraction itself read each reviewer thread with `t3_thread_read`, and the intent from `/tmp/pr-review-<slug>.*/intent`, which a reboot empties: the committed cases are the record.

## Limits

- One model, three trials a case and arm. The noise floor is one draw of base against base, so a run where the two base arms happen to agree closely is a strict one: a second run is the check on a verdict that turns on a small gap.
- The `lead` key is one lead's judgment, made with the repository open and the conversation in view. The model here gets the findings and the intent and no code, so it cannot trace a call site, and its agreement with the key is bounded below one by what it was not given. The eval reads the change in agreement between arms, not the agreement itself.
- A key that splits sent from held back says nothing on Act on against Consider, or Noted against Dismissed: the shipped review lists the sent ones with a severity, and counts the noted ones without naming them.
- A `steps` expression checks that the answer names the prescribed step, not that the thread would then do it right. A scenario is a single question with no tools: it tests whether the text is followed when asked, not over a whole session.
- The cases are this repo's reviews and threads, from the weeks before the first run.

## Result

See each run's `results.md`. Run 1 (2026-10-16) is main (`c228ac6`) against main with #634's cuts applied to jstack's copies (`4003f32`, a local commit kept as `refs/jstack/skill-cut-eval/variant-634`, its diff in `run-1/variant.patch`): `skills/interrogate/references/lead-judgment.md`, `principles/type-system-discipline.md` and `principles/migrate-callers-then-delete-legacy-apis.md`. `playbooks/swarm.md` is jstack's own rewrite and is not cut, as the pin brief says. 396 answers, 9 settled by the judge.

**By the rule, the cut does not regress, in either family.**

| Family | Base | Base again | Variant | Noise floor | Variant higher / tied / lower, p |
|---|---|---|---|---|---|
| `lead` (17 reviews, 223 findings) | 0.729 | 0.710 | 0.739 | 0.019 | 8 / 4 / 5, 0.581 |
| `steps` (27 scenarios) | 0.963 | 0.963 | 0.963 | 0.000 | 0 / 27 / 0, 1.000 |

What limits these numbers:

- **`lead` agrees with the shipped review on about three findings in four, in every arm.** It is bounded by what the model is not given: the shipped lead had the code and the conversation, and this one has the intent and the findings. The gap between arms (variant 0.010 above base) is half the gap between the two base arms (0.019), and single cases move up to 0.62 between trials of one arm (`ci-self-hosted`), so the run cannot tell the cut from no cut on this family. It would show a drop of more than about 0.02 on the mean, or a loss on most cases.
- **`steps` is at its ceiling.** 26 of 27 scenarios scored 1 in every trial of every arm, the variant's cut principles included: with the "illegal states", "exhaustive matching" and "Rule" bullets gone, the answers still wrote a sum type, a `never` check and deleted the old API (read in `run-1/answers.json`, not inferred from the score). So this family shows a regression only as a fall from 1, and says nothing finer.
- **One case is a dud.** `scout-no-launch` scored 0 in all nine trials. Every answer went straight to "End" and started no crewmate, which is what the skill asks, but did not say in words that the home starts it, and the judge held the answer to the `expect` text. It is the same in each arm, so it moves no comparison. It is kept as it was fixed before the run.
- In run 1 the `steps` files of the six own skills are the same at both revisions: those scenarios are the baseline that skill-cut-own's run compares against.
