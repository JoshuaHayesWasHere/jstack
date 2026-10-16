# pstack-autopilot-ketchup

## Intent

Task: the audit's P4
Done when:
- `playbooks/autopilot-full.md` step 5 and Hand over, and `playbooks/autopilot-stack.md` Hand over, say a tick or reply that changed something ends by catching the user up per `skills/ketchup` (upstream 8043881); a tick that changed nothing still ends silently, unchanged
- the playbook tests pass, and `make check` exits 0, and `jgauge test-slot -- make check` passes here
Proves it: `make pstack-drift ARGS=--diff` for the two playbooks against 8043881, and the playbook tests
Size: S
Where: `playbooks/autopilot-full.md`, `playbooks/autopilot-stack.md`, their tests
Do not touch: `skills/ketchup` (pstack-ketchup's); `THIRD_PARTY.md`
Decisions: the user, 2026-10-15 09:44 ET, word 79eb162adcb3, from Sous Chef's Grok Bot chat: "Yes, send it", approving the pstack catch-up (bring jstack up to current pstack, the #633 principle rewrite and every other upstream update it is missing), in the audit's priority order. Upstream is cursor/plugins `pstack/` at e5136d8; read it from a fresh clone in a temporary directory (`git clone --filter=blob:none`), never from memory. Keep jstack's local form where the audit says so. The split is the home's call. A question only he can answer is a gate: take the default, pipe it to `jbus gate <slug>` with every option you weighed, and carry on. Ask him nothing in this thread.
Design: ~/.local/state/home/jstack/scouts/pstack-drift-2026-10-15.md, P4

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

### 1. [warning] Step 5 now gives a second rule for the tick's reply, and it contradicts the one in "One tick"
**Location**: playbooks/autopilot-full.md:19 (step 5). The rule it collides with is in skills/home/queue-and-its-hourly-audit.md:110 ("One tick", step 4).
**Finding**: Step 5 already tells the home to "Work each tick as 'One tick' says". That section's step 4 sets the tick's reply: "Tell the user what this tick changed, in one line each: a merge, a launch with its link, a stuck thread and what was done, and a question asked. Nothing that an earlier message said." The new sentence tells the home to end the same tick by catching the user up per `skills/ketchup/SKILL.md`. Ketchup covers "what changed in this chat since the last message they wrote". It has its own format: an opening sentence counting what needs the user, visuals, a bullet per thing the user asked for, two-line action items, under 150 words.
**Evidence**: Autopilot runs "with no word from the user", so the user's last message can be hours and many ticks old. If the home follows ketchup, each tick that changes something repeats everything earlier ticks already reported, and the reply grows each hour. That breaks One tick's "Nothing that an earlier message said". If the home follows One tick, the new sentence does nothing. The home now has two rules for one reply and must pick one. That is an old path kept beside a new one, and it is decided only by a prose convention.
**Suggestion**: Keep one rule. Either bound the catch-up to "what this tick changed, nothing an earlier message said", or move the ketchup rule into "One tick" step 4 and have step 5 only point there. The second option changes skills/home/queue-and-its-hourly-audit.md, which is outside "Where", so note it for later.

### A2

### 2. [warning] "Changed something for the user" leaves a gap between the two tick endings
**Location**: playbooks/autopilot-full.md:19
**Finding**: The task asks for two cases: a tick that changed something catches the user up, and one that changed nothing stays silent. The new wording has three: "changed something for the user", "changed nothing", and a tick that changed something but not "for the user". Examples of the third are a launch, re-sending a stuck thread, or a `session-pickup`. Neither sentence covers it.
**Evidence**: Ketchup also says "Leave out work that changed nothing for the user". So a tick that launched a crewmate or picked up a stuck thread may end with no message at all. One tick step 4 explicitly requires telling the user about exactly those ("a launch with its link, a stuck thread and what was done").
**Suggestion**: Drop "for the user" so the two sentences split the ticks cleanly: "A tick that changed something ends by catching the user up…; a tick that changed nothing ends with no reply."

### A3

### 3. [warning] Both Hand over lines require content that ketchup's own rules tell the writer to cut
**Location**: playbooks/autopilot-full.md:32 and playbooks/autopilot-stack.md:33 (Hand over)
**Finding**: The full hand-over must cover "each entry with its crewmate's link, its state and its pull request; what merged, with the commit; each stuck thread…". The stack hand-over must give "one line a link with its verdict". Each is now framed as "per `skills/ketchup/SKILL.md`". Ketchup says:
- "Keep the whole reply well under 150 words".
- "Leave out hashes … unless the user needs one to act".
- "Leave out work that changed nothing for the user".
- "When words run short, cut from what happened before you cut from the action items".
**Evidence**:
- A six-entry queue, with a link, state and pull request for each, plus merges and commits, plus stuck threads, plus gates, does not fit in 150 words. Ketchup then tells the writer to cut exactly the per-entry account the Hand over requires.
- "What merged, with the commit" contradicts "leave out hashes".
- Step 7's closing account ("account for every entry by its line in `$H/merge.log`") is the same handover, and it does not mention ketchup.

A writer cannot satisfy both texts, and nothing says which one wins.
**Suggestion**: Say which one wins. For example: "catch the user up in ketchup's voice; the account of every entry below is kept whole and is not cut for length". Or limit ketchup to the opening and the action items, and keep the per-entry list as its own part.

### A4

### 4. [nit] In the stack playbook, step 8 and Hand over now describe the same delivery in two different ways
**Location**: playbooks/autopilot-stack.md:33. The other description is step 8 at playbooks/autopilot-stack.md:23.
**Finding**: Step 8 still says "Tell the user the name, each link from the bottom up with its pull request and its verdict, what is parked or left out and why, and that it lands on their word". The changed Hand over line, which fires at the same moment ("when the top link is fixed and green"), now says to do it per ketchup. The two descriptions of one message have drifted apart. Step 8 also has "that it lands on their word, 'land <name>'", which the Hand over does not.
**Suggestion**: Have step 8 point to the Hand over line, or use the same wording in both.

### A5

### 5. [nit] No test executes or pins the new behaviour
**Location**: none (this is about the change as a whole)
**Finding**: The only automated check that touches the change is the existing `names X, which is not there` check in tests/test_playbooks.py. It confirms `skills/ketchup/SKILL.md` exists. Nothing checks that step 5 keeps both endings (catch up when something changed, silent otherwise). Nothing catches the contradiction with "One tick" step 4 (finding 1).
**Suggestion**: Add a test that loads the playbook and the "One tick" section and asserts they agree on how a tick ends. For example, parse the step-5 sentence and One tick step 4 and check that both name the same reply rule. That beats a test that only matches wording.

### B1

### 1. [warning] The tick line now contradicts the home skill's "One tick" step 4, which is what a tick actually follows
**Location**: playbooks/autopilot-full.md:19. The conflicting text is in skills/home/queue-and-its-hourly-audit.md:110.
**Finding**: Step 5 still says "Work each tick as 'One tick' says". One tick's step 4 says: "Tell the user what this tick changed, in one line each ... Nothing that an earlier message said." The new sentence says the same tick "ends by catching them up per `skills/ketchup/SKILL.md`". Ketchup's rules work differently:
- It covers everything since the user's last message, not since the last tick.
- It opens with a count of things that need the user.
- It checks every pull request and thread with `gh pr view` and `t3_thread_read`, and runs the gates block.
- It draws visuals.

**Evidence**: The audit fires every hour, and the user is usually away while it runs. Each ketchup-style tick reply would repeat every merge and launch since the user last wrote. That breaks "Nothing that an earlier message said" in the home skill. So the home now gets two different rules for one reply, and nothing decides which wins. Upstream does not have this problem: its "One tick" has no separate one-line-each rule.
**Suggestion**: Make one rule own the tick reply. The cleanest way is to change One tick step 4 itself to point to ketchup, scoped to "since the last tick". That file is outside the "Where" line, so note it for later. Within this pull request, at least say that the catch-up covers only what this tick changed, so the two rules agree.

### B2

### 2. [warning] The Hand over line asks for things ketchup tells the model to leave out
**Location**: playbooks/autopilot-full.md:32, and the same pattern at playbooks/autopilot-stack.md:33.
**Finding**: The line now says "catch the user up per `skills/ketchup/SKILL.md`, covering each entry with its crewmate's link, its state and its pull request; what merged, with the commit; ...". Ketchup (skills/ketchup/SKILL.md, "Write the reply" and the opening voice paragraph) says three things that clash with this:
- "Leave out hashes ... unless the user needs one to act". The Hand over asks for the commit.
- "Keep the whole reply well under 150 words". A queue of any real size cannot fit every entry with its link, state and pull request in that.
- "cut from what happened before you cut from the action items". So the per-entry list is exactly what ketchup tells the model to drop.

**Evidence**: Step 7 of autopilot-full requires accounting for every entry: merged, with its pull request and commit, or left, with the reason. Under ketchup's word limit and cutting order, that list gets shortened or loses its commits. The two instructions in this one sentence pull in opposite directions, and the model has to guess which wins.
**Suggestion**: Keep the per-entry list as its own required part, outside ketchup's limit. For example: "account for each entry as step 7 says, then catch the user up per `skills/ketchup/SKILL.md` on the rest". Or say outright that the listed items override ketchup's word limit and its no-hash rule.

### B3

### 3. [nit] "Changed something for the user" is a new, undefined test that does not match One tick's list
**Location**: playbooks/autopilot-full.md:19
**Finding**: The new sentence only applies to "a tick that changed something for the user", while the next sentence keeps "a tick that changed nothing". One tick step 4 already lists what counts as a change: a merge, a launch, a stuck thread, a question. It also excludes `hold` lines. The phrase "for the user" adds a third test that matches neither. A tick that only launched a crewmate fits neither sentence clearly.
**Suggestion**: Drop "for the user", so the two sentences cover every tick between them and use One tick's own definition of a change.

### B4

### 4. [warning] Nothing in the change tests the new behaviour
**Location**: no file. This is about the change as a whole.
**Finding**: The "Where" line includes the playbooks' tests, but the diff touches no test. The existing checks in tests/test_playbooks.py run the playbook checker, so a missing `skills/ketchup/SKILL.md` would fail. But nothing checks that step 5 and both Hand over lines point to ketchup, or that the silent-tick sentence is still there. A later edit could drop either one and every test would still pass.
**Suggestion**: Add a test that runs the existing playbook parser in tests/test_playbooks.py on both files. It should check that step 5 and the Hand over section name `skills/ketchup/SKILL.md`, and that step 5 still ends with the no-reply sentence for an unchanged tick. Do not add a bare string match.
