### Intent
> Every gate becomes act-unless-stopped. The thread acts on the default at once, the user sees the question as already acted on, and an answer that differs is carried back. An open plain question closes by silence at 2 hours, on a basis that says it was not the user's word, and a later answer is still taken. A gate whose default is irreversible or slow to revert must carry `Holds: <case>` and a `Fail-safe:` line. It never acts and never closes by silence: it waits for the user, with the dry-run, plan or bundle attached. `jbus gate` refuses a gate with no default, one whose recommended option is not the default, a `Holds:` gate with no fail-safe, and an unknown case. The rule, definition and table go into the home, crew and scout skills, `templates/gates.md` and `docs/jbus.md`, in the same pull request. Fake-clock tests cover it, and `make check` passes.

### Reviewers
- Reviewer A: 6 findings
- Reviewer B: 6 findings
- Both reviewers worked through the review skill's questions. They agreed on two findings (the display gap and the redundant marks). Each found a different critical in the `Holds:` path.

### Act On

1. **A `Holds:` gate answered with its default never releases the thread** (B1). A held gate's thread waits by design. `tell`, `_answer` and the page all still assume "a default answer means the thread already acted", so they send nothing on `keeps`. A held gate can therefore only ever proceed when the user says *no*, and agreeing with the recommendation does nothing. This is a concrete path that breaks the core of the fail-safe design.
   - In `tell`, carry a "go ahead with the default" message when `one.holds` is set.
   - Fix the `docs/jbus.md:132` sentence.
   - Add a test: a `Holds:` gate answered `--default` sends one message to its thread.
   - The page path (`view/__init__.py`) is outside **Where**, so note it for later. Name that gap in the Result.

2. **A re-piped gate after a silence close is told "already answered", and any new `Holds:` is dropped** (A1). `ask` treats a silence close as a settled answer. Take a thread that re-pipes the same gate after learning that its default deletes data or force-pushes. It is told to "go by" a default nobody said yes to. That is exactly the hold the user required, bypassed. The diff already has `_open()` and only needs to use it in `ask`. When the re-pipe adds `holds`, clear the silence answer. Add the fake-clock test the reviewer describes.

3. **"Shown as already acted on" and "with the fail-safe attached" are not met** (A4, B2). `acted`, `holds` and `fail_safe` reach only `waiting-on-user.json`. Nothing the user reads shows them, and the only test reads the JSON file, which is a proxy for what the user sees. Two Done-when lines are unmet. Fix it inside **Where**:
   - Put the state in the item's `line`, e.g. `question N (acted): …` or `question N (holds: deletes data; fail-safe: …): …`.
   - Add `.holds, .fail_safe` to the home skill's jq and printf.
   - The page panel and `waiting._blocks` are outside **Where**, so note them for later.

4. **Silence closes the link-conflict questions meant for the home, and stacks park** (A2). `_quiet` closes every record without `holds`, including the stack-conflict questions that the home picks up with `.answer == null`. Two hours later the home stops sending the rebase line, so this change creates parked work, the opposite of the task. Exempt questions that ask the home from `_quiet` in `questions.py`, and add a test.

5. **The home skill still says only the user's name closes a question** (A6). `skills/home/SKILL.md:822` now contradicts the rule this PR adds, in the same section the home acts from. It is a one-line fix inside **Where**, and leaving agent instructions that contradict each other is not worth it.

### Consider

- **The words panel shows a silence close as "Your answer"** (A3). The record's basis correctly says it was not the user's word, but the user's own history page claims it was. The task asked for exactly that distinction. The fix is in `view/panels/words`, outside **Where**, so note it for later unless the crewmate can fold it into a follow-up.
- **The `(default)` and `(recommended)` marks are now always equal** (A5, B5). There is a real subtraction available: treat `(default)` as the pick and refuse `(recommended)` on any other option. That still meets the Done-when line, removes two refusal branches and the fixture churn, and stops refusing older-style gates. The tradeoff is that the PR already works and the user's wording names both. This is a worthwhile simplification, not a blocker.
- **Expert findings now recommend against themselves and vanish by silence** (B3). The test fixture was bent to pass: the expert's default "leave it" is now also its recommendation, and it closes at 2 hours. That is probably not what the user wanted from expert advice. It needs a decision (a held kind, or a default that is the change itself), and `skills/expert/SKILL.md` is outside **Where**, so it is for later. Name it in the Result so it is not lost.
- **Later answers after silence work only from the CLI** (B4). The Done-when line "a later differing answer is taken" is met through `jbus answer`. The page, however, drops the question, while the docs suggest it is still easy to answer. The cheap fix inside **Where** is one sentence in `docs/jbus.md` saying the CLI takes it. A "closed by silence" state on the page is for later.

### Noted
- `_held` repeats the line-scanning logic of `mirror.field` (B6). The drift risk is real but small, and the fix (`mirror.fields`) is outside **Where**.

### Dismissed
- None. Every finding traces to a changed line and a concrete path.

### Agreement Map
The reviewers converged on the visible surface: the new state never reaches the user (A4/B2), and the marks are redundant (A5/B5). They diverged on the criticals, each finding a different hole in the same place. A1 is the re-pipe in `ask`, B1 is the `--default` path in `tell`, and A2 is `_quiet` closing records that are not user gates.

The pattern is that the PR added `holds` as a field but did not model the gate's state. The code that existed before this change (`ask`, `tell`, `_answer`, the view, the home's jq) still assumes "default means already done, and every question is a user gate". The structural fix is to make the gate's state explicit (acted, holding, closed by silence, home-directed) and have `ask`, `tell` and `silent` branch on it. That one move addresses items 1, 2 and 4 together.

BUCKETS
A1: Act on
A2: Act on
A3: Consider
A4: Act on
A5: Consider
A6: Act on
B1: Act on
B2: Act on
B3: Consider
B4: Consider
B5: Consider
B6: Noted
