### Intent
> Eliminate the Exec home, as the user said on 2026-10-15 ("they can completely go, we are moving from this pattern"). Sous Chef is the one orchestrator, escalations reach the user through jbus's webhook, and the experts retire with Exec. This is step 4 of `scouts/exec-home-removal.md`: scrub Exec from the new-home, home and handoff skills, `jroles`, the jbus text, the docs and the pinned tests. `rg` should find only shell `exec`, and `make check` should pass. The brief said to keep any behaviour a test still needs, renamed.

### Reviewers
- Reviewer A: 7 findings
- Reviewer B: 5 findings
- The reviewers converged on the three substantive points: the dropped `[exec]` handling, the dropped streak cleanup, and the out-of-Where files. Neither reported a `make check` or `rg` failure, so the mechanical Done-when lines look met.

### Act On
- **The `exec-webhook` streak cleanup was deleted, but the brief said to rename it.** Raised by A2 and B2. This Done-when line names the cleanup explicitly and asks for its text to change, not for it to go. B checked that this machine has no leftover streak and no `exec-sent.json`, so deleting it is defensible. The PR does not say so, though, and the test that pinned it went with it. Fix it one of two ways:
  - restore it under a neutral constant, with its test renamed; or
  - write `Finding: not fixed, …, because` with the live-state check as evidence.

  Either is cheap. Leaving the departure silent is not acceptable.
- **The new line in the home skill adds a standing rule nobody asked for.** Raised by A5. "A home sends no other thread a status" goes beyond the brief's one line. `skills/home/SKILL.md` is fenced ("text this brief does not name"). Skill text is instruction to agents, and this clause reads against a home messaging its own crewmates and scouts. Drop the clause and use the brief's wording.

### Consider
- **A stale `[exec]` table now loads silently and is no longer redacted.** Raised by A1 and B1, so this is a consensus finding. The real loss is the "remove them" notice. With nothing reading the table, there is little path for its URL or key to reach output, so the redaction risk is thin. The tradeoff:
  - The user's config is clean, and the intent is to drop Exec entirely.
  - jstack installs elsewhere, and the notice was the only cleanup prompt.

  The cheapest remedy keeps a generic "retired key" notice that names no Exec, as B suggests. Otherwise, record that dropping it was deliberate. The change sits in `src/jbus/__init__.py`, outside Where. It is needed for `rg`, but the behavioural change is the crewmate's call to justify.
- **The leftover pair-tell message in the gauge test.** Raised by A7 and B5. The example message describes a send this PR removed. Changing the string to the mail pass-on's shape is a one-line fix, and then the test describes what a handoff still does.
- **The party handoff machinery no longer has a real user.** Raised by A3. With Exec and the experts retired, `party_home` and its blocks are kept alive only by an invented `desk` fixture. This matches the user's "moving from this pattern". It is still wider than this brief, though, and `skills/expert/` is fenced. Carry it to a follow-up step of the removal plan, not this PR.

### Noted
- **Files outside Where** (A4, B3): `project.py`, the t3 fixture README, `test_jbus_view.py` and `test_home_on_bus.py` are wording edits the `rg` line requires. `__init__.py` is covered above.
- **The `who()` label and the doc line in `docs/jbus.md:279`** (B4): Chef approvals were already mislabelled before this PR. A doc rewording would help, but it is a follow-up.
- **The tuple assertion in `test_roles.py`** (A6): this is mild implementation pinning, and the behavioural assertions already cover the refusal. A's suggestion to use `exec` as the refused role would break the `rg` Done-when line, so that part does not apply.

### Dismissed
- None outright. A6's alternative is set aside as noted above.

### Agreement Map
Both reviewers independently caught the same two behaviour deletions (A1/B1 and A2/B2) and the same leftover fixture string (A7/B5). That pattern is the signal: the PR met the text scrub cleanly but deleted behaviour and its tests where the brief said to rename. A alone pushed toward deeper subtraction (A3) and saw the scope creep in the skill text (A5). B alone checked the live state, which is what turns the streak deletion from a bug into a recording gap. The divergent findings are mostly scope and test-hygiene points. Nothing suggests a hidden correctness bug beyond the two deletions.

BUCKETS
A1: Consider
A2: Act on
A3: Consider
A4: Noted
A5: Act on
A6: Noted
A7: Consider
B1: Consider
B2: Act on
B3: Noted
B4: Noted
B5: Consider
