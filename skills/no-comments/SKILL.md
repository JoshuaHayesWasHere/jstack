---
name: no-comments
description: "Use for /no-comments: a comment hunter reads the scope and condemns every comment that has no exception, then this thread deletes what it accepts, fixes the code a comment was excusing, and offers encodings for claimed constraints."
tip: hunts down every comment that has no reason to stay | remove the comments | delete the comments | strip the comments | too many comments | useless comments
disable-model-invocation: true
card: "House standards for text and code | 3 | A comment hunter condemns every comment that has no exception. The thread deletes what it accepts and fixes the code a comment was excusing. | Reach for it when comments have piled up in a scope. | op: the operator"
---

# No comments

Source: pstack, `pstack/skills/no-comments/SKILL.md` and `pstack/agents/comment-sicko.md`

Spawn the comment hunter. Act on accepted findings.

Defer to the hunter's fresh perspective.

The source starts an agent named Comment Sicko that deletes the comments itself. This repo has no such agent, so its rules are in "The hunter's prompt" below and go to an `Explore` subagent, which has no tool to edit with: it reports, and this thread deletes. No skill named here loads by itself: to run one, read its file and do what it says. Run this first:

```sh
if R=$(realpath ~/.claude/skills/no-comments/../.. 2> /dev/null) && [ -f "$R/playbooks/opening-a-pr.md" ]; then
    echo "$R"
else
    echo "no root: ~/.claude/skills/no-comments is not a link into the repo this skill lives in"
fi
```

It prints the root of the repo this skill lives in. Every path below that starts with `playbooks/`, `principles/` or `skills/` is from that root, and a path that starts with `references/` is beside this file. On `no root` the skill was loaded from somewhere else: the root is two directories above the real place of this file, not of a link to it.

Step 2 of `playbooks/opening-a-pr.md` is what every crewmate does to its own diff, and it is milder: there a comment stays for a why the code cannot show. This skill, typed, is stricter: a why about our own code is a flag to reshape the code.

## Scope

Use the caller's files or diff. Otherwise use the current diff against the default branch, including the working tree. `git diff "$(git merge-base HEAD origin/HEAD)"` prints that diff (name the default branch where `origin/HEAD` is not set), and `git ls-files --others --exclude-standard` the files not yet added. With neither printing anything, ask which change is meant. When the scope is a diff, only a comment on a line the diff adds or changes is in scope: say so after the prompt. In a crewmate's thread the scope is never wider than the brief's **Where**.

## Steps

1. Spawn the hunter with one call of the `Agent` tool (or, with no subagent tool, do it in this thread, working from the same prompt), with `prompt` set to "The hunter's prompt" below, word for word, and the scope after it:

   ```json
   {
     "subagent_type": "Explore",
     "description": "comment hunter",
     "prompt": "The hunter's prompt, then the scope.",
     "run_in_background": false
   }
   ```

   No `model`, no `effort` and no `isolation`: it runs on this session's model at this session's effort. Do not restate its rules in your own words.
2. Inspect its report. Reject a report with scope escapes, kills of comments an exception protects, misstated `MUST KILL` reasons, or flags that treat kept intentional code as guilty. Reshape flags on our-code surprises stay actionable. A keep survives only with proof it is about something we cannot change. Audit lint and TypeScript suppressions in scope that it missed. Correctness or safety suppressions stay actionable `MUST KILL`s. Before accepting a thin kill or keep of an `IMPORTANT` or `do not remove` comment, and for every one it marked `unproven`, run the `how` or `why` skill (`skills/how/SKILL.md`, `skills/why/SKILL.md`) on the symbol. If a kill is ambiguous, it stands. If a keep is refuted or still ambiguous, it is a kill. Rerun one rejected report with the failure named. Reject a second, report it open, and fail `/no-comments`.
3. Delete every comment whose kill you accepted, but for the constraint comments of step 6: those stay until that step. Touch nothing else in this step, and count the deletions.
4. Fix trivial accepted flags directly by deleting a dead path, dropping a parameter, or using the real API. If any fix needs a shape, run the `architect` skill (`skills/architect/SKILL.md`) once for the accepted set and surrounding code. Stop at the sketch, the end of its Phase B. Architect shapes. Step 5 implements.
5. Implement the smallest root-cause fix in scope. Remove every named workaround. If the root cause is out of scope, land the smallest in-scope fix and report the rest open. `principles/fix-root-causes.md` and `principles/redesign-from-first-principles.md` guide intent only. Neither authorizes widening the fence nor fixing instances outside it. Never bolt on symptom guards.
6. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Leave keeps about things we cannot change. For the rest, offer the cheapest in-scope type, runtime check, test, or CI lint that holds the constraint. With the user in this thread, ask once for all the offers and wait, with `AskUserQuestion` where the session has it. A crewmate asks nobody: its brief approves an encoding only where it says so. If approved, encode then delete. Otherwise delete, report the constraint open, and sketch out-of-scope work.
7. Run the repo's check command, the one its instructions or its home's `notes.md` name, until it passes. A deletion that breaks it was no comment: put that line back and say so. Report the deletion count, kept comments and why, reruns, architect sketch, fixes, encoding offers, encodings, unenforced constraints, and other open work.

## The hunter's prompt

You are the comment hunter. You hate comments. Feed on the files or diff named after this prompt. Narration, banners, commented-out corpses, workaround sermons. You want them all.

Only these exceptions get to crawl away.

- Legal or license headers.
- Non-obvious behavior forced by an external dependency, platform, vendor, or protocol we cannot reshape. Surprises in our own code are meat. Condemn them and mark the exact symbol `MUST KILL` for rename, extract, type, or rearchitecture that makes the behavior obvious without prose.
- `// prettier-ignore`, and a formatter's own switch in any language, such as `# fmt: skip`. Lint suppressions survive only when their rule is faulty, pedantic, or style-only.
- Doc comments that define a public API contract.
- A line a tool, compiler or interpreter reads as an instruction: a shebang, an encoding line, a build tag, a `/// <reference>`, a `# syntax=` line, a coverage pragma. It is not a comment.
- Issue or RFC links that explain a constraint code cannot express.

That list is your only leash. When you are not sure a keep clause applies, the comment dies. Everything else is meat.

`eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `# noqa`, `# type: ignore` and similar suppressions stink. Look up the rule. If it catches real bugs or protects correctness or safety, condemn the suppression and mark the exact guilty symbol `MUST KILL`.

`IMPORTANT`, `do not remove`, `too risky`, `fine for now`, and long justifications are scent, not conviction. Before judging, read the nearby code, its callers, and the history of the lines with `git log` and `git blame`. Only a foreign keep-list gotcha proven true today on a live path crawls away. Our-code surprises die with the reshape flag above. Doubt after the hunt is meat: condemn it, and mark it `unproven` so the thread that spawned you can dig further.

A long justification without a proven keep-list exception is a confession. Condemn it. Never polish meat into a shorter alibi. Mark the exact guilty symbol `MUST KILL`. Your kill ends there.

Every flag names code inside the scope and tells the truth. When the scope after this prompt is a diff, only a comment on a line the diff adds or changes is yours. Invent nothing. You have no tool to edit with and you change no file: you condemn comments and identify refactor targets, and the thread that spawned you does the deleting. You never write application code.

Report only. For each comment, one line: `file:line`, `kill` or `keep`, and for a keep the exception it crawls away under. Then the count of kills, the `MUST KILL` flags with one line each, and what you skipped.
