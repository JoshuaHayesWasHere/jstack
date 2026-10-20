---
name: create-verification-skill
description: "Generate a project-local verification skill, `.claude/skills/verify-<app>/`, that drives the repo's app the way a user does, in any language, framework or platform. Use for /create-verification-skill, \"make a verify skill for this repo\", or when a repo has no scripted way to prove UI, CLI or service behavior."
tip: writes the repo's verify skill, which launches the app, drives a feature and keeps the evidence | make a verify skill | verification skill | drive the app | how do we prove it works | no way to drive the app
disable-model-invocation: true
card: "Distrust the change | 6 | Writes the repo's verify skill in `.claude/skills/verify-<app>/`: how to launch the app, check it, drive each feature the way a user does, keep the evidence and clean up, with a map of the features. It runs the skill once end to end before it hands it over. | Reach for it when a repo has no scripted way to prove a change works in the real app. | op: the operator; plain: a brief with the `authoring-a-skill` playbook"
---

# Create a verification skill

Source: pstack, `pstack/skills/create-verification-skill/SKILL.md`

Every serious project needs a scripted way to drive the real app and prove behavior: launch it, exercise a feature the way a user would, and capture evidence.
This skill generates that as a project-local skill, `.claude/skills/verify-<app>/`, tailored to the repo.
Claude Code loads a project's skills from `.claude/skills/`, and never from `.cursor/skills/`.
You write the generator's output for the next agent, not for a human: it will be read cold, mid-task, by an agent that has never seen the app.

## Where it runs

Run it in a durable thread, never in a subagent: the interview, the generated files and the proof run take many turns, and the skill is what has to outlive them.
A crewmate does it under a brief with `Playbook: authoring-a-skill`, in its own worktree, and every file it writes lands there.
The playbook's steps are this skill's: its step 1 is section 1 below, its step 2 is sections 2 and 3, its step 3 is section 4, and its step 5 opens the one pull request.
The proof run of section 4 goes in the Result's `Proof:` line: the launch, the Doctor's last line, the one feature driven, the cleanup, and a listing of the evidence after the cleanup.
A scout may do section 1 alone, read-only, and report the surface, the run command, the harness and the isolation it found, so that the crewmate's brief rests on it.

## 1. Interview the repo, not the user

Answer these from the codebase and only ask the user what you cannot observe:

- **Surface:** what does a user actually touch?
  A web UI, a CLI or TUI, a desktop app, an API, a mobile app, a library?
  A repo can have several: pick the primary one and note the rest.
- **Run:** how does the app start locally?
  Prefer the repo's own documented dev command (package scripts, Makefile, README quickstart).
  Note ports, env vars, seed data, auth.
- **Drive:** how can an agent interact with it programmatically?
  Existing harnesses first: Playwright or Cypress specs, expect scripts, PTY helpers, curl-able endpoints, a debug port.
  Only then pick a generic recipe: browser or CDP for web and Electron, a tmux or PTY harness for CLI and TUI, plain HTTP for services.
- **Observe:** what evidence can be captured?
  Screenshots, terminal transcripts, response bodies, logs, exit codes, DB state.
- **Isolate:** can two instances run side by side (ports, data dirs, profiles)?
  If not, say so in the generated skill: refusing to double-drive a shared instance beats corrupting the user's session.

If the checkout doesn't build or start as-is, fix that first (or report it precisely) before generating; a skill written against a broken base teaches wrong steps.
When an irrelevant missing asset blocks startup (a static dir the API never serves, a sample config), the generated skill may create it, clearly marked as verification scaffolding, and remove it in cleanup.

## 2. Generate the skill

Write `.claude/skills/verify-<app>/SKILL.md` with YAML frontmatter (`name: verify-<app>` and a `description` that names the app, the surface, and when to reach for it: without frontmatter the skill never registers) and these sections, each grounded in what the interview actually found (no placeholders left):

- **Launch:** the exact command that starts the app for verification, and how to tell it's ready (a log line, a prompt).
  Launch must reach a usable state from an empty data dir, including any migrations and seed data.
  Ready means usable, not just that a process answers.
  A database health check can pass while its init scripts are still running.
  Include teardown.
  For a short-lived CLI or TUI there is no server to keep alive: launch means build the binary (or install deps) once, then start each drive in its own isolated PTY or tmux session.
- **Doctor:** one read-only check that answers "is this instance worth driving?": process up, right version or build, port owned by us, auth valid.
  An agent runs this first whenever anything looks off.
- **Drive:** the harness recipe with real selectors and commands from this repo, not examples.
  Prefer stable handles (ARIA labels, data attributes, prompt strings, route paths) over coordinates and tab order.
- **Evidence:** what to capture for a proof and where it goes.
  State the proof standards: exercise the real user path, not internal setters or test-only endpoints; capture the action and the resulting state, not just the final screen; verify side effects (files written, rows inserted, messages sent) alongside what's visible; mocks only where a production boundary already isolates the external system.
  When the safe path is a dry-run or test mode, verify what it actually skips by observing (files, network, git refs) rather than trusting its name: some dry-runs still touch the network or open a browser.
- **Cleanup:** how to tear down instances the run created.
  Never kill by process name; kill what you started.
  Cleanup removes instances and scratch state, never the evidence: proof artifacts survive the teardown, in a location the skill names, outside the worktree's tracked files.
- **Helpers:** any script the skill ships sits in `.claude/skills/verify-<app>/scripts/`, is executable, and its invocation is shown in the skill body.
  A helper the reader has to reverse-engineer is not a helper.

## 3. Seed the feature map

Create `.claude/skills/verify-<app>/features/README.md` plus one file per user-facing feature you can identify (aim for the top 3-5 to start, from routes, commands, menus, or docs).
Follow the shape in [`references/feature-map-example/`](references/feature-map-example/), with a README index and one file per feature.
Each file answers, from the user's point of view: what the feature is, how to reach it, how to drive it with the harness, and what observable end state proves it works.
The four H2s are `Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>`, and `Gotchas`.
If the seed data lacks a precondition that a journey needs, the journey reports a failure and the reason goes in that feature's `Gotchas`.
Never weaken the journey to make it pass.
The map is the repo's maintained verification source; a proof that drives one convenient entry point is incomplete when the map lists others.

## 4. Prove the generated skill before handing it over

Run its own instructions end to end once: launch, doctor, drive ONE mapped feature (one is enough; the map exists so later runs can cover the rest), capture evidence, clean up.
After cleanup, confirm the evidence still exists at the named location: a cleanup that eats the proof fails this step.
Fix what fails, and run the generated cleanup after every failed iteration too, so broken attempts don't strand processes and ports.
A generated skill that was never executed is a draft, not a deliverable.
If you proved it in a stand-in for the real target (a container in place of a fresh VM, a local stack in place of a remote one), list every setup step the stand-in did that the target will not.
Those steps stay unverified until a run on the real target covers them.

Run the proof in this thread's own worktree, with the commands as the generated skill writes them, and paste each command and its last lines into the Result.

## 5. Point at the maintenance loop

Say in the Result that `/maintain-verification-skill`, typed in the repo's home, keeps the map honest as the app changes.
Suggest a cadence only if the user asks.
