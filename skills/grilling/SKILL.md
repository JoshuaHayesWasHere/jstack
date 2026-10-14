---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea, until nothing is left assumed. Use for /grilling, or when a home plans work whose shape is not settled.
tip: questions a plan until nothing is left assumed | grill me | poke holes | what am i missing | challenge my plan
disable-model-invocation: true
card: "Settle the shape before code | 1 | Questions the operator about a plan, a decision or an idea, round after round, until nothing is left assumed. | Reach for it when the work is more than one task, or a design choice is not made yet. | op: the operator; model: a home"
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (the code, the docs, a tool), send the `Explore` agent to find it, which in a home is a light scout (or, with no subagent tool, do it in this thread); don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## In a home

Grilling is planning, so it is the one place a home waits for the user round after round: what the work is for comes from them. It ends before anything is launched. Once a task is out, a question only the user can answer is a gate with a default, not a new round.

When the user confirms, write what was settled into `plan.md`: one entry per task, each answer under **Decisions** in the entry it belongs to, in the user's words, with the date. An answer that was "yes" is recorded as the recommended answer it accepted.

## On a page

In a home, a round of two or more questions is a page, and once a grill has a page every later round is on it, the confirming one included. A round stays text, in the format above, when it is one question and no page is open, when this thread is not a home, or when `lavish-axi` is not on `PATH`.

The page is one file, made from `$T/grill-page.html`. Shell variables do not last from one call to the next, so run each block below in one call with this one at its top, `<slug>` being a short name for what the grill is about:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/grilling/../../templates)
F="$H/reports/grill-<slug>.html"
```

1. Make the file. A file that is there is kept: it is this grill's, from an earlier round. On `no page`, there is nothing to serve a page with and no file is made: ask this round, and every later one, as text.

   ```sh
   if ! command -v lavish-axi > /dev/null; then
       echo "no page: lavish-axi is not installed"
       exit 0
   fi
   mkdir -p "$H/reports"
   [ -f "$F" ] || cp "$T/grill-page.html" "$F"
   ```

2. Write the round into the file's `round-data` block, by hand, and change nothing else in the file. The comment above the block names every key. Each question has an `id` that says what it decides, and exactly one option with `"recommended": true`: that one is checked when the page opens, so a question the user leaves alone is a yes. A block that breaks a rule draws no round: the page lists what is wrong and sends nothing.
3. Open the session, once per grill. The block prints the session's status, any warning Lavish gave, and on its last line the address Lavish printed: give the user that one, as it is. If it exits with `no session`, it has printed what Lavish said: the grill goes on as text. On `status: user-ended` the user closed this page and it was not opened again: give no address, and go on as text.

   ```sh
   out=$(lavish-axi "$F" --no-open 2>&1)
   at=$(printf '%s\n' "$out" | sed -n 's|.*url: "\(http[^"]*/session/[0-9a-f]*\)".*|\1|p' | head -n 1)
   if [ -z "$at" ]; then
       printf '%s\n' "$out"
       echo "no session: the page is not open"
       exit 1
   fi
   printf '%s\n' "$out" | grep -E '^ *(status|self_paint_warning|network_warning):'
   echo "$at"
   ```

4. Hold one poll for the round, as a tracked background command (the Bash tool's `run_in_background`), and end your turn. It is one wait that returns once, when the user presses "Send to Claude", and its return wakes this thread. Never a loop, `&` or `nohup`, and never a second poll while one is out.

   ```sh
   lavish-axi poll "$F"
   ```

5. Read what the poll returned in full: one line per question, and under `Context data:` the same answers as JSON (`id`, `option`, `label`, `left_as_recommended`, `note`). If it says the user ended the session, the grill goes on as text. If it says `status: browser_disconnected`, the user closed the tab and sent nothing: ask, as text, whether to go on on the page, and hold the next poll only when they say so. On a no, end the session with the block of step 7, and the grill goes on as text.
6. Recompute the frontier and write the next round into the same file: move each answered question into `settled`, put the new frontier in `questions`, and raise `round`. The open page reloads by itself, so go back to step 4. When the frontier is empty, the last round is one question that asks the user to confirm the shared understanding.
7. On that confirmation, write the Decisions as "In a home" says. Each line carries the date, the question's `id`, the option's label and the note, word for word. An answer with no note is a picked choice: say so, and do not pass the label off as the user's wording. Then end the session. The file stays.

   ```sh
   lavish-axi end "$F"
   ```
