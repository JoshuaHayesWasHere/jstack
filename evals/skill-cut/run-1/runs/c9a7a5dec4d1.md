### Intent
> Eliminate the exec home: the user's word (2026-10-15, relayed by Sous Chef) is "they can completely go; we are moving from this pattern." Sous Chef is the one orchestrator. Escalations reach it through jbus's webhook, and the user's word comes down by `jbus word`. This step removes Exec from the skills (`new-home`, `home`, `handoff`), the `jroles` role, the jbus text and the retired-streak cleanup ("keep any behaviour a test still needs, renamed"), the docs, the README and the tests that pinned it. Done when `rg` finds only the shell `exec` and `make check` passes.

### Reviewers
- Reviewer A: 7 findings
- Reviewer B: 5 findings
- Both found the dropped `[exec]` redaction, the dropped streak cleanup, the files outside "Where" and the stale gauge fixture. Each also raised something the other did not. The review skill's questions were asked.

### Act On
- **The retired `[exec]` table now loads silently, and its `webhook_url` and `webhook_key` are no longer redacted.** Raised by A1 and B1, independently.
  - The brief said to keep behaviour "renamed". The PR deleted the behaviour and the test that pinned it, and it does not record that it did so.
  - The leak path is narrow. jbus no longer reads the table, so a secret only reaches output if something quotes it. The user's config is also clean today.
  - Still, it is a security-adjacent behaviour the brief asked to keep, and it was dropped without a word.
  - The remedy is one of two things:
    - Keep it under a neutral name, with a "retired table" entry and its redaction test.
    - Close it as `Finding: not fixed, because` the table was already unread and the user said the pattern goes entirely. If this is the choice, `docs/configuration.md` should still tell an old install to delete the table.

### Consider
- **The retired `exec-webhook` streak cleanup and the `exec-sent.json` unlink were deleted, not renamed.** Raised by A2 and B2.
  - B confirmed that the live `streaks.json` and the state directories have no leftovers. That makes the deletion defensible, and it fits "completely go".
  - The cost is a sentence in the PR saying the cleanup was dropped on purpose and why. Restoring the code is not needed unless the user expects other installs.
- **The new line at `skills/home/SKILL.md:98` adds "A home sends no other thread a status".** Raised by A5.
  - That is a standing rule the brief did not ask for. It also reads against the home messaging its own crewmates.
  - The brief keeps the scout's 5c wording, so check 5c. If 5c does not have this clause, drop it. If it does, the clause may still read wrong in place, which the brief allows as a reason to change it.
- **The gauge fixture still carries the removed pair-telling message.** Raised by A7 and B5. The `t3_thread_send` entry should stay, but its example should be a mail pass-on. It is a cheap fix, and it keeps the test describing calls the handoff still makes.
- **`docs/jbus.md:279` now says every session is "the `<directory>` home".** Raised by B4. Sous Chef's own approvals would be labelled as a home. The `who()` behaviour is not new, but the changed doc line now states it as fact. Rewording that one line is cheap. Fixing `who()` itself belongs to a follow-up.

### Noted
- **The party-handoff machinery may have no real party left** (A3). With Exec and the experts retired, the case is plausible. But the brief kept the party handoff and only removed its `exec` role and case, and `skills/expert/` is off-limits beyond removing the Exec mention. Record it as a follow-up and leave it out of this PR.
- **Files outside "Where"** (A4, B3): `project.py`, the t3 fixture README, `test_jbus_view.py` and `test_home_on_bus.py`. Each is a wording change the `rg` Done-when line requires, so they trace to the task. The one behavioural file, `__init__.py`, is covered under Act On.
- **The `ROLES` tuple assertion in `test_roles.py`** (A6). The role set is arguably observable behaviour, so this is a minor point. Using `exec` as the refused input would be slightly sharper, but this does not need to change.

### Dismissed
- None. No finding was wrong. The nits were small but grounded in changed lines.

### Agreement Map
**Where the reviewers agreed.** Both independently landed on the same core issue: the PR deleted two already-retired compatibility shims (the `[exec]` ignore and redaction, and the streak cleanup) rather than renaming them as the brief said. They also matched on the two small cleanup items, the files outside "Where" and the stale fixture. That consensus is the signal.

The text sweep itself drew no correctness complaints. The real question is one decision the PR made silently: "completely go" versus "keep behaviour, renamed". Whichever way it goes, it has to be stated.

**Where they diverged.**
- A pushed on scope in both directions: the larger cut of the party handoff, and the extra rule in the home skill.
- B looked at audit labelling once Sous Chef is the only orchestrator.

Neither divergence is a defect in the change as briefed.

BUCKETS
A1: Act on
A2: Consider
A3: Noted
A4: Noted
A5: Consider
A6: Noted
A7: Consider
B1: Act on
B2: Consider
B3: Noted
B4: Consider
B5: Consider
