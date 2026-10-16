# pstack-depth-style

## Intent

Task: the relay of the user's word 79eb162adcb3: "write the depth-over-breadth principle in #633's reasoning-not-rules style". It was written by deeper-skill (#10) before #633 was known
Done when:
- `principles/depth-over-breadth.md` reads like the four principles of #633: the reasoning (why depth beats extra scope, and how to tell) rather than a list of rules, with its boundary and its pairs kept, in jstack's form (first paragraph, relative links, card footer)
- `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: the principle and card tests, and a side by side in the Result of one #633 principle and this one
Size: S
Where: `principles/depth-over-breadth.md`, its card and any line that quotes it
Do not touch: the skill /deeper
Decisions: the user, 2026-10-15 09:44 ET, word 79eb162adcb3, from Sous Chef's Grok Bot chat: "Yes, send it", approving the pstack catch-up (bring jstack up to current pstack, the #633 principle rewrite and every other upstream update it is missing), in the audit's priority order. Upstream is cursor/plugins `pstack/` at e5136d8; read it from a fresh clone in a temporary directory (`git clone --filter=blob:none`), never from memory. Keep jstack's local form where the audit says so. The split is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/pstack-drift-2026-10-15.md, the relay notes at its top, and ~/.local/state/home/jstack/scouts/deeper-design.md section 2

Scope of this review. It overrides anything above that reads wider.
Review only the lines this pull request changes: its diff against its base branch.
Report a finding only when it is about a changed line, or about something a changed line breaks. Give every finding the file and line of the changed line, and when the damage is elsewhere, say where in the text.
For a finding about a removed line, give the line that now sits just before or just after where it was. For a finding about what the change as a whole lacks (a "Done when" line it does not meet, a test it does not have), give no file and say so.
Do not report and do not fix a bug or weakness in code this pull request did not change, however real: those are handled elsewhere.
Do not ask for work beyond what the task above needed.
Read the changed code the way a tech lead would, and answer these about it:
1. Does it meet the task and every "Done when" line above? Name each line it does not meet.
2. Is it tested properly? A test must execute something. A new or changed test that only matches wording and executes nothing is a warning, and the remedy to name is a test that executes (one that runs the shell, parses the block and checks it, or runs the script), not deleting the test.
3. Does it do what the user wanted, not only what the words of the task say?
4. Is it correct? Look for these too, in the changed lines:
   - Run twice, or after a run that crashed halfway: if what happens depends on the state left behind, a reconciliation step is missing.
   - Shared state: where several actors can touch the same files, branches or data, is access kept in step by structure (a lock, sequential phases, one owner), or only by a convention that will not hold?
   - A rule in prose: a comment or convention someone has to remember, where a type, a lint rule or a runtime check would make the wrong thing impossible.
   - An old path kept beside a new one: with no outside consumer, the callers move and the old path goes in the same change.
   - A proxy: a check that reads a file's age, a cached value or a self-report, and not the real value or the output itself.
   - A bug fix with no test for the bug.
5. Could it be done more simply or cheaply? Look for these too, in the changed lines:
   - Be ambitious about structural simplification. Do not stop at "this could be a bit cleaner." Look for reframings that make whole branches, helpers, modes, conditionals or layers disappear. Assume a "code judo" move is often available: one that uses the existing architecture more effectively and makes the change dramatically simpler. If you can delete complexity rather than rearrange it, push hard for that.
   - A file the change pushes from under 1,000 lines to over 1,000: should it be split first?
   - Ad-hoc conditionals, special cases or one-off branches put into an existing flow, where a helper or a module of its own would hold the logic.
   - A thin abstraction, identity wrapper or pass-through helper that adds indirection and no clarity.
   - Logic outside its canonical layer: feature logic in a shared path, or a one-off where an existing helper would do.
   When the remedy for one of these would change a file outside the "Where" line above, say so in the finding: it is noted for later, not asked for in this pull request.
6. Does it leave everything it did not mean to change unaffected? Look for these too, in the changed lines:
   - A changed line that does not trace to the task: adjacent code, comments or formatting "improved" in passing, or a refactor of something that was not broken. Every changed line should trace directly to the task above.
   - A removal the change did not earn: an import, variable or function that was already unused before this change is named in the finding, not deleted. What the change itself made unused goes in the same change, and one left behind is a finding too.
7. Does it change a file outside the "Where" line above? Each such file is a finding.

## Findings

### A1

### 1. [Warning] The test for telling depth from breadth contradicts the principle's own third question
**Location**: principles/depth-over-breadth.md:15, which conflicts with line 13
**Finding**: Line 15 says "Depth changes those three answers and nothing else" and gives this test: "hold the plan against the task's 'Done when': deeper work reaches the same outcome from better ground, and wider work changes the outcome." But line 13 tells the reader to change what proves the work is done. It asks for a test that fails before and passes after, a measured number against a stated target, and "a target the field would call ambitious." Those changes rewrite what the "Done when" asks for. One example is "p95 under 200ms, measured by hyperfine with 10 runs" replacing "the crewmate confirms it is faster."
**Evidence**: Under line 15's test, the deepest answer the principle recommends counts as "wider." A home that applies the test literally will file the outside judge or the ambitious target under "Noticed" as breadth. That is the opposite of what the principle and `/deeper` answer 4 ask for (skills/deeper/SKILL.md:27 says "Ask for an unreasonable target"). The old text did not have this problem: it defined breadth only as "a new deliverable."
**Suggestion**: Base the test on deliverables, not outcomes. For example: "deeper work keeps the deliverables and changes only where the work starts, what it measures with, and what proves it; wider work adds a deliverable."

### A2

### 2. [Nit] The same point is made twice within six lines
**Location**: principles/depth-over-breadth.md:7 and :12; also :5 and :7
**Finding**: Line 7 says "Naming a method without the command that runs it here is still words." Line 12 says it again: "A plan that names the method and not the command has the vocabulary and not the instrument." Lines 5 and 7 also overlap: "Deeper work finds what was not already known. Wider work restates it" is followed straight away by "An agent that starts from it can only agree or disagree in words."
**Evidence**: The file grew from 544 to 710 words and is now the longest of the 25 principles (type-system-discipline.md has 576, and the four #633 rewrites have at most 475). Much of the growth is these repeats. That cuts against minimize-reader-load and against the style of the #633 principles the task points to.
**Suggestion**: Keep each point in one place. The "names the method, not the command" point belongs in the bullet at line 12. Drop the sentence at line 7 and the closing restatement at line 5.

### A3

### 3. [Nit] The `/deeper` sentence is hard to parse
**Location**: principles/depth-over-breadth.md:17
**Finding**: "`/deeper` asks these, after what a top professional would do that is not asked, as four questions of a task or a draft brief…" The clause "after what a top professional would do that is not asked" sits between the verb and its complement. A reader has to work out that "these" means the three questions and that the clause is the first of the four.
**Suggestion**: "`/deeper` asks these three questions, after a first one (what a top professional would do here that is not asked), and rewrites the prompt to ask for the answers."

### A4

### 4. [Nit] The card still sums up the three "X over Y" bullets the body no longer has
**Location**: principles/depth-over-breadth.md:23 (unchanged, but the task's "Where" line names "its card")
**Finding**: The card reads "raw data over summaries, the expert's instruments over their words, an outside judge over self-assessment." The body now frames the same content as three questions (where it starts, what it measures with, what says it is done), and none of those phrases appear in it any more. A reader who goes from the card to the principle will not find the card's words there.
**Evidence**: The task asked for a review of the card and of every line that quotes the principle. The card was left as it was, and so was its copy in docs/jstack-explained.html:735. The meaning still matches, so this is about consistency, not correctness.
**Suggestion**: Either confirm the card on purpose (say so in the Result), or reword it around the three questions and regenerate the explained page in this same change.

### A5

### 5. [Nit] Drops the `**Why:**` label that all four #633 principles in this repo keep
**Location**: principles/depth-over-breadth.md:7 (the line that replaced `**Why:**`) and :19 (the line that replaced `**Boundary:**`)
**Finding**: The "Done when" asks for the principle to read "like the four principles of #633." In this repo those four (attack-the-premise, fix-root-causes, make-operations-idempotent and test-behavior-not-implementation) keep a labelled `**Why:**` paragraph, and most also have `**Pattern:**` or `**The test:**`. This rewrite removes every label. The prose is closer to "reasoning" in tone, but it no longer looks like its siblings.
**Suggestion**: Restore `**Why:**` at line 7, and consider `**The test:**` for the three questions at line 9, to match make-operations-idempotent.md.

### B1

### 1. [warning] "say why it is reasonable" changes the meaning of the target rule
**Location**: principles/depth-over-breadth.md:13
**Finding**: The old line said "Set a target the field would call ambitious and say it is reasonable." The new line says "...and say why it is reasonable." That turns a prompting move into a duty to justify the target.
**Evidence**: The rule comes from Felix Rieseberg's Depth move: ask for an unreasonable target and tell the worker that it is reasonable ("ask for 200ms"). `skills/deeper/SKILL.md` question 4 still says "Ask for an unreasonable target and say it is reasonable where the field would". `THIRD_PARTY.md:260` credits "an ambitious target said to be reasonable". After this change the principle no longer matches the skill it backs or the source it credits. The task asked for a change of style, not of rule.
**Suggestion**: Keep "and say it is reasonable". If the reasoning style needs a reason, add one clause on why: a target stated as reasonable makes the worker reach for the expert's tools, not trim the goal.

### B2

### 2. [warning] The test for telling depth from breadth contradicts the third question
**Location**: principles/depth-over-breadth.md:15 (it conflicts with line 13)
**Finding**: Line 15 says to hold the plan against the task's "Done when": deeper work "reaches the same outcome from better ground, and wider work changes the outcome." But the third question ("What says it is done?", line 13) is exactly a change to the "Done when". It swaps "the crewmate confirms" for a failing-then-passing test, a measured target or an outside verdict. `/deeper` rewrites the prompt to ask for that.
**Evidence**: Applied as written, the test labels the main thing depth adds (a new outside judge in the "Done when") as breadth, which belongs under "Noticed". This is the one new decision rule the rewrite adds ("and how to tell", from the Done-when line), and it is the part that is wrong. The same paragraph also says "Depth changes those three answers and nothing else. A plan that answers them by adding a deliverable..." That reads as though adding a deliverable is a way of answering the three questions, which muddles the point.
**Suggestion**: Base the test on the deliverable, not on the "Done when". Deeper work keeps what is delivered and changes where it starts, what it measures with, and what judges it. Wider work adds something to deliver.

### B3

### 3. [nit] The instruments sentence sits in the raw-data argument and is said twice
**Location**: principles/depth-over-breadth.md:7 and :12
**Finding**: "Naming a method without the command that runs it here is still words." moved out of the instruments bullet. It now sits in the middle of the paragraph about digested inputs, between "can only agree or disagree in words" and the self-judging sentence. Line 12 then says the same thing again: "A plan that names the method and not the command has the vocabulary and not the instrument."
**Evidence**: The paragraph's chain (digested input, then self-judge, then three doors) is broken by a sentence about instruments, and that point is made twice in 6 lines.
**Suggestion**: Drop it from line 7. Line 12 already covers it.

### B4

### 4. [nit] The /deeper sentence is hard to follow
**Location**: principles/depth-over-breadth.md:17
**Finding**: "`/deeper` asks these, after what a top professional would do that is not asked, as four questions of a task..." folds a whole clause into the sentence to reconcile three questions with four, and the result is hard to read.
**Evidence**: The principle now names three questions. The skill has four, and its first one ("what a top professional would do that is not asked") is the one most open to breadth. The rewrite explains neither the gap nor how that first question stays deep.
**Suggestion**: "`/deeper` asks these three, after a first question on what a top professional would insist on here, and rewrites the prompt to ask for the answers."

### B5

### 5. [nit] The "Proves it" side by side cannot be checked from the diff
**Location**: none (the change as a whole)
**Finding**: The brief's "Proves it" line asks for a side by side, in the Result, of one #633 principle and this one. Nothing in the diff shows it, and no test touches the new wording. `tests/test_principles.py` only checks the heading, em dashes and links. For prose that is acceptable. The side by side is the only check that the style matches #633, so it has to be in the Result.
